package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/service"
	"github.com/kekxv/ai-gateway/test"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func TestAnthropicHandler_CreateMessages_MissingFields(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKey := test.CreateTestAPIKey(db, nil, func(k *models.GatewayAPIKey) {
		k.Name = "test-key"
		k.BindToAllChannels = true
	})

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := service.NewBillingService(userRepo)

	gatewayService := service.NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, nil,
	)
	anthropicHandler := NewAnthropicHandler(gatewayService)

	router := gin.New()
	router.POST("/v1/messages", middleware.APIKeyAuth(apiKeyRepo), anthropicHandler.CreateMessages)

	// Test missing model
	reqBody := map[string]interface{}{
		"max_tokens": 100,
		"messages":   []interface{}{},
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/v1/messages", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey.Key)

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing model, got %d", w.Code)
	}

	// Test missing max_tokens
	reqBody = map[string]interface{}{
		"model":   "gpt-4",
		"messages": []interface{}{},
	}
	body, _ = json.Marshal(reqBody)

	req = httptest.NewRequest("POST", "/v1/messages", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey.Key)

	w = httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing max_tokens, got %d", w.Code)
	}

	// Test missing messages
	reqBody = map[string]interface{}{
		"model":      "gpt-4",
		"max_tokens": 100,
	}
	body, _ = json.Marshal(reqBody)

	req = httptest.NewRequest("POST", "/v1/messages", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey.Key)

	w = httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing messages, got %d", w.Code)
	}
}

func TestAnthropicHandler_CreateMessages_InvalidJSON(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKey := test.CreateTestAPIKey(db, nil, func(k *models.GatewayAPIKey) {
		k.Name = "test-key"
		k.BindToAllChannels = true
	})

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := service.NewBillingService(userRepo)

	gatewayService := service.NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, nil,
	)
	anthropicHandler := NewAnthropicHandler(gatewayService)

	router := gin.New()
	router.POST("/v1/messages", middleware.APIKeyAuth(apiKeyRepo), anthropicHandler.CreateMessages)

	req := httptest.NewRequest("POST", "/v1/messages", bytes.NewReader([]byte("invalid json")))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey.Key)

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for invalid JSON, got %d", w.Code)
	}
}

func TestAnthropicHandler_CreateMessages_XAPIKeyAuth(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKey := test.CreateTestAPIKey(db, nil, func(k *models.GatewayAPIKey) {
		k.Name = "test-key"
		k.BindToAllChannels = true
	})

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := service.NewBillingService(userRepo)

	gatewayService := service.NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, nil,
	)
	anthropicHandler := NewAnthropicHandler(gatewayService)

	router := gin.New()
	router.POST("/v1/messages", middleware.APIKeyAuth(apiKeyRepo), anthropicHandler.CreateMessages)

	reqBody := models.AnthropicMessagesRequest{
		Model:     "gpt-4",
		MaxTokens: 100,
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
		},
	}
	body, _ := json.Marshal(reqBody)

	// Test with x-api-key header (Anthropic style)
	req := httptest.NewRequest("POST", "/v1/messages", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey.Key)

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Should not return 401 (authentication should pass)
	if w.Code == http.StatusUnauthorized {
		t.Error("x-api-key header should be accepted for authentication")
	}
}

func TestAnthropicHandler_CreateMessages_BearerAuth(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKey := test.CreateTestAPIKey(db, nil, func(k *models.GatewayAPIKey) {
		k.Name = "test-key"
		k.BindToAllChannels = true
	})

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := service.NewBillingService(userRepo)

	gatewayService := service.NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, nil,
	)
	anthropicHandler := NewAnthropicHandler(gatewayService)

	router := gin.New()
	router.POST("/v1/messages", middleware.APIKeyAuth(apiKeyRepo), anthropicHandler.CreateMessages)

	reqBody := models.AnthropicMessagesRequest{
		Model:     "gpt-4",
		MaxTokens: 100,
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
		},
	}
	body, _ := json.Marshal(reqBody)

	// Test with Authorization Bearer header (OpenAI style)
	req := httptest.NewRequest("POST", "/v1/messages", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey.Key)

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Should not return 401 (authentication should pass)
	if w.Code == http.StatusUnauthorized {
		t.Error("Authorization Bearer header should be accepted for authentication")
	}
}

func TestAnthropicHandler_ErrorFormat(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKey := test.CreateTestAPIKey(db, nil, func(k *models.GatewayAPIKey) {
		k.Name = "test-key"
		k.BindToAllChannels = true
	})

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := service.NewBillingService(userRepo)

	gatewayService := service.NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo,
		userRepo, logRepo, logDetailRepo, billingService, nil,
	)
	anthropicHandler := NewAnthropicHandler(gatewayService)

	router := gin.New()
	router.POST("/v1/messages", middleware.APIKeyAuth(apiKeyRepo), anthropicHandler.CreateMessages)

	// Invalid request to trigger error
	req := httptest.NewRequest("POST", "/v1/messages", bytes.NewReader([]byte("{}")))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey.Key)

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Check error response format matches Anthropic spec
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["type"] != "error" {
		t.Error("Error response should have 'type' field set to 'error'")
	}

	errorObj, ok := resp["error"].(map[string]interface{})
	if !ok {
		t.Error("Error response should have 'error' object")
	} else {
		if errorObj["type"] == nil {
			t.Error("Error object should have 'type' field")
		}
		if errorObj["message"] == nil {
			t.Error("Error object should have 'message' field")
		}
	}
}