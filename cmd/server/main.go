package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/config"
	"github.com/kekxv/ai-gateway/internal/handler"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/service"
	"github.com/kekxv/ai-gateway/internal/utils"
)

func main() {
	// Load configuration
	cfg, err := config.Load("configs/config.yaml")
	if err != nil {
		log.Printf("Warning: Failed to load config file: %v, using defaults", err)
	}

	// Initialize database
	dbPath := "ai-gateway.db"
	if cfg != nil && cfg.Database.Path != "" {
		dbPath = cfg.Database.Path
	}
	// Parse SQLite URI format: file:path, file:/path, file:///path
	if strings.HasPrefix(dbPath, "file:") {
		dbPath = strings.TrimPrefix(dbPath, "file:")
		// Handle // or /// prefix (normalize to single / for absolute paths)
		for strings.HasPrefix(dbPath, "//") {
			dbPath = strings.TrimPrefix(dbPath, "/")
		}
	}
	log.Printf("Using database: %s", dbPath)
	db, err := config.InitDatabase(dbPath)
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}

	// Initialize repositories
	userRepo := repository.NewUserRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	settingsRepo := repository.NewSettingsRepository(db)

	// Get JWT secret from settings or environment
	jwtSecret := ""
	if cfg != nil {
		jwtSecret = cfg.Auth.JWTSecret
	}
	if jwtSecret == "" {
		jwtSecret, err = settingsRepo.GetJWTSecret(context.Background())
		if err != nil {
			// Generate new secret
			jwtSecret, _ = utils.GenerateRandomSecret(64)
			settingsRepo.Set(context.Background(), "JWT_SECRET", jwtSecret)
		}
	}

	jwtExpiry := 8 * time.Hour
	if cfg != nil {
		jwtExpiry = cfg.Auth.JWTExpiry
	}

	// Initialize services
	authService := service.NewAuthService(userRepo, jwtSecret, jwtExpiry)
	billingService := service.NewBillingService(userRepo)

	proxyConfig := &service.ProxyConfig{}
	if cfg != nil {
		proxyConfig.HTTPProxy = cfg.Proxy.HTTPProxy
		proxyConfig.HTTPSProxy = cfg.Proxy.HTTPSProxy
		proxyConfig.NoProxy = utils.ParseNoProxy(cfg.Proxy.NoProxy)
	}

	gatewayService := service.NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, proxyConfig,
	)

	responseService := service.NewResponseService(
		modelRepo, modelRouteRepo, providerRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, proxyConfig,
	)

	// Initialize model sync service
	modelSyncService := service.NewModelSyncService(providerRepo, modelRepo, modelRouteRepo)

	// Initialize handlers
	authHandler := handler.NewAuthHandler(authService)
	userHandler := handler.NewUserHandler(userRepo, logRepo, authService)
	providerHandler := handler.NewProviderHandler(providerRepo, modelRepo, modelRouteRepo, modelSyncService)
	channelHandler := handler.NewChannelHandler(channelRepo)
	modelHandler := handler.NewModelHandler(modelRepo, modelRouteRepo, channelRepo)
	apiKeyHandler := handler.NewAPIKeyHandler(apiKeyRepo, authService)
	logHandler := handler.NewLogHandler(logRepo, logDetailRepo)
	statsHandler := handler.NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)
	gatewayHandler := handler.NewGatewayHandler(gatewayService, responseService)
	anthropicHandler := handler.NewAnthropicHandler(gatewayService)

	// Setup Gin
	port := 3000
	if cfg != nil {
		port = cfg.Server.Port
		if cfg.Server.Mode == "release" {
			gin.SetMode(gin.ReleaseMode)
		}
	}

	r := gin.Default()

	// Middleware
	r.Use(middleware.CORS())

	// ========== Routes ==========
	setupRoutes(r, &Dependencies{
		JWTSecret:        jwtSecret,
		AuthHandler:      authHandler,
		UserHandler:      userHandler,
		ProviderHandler:  providerHandler,
		ChannelHandler:   channelHandler,
		ModelHandler:     modelHandler,
		APIKeyHandler:    apiKeyHandler,
		LogHandler:       logHandler,
		StatsHandler:     statsHandler,
		GatewayHandler:   gatewayHandler,
		AnthropicHandler: anthropicHandler,
		APIKeyRepo:       apiKeyRepo,
	})

	// ========== Static Files (Frontend) ==========
	setupStaticRoutes(r)

	// Initialize and start scheduler if enabled
	var scheduler *service.SchedulerService
	if cfg != nil && cfg.Scheduler.Enabled {
		scheduler = service.NewSchedulerService(
			modelSyncService,
			cfg.Scheduler.SyncInterval,
			cfg.Scheduler.InitialDelay,
		)
		ctx, cancel := context.WithCancel(context.Background())
		scheduler.Start(ctx)
		defer func() {
			cancel()
			scheduler.Stop()
		}()
	}

	// Start server with graceful shutdown
	addr := fmt.Sprintf(":%d", port)
	srv := &http.Server{
		Addr:    addr,
		Handler: r,
	}

	// Start server in a goroutine
	go func() {
		log.Printf("AI Gateway starting on %s", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down server...")

	// Stop scheduler first
	if scheduler != nil {
		scheduler.Stop()
	}

	// Give outstanding requests 5 seconds to complete
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatal("Server forced to shutdown:", err)
	}
	log.Println("Server exited")
}

// Dependencies holds all dependencies for handlers
type Dependencies struct {
	JWTSecret        string
	AuthHandler      *handler.AuthHandler
	UserHandler      *handler.UserHandler
	ProviderHandler  *handler.ProviderHandler
	ChannelHandler   *handler.ChannelHandler
	ModelHandler     *handler.ModelHandler
	APIKeyHandler    *handler.APIKeyHandler
	LogHandler       *handler.LogHandler
	StatsHandler     *handler.StatsHandler
	GatewayHandler   *handler.GatewayHandler
	AnthropicHandler *handler.AnthropicHandler
	APIKeyRepo       *repository.APIKeyRepository
}

func setupRoutes(r *gin.Engine, deps *Dependencies) {
	// ========== Auth API (No JWT required) ==========
	r.POST("/api/auth/login", deps.AuthHandler.Login)

	// ========== Admin API (JWT required) ==========
	admin := r.Group("/api")
	admin.Use(middleware.JWTAuth(deps.JWTSecret))

	// User management
	admin.GET("/users", middleware.RequireRole("ADMIN"), deps.UserHandler.ListUsers)
	admin.POST("/users", middleware.RequireRole("ADMIN"), deps.UserHandler.CreateUser)
	admin.GET("/users/:id", deps.UserHandler.GetUser)
	admin.PUT("/users/:id", middleware.RequireRole("ADMIN"), deps.UserHandler.UpdateUser)
	admin.DELETE("/users/:id", middleware.RequireRole("ADMIN"), deps.UserHandler.DeleteUser)
	admin.PUT("/users/:id/balance", middleware.RequireRole("ADMIN"), deps.UserHandler.UpdateBalance)
	admin.POST("/users/:id/toggle-disabled", middleware.RequireRole("ADMIN"), deps.UserHandler.ToggleUserDisabled)

	// Current user
	admin.GET("/users/me", deps.UserHandler.GetCurrentUser)
	admin.POST("/users/me/change-password", deps.AuthHandler.ChangePassword)
	admin.GET("/users/me/stats", deps.UserHandler.GetUserStats)
	admin.POST("/users/me/totp/setup", deps.AuthHandler.SetupTOTP)
	admin.POST("/users/me/totp/verify", deps.AuthHandler.VerifyTOTP)
	admin.POST("/users/me/totp/disable", deps.AuthHandler.DisableTOTP)

	// Provider management
	admin.GET("/providers", deps.ProviderHandler.ListProviders)
	admin.POST("/providers", deps.ProviderHandler.CreateProvider)
	admin.GET("/providers/:id", deps.ProviderHandler.GetProvider)
	admin.PUT("/providers/:id", deps.ProviderHandler.UpdateProvider)
	admin.DELETE("/providers/:id", deps.ProviderHandler.DeleteProvider)
	admin.GET("/providers/:id/load-models", deps.ProviderHandler.LoadModels)
	admin.POST("/providers/:id/add-models", deps.ProviderHandler.AddModels)
	admin.POST("/providers/:id/sync-models", deps.ProviderHandler.SyncModels)

	// Channel management
	admin.GET("/channels", deps.ChannelHandler.ListChannels)
	admin.POST("/channels", deps.ChannelHandler.CreateChannel)
	admin.GET("/channels/:id", deps.ChannelHandler.GetChannel)
	admin.PUT("/channels/:id", deps.ChannelHandler.UpdateChannel)
	admin.DELETE("/channels/:id", deps.ChannelHandler.DeleteChannel)
	admin.POST("/channels/:id/providers", deps.ChannelHandler.BindProviders)
	admin.POST("/channels/:id/models", deps.ChannelHandler.BindModels)

	// Model management
	admin.GET("/models", deps.ModelHandler.ListModels)
	admin.POST("/models", deps.ModelHandler.CreateModel)
	admin.GET("/models/:id", deps.ModelHandler.GetModel)
	admin.PUT("/models/:id", deps.ModelHandler.UpdateModel)
	admin.DELETE("/models/:id", deps.ModelHandler.DeleteModel)
	admin.GET("/models/:id/routes", deps.ModelHandler.GetModelRoutes)

	// Model routes
	admin.POST("/model-routes", func(c *gin.Context) {
		// TODO: Implement create model route
		c.JSON(201, gin.H{"message": "create route"})
	})

	// API Key management
	admin.GET("/keys", deps.APIKeyHandler.ListAPIKeys)
	admin.POST("/keys", deps.APIKeyHandler.CreateAPIKey)
	admin.PUT("/keys/:id", deps.APIKeyHandler.UpdateAPIKey)
	admin.DELETE("/keys/:id", deps.APIKeyHandler.DeleteAPIKey)

	// Logs and stats
	admin.GET("/logs", deps.LogHandler.ListLogs)
	admin.GET("/logs/:id", deps.LogHandler.GetLogDetail)
	admin.GET("/stats", deps.StatsHandler.GetStats)
	admin.DELETE("/cleanup/log-details", middleware.RequireRole("ADMIN"), deps.LogHandler.CleanupLogDetails)
	admin.POST("/test-model", deps.StatsHandler.TestModel)

	// ========== Gateway API (API Key required) ==========
	v1 := r.Group("/api/v1")
	v1.Use(middleware.APIKeyAuth(deps.APIKeyRepo))

	v1.POST("/chat/completions", deps.GatewayHandler.ChatCompletions)
	v1.GET("/models", deps.GatewayHandler.ListGatewayModels)
	v1.POST("/embeddings", deps.GatewayHandler.Embeddings)
	v1.POST("/audio/transcriptions", deps.GatewayHandler.AudioTranscriptions)
	v1.POST("/audio/translations", deps.GatewayHandler.AudioTranslations)
	v1.POST("/images/generations", deps.GatewayHandler.ImageGenerations)
	v1.POST("/images/edits", deps.GatewayHandler.ImageEdits)
	v1.POST("/images/variations", deps.GatewayHandler.ImageVariations)
	v1.GET("/responses", func(c *gin.Context) { c.JSON(200, gin.H{"data": []gin.H{}}) })
	v1.POST("/responses", deps.GatewayHandler.CreateResponse)
	v1.GET("/responses/:id", deps.GatewayHandler.GetResponse)
	v1.DELETE("/responses/:id", deps.GatewayHandler.DeleteResponse)
	v1.POST("/responses/:id/cancel", deps.GatewayHandler.CancelResponse)
	v1.POST("/responses/compact", deps.GatewayHandler.CompactConversation)
	v1.GET("/dashboard/billing/subscription", deps.GatewayHandler.BillingSubscription)
	v1.GET("/dashboard/billing/usage", deps.GatewayHandler.BillingUsage)

	// ========== Anthropic Messages API (API Key required) ==========
	anthropic := r.Group("/api/anthropic/v1")
		anthropic.Use(middleware.APIKeyAuth(deps.APIKeyRepo))
		anthropic.POST("/messages", deps.AnthropicHandler.CreateMessages)
}
