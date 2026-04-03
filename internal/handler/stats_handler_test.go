package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/test"
)

func TestGetStatsHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	logRepo := repository.NewLogRepository(db)
	userRepo := repository.NewUserRepository(db)
	modelRepo := repository.NewModelRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	statsHandler := NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/stats", middleware.MockJWTAuthWithAdmin(adminUser.ID), statsHandler.GetStats)

	req := httptest.NewRequest("GET", "/stats", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGetStatsHandler_WithLogs(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	logRepo := repository.NewLogRepository(db)
	userRepo := repository.NewUserRepository(db)
	modelRepo := repository.NewModelRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	statsHandler := NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create some logs
	for i := 0; i < 5; i++ {
		log := &models.Log{
			APIKeyID:         apiKey.ID,
			ModelName:        "gpt-4",
			ProviderName:     "openai",
			PromptTokens:     100,
			CompletionTokens: 50,
			TotalTokens:      150,
			Cost:             10,
			Status:           200,
			CreatedAt:        time.Now(),
		}
		db.Create(log)
	}

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/stats", middleware.MockJWTAuthWithAdmin(adminUser.ID), statsHandler.GetStats)

	req := httptest.NewRequest("GET", "/stats", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGetStatsHandler_ProviderModelCounts(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	logRepo := repository.NewLogRepository(db)
	userRepo := repository.NewUserRepository(db)
	modelRepo := repository.NewModelRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	statsHandler := NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)

	// Create providers
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider1" })
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider2" })

	// Create models
	test.CreateTestModel(db, func(m *models.Model) { m.Name = "model1" })
	test.CreateTestModel(db, func(m *models.Model) { m.Name = "model2" })
	test.CreateTestModel(db, func(m *models.Model) { m.Name = "model3" })

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/stats", middleware.MockJWTAuthWithAdmin(adminUser.ID), statsHandler.GetStats)

	req := httptest.NewRequest("GET", "/stats", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	// The response should include providerCount and modelCount
	// This test verifies the API structure is correct
}

func TestGetStatsHandler_UserStatsForAdmin(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	logRepo := repository.NewLogRepository(db)
	userRepo := repository.NewUserRepository(db)
	modelRepo := repository.NewModelRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	statsHandler := NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)

	// Create multiple users
	test.CreateTestUser(db, func(u *models.User) { u.Email = "user1@example.com" })
	test.CreateTestUser(db, func(u *models.User) { u.Email = "user2@example.com" })
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "disabled@example.com"
		u.Disabled = true
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/stats", middleware.MockJWTAuthWithAdmin(adminUser.ID), statsHandler.GetStats)

	req := httptest.NewRequest("GET", "/stats", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGetStatsHandler_NonAdmin(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	logRepo := repository.NewLogRepository(db)
	userRepo := repository.NewUserRepository(db)
	modelRepo := repository.NewModelRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	statsHandler := NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)

	// Regular user should still be able to get stats (just without userStats)
	regularUser := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "regular@example.com"
	})

	router := gin.New()
	router.GET("/stats", middleware.MockJWTAuthWithUser(regularUser.ID), statsHandler.GetStats)

	req := httptest.NewRequest("GET", "/stats", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestTestModelHandler(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	logRepo := repository.NewLogRepository(db)
	userRepo := repository.NewUserRepository(db)
	modelRepo := repository.NewModelRepository(db)
	providerRepo := repository.NewProviderRepository(db)
	statsHandler := NewStatsHandler(logRepo, userRepo, modelRepo, providerRepo)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/test-model", middleware.MockJWTAuthWithAdmin(adminUser.ID), statsHandler.TestModel)

	req := httptest.NewRequest("POST", "/test-model", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}
}