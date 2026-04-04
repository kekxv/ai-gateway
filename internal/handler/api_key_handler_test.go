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
	"golang.org/x/crypto/bcrypt"
)

func TestListAPIKeysHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)
	authService := service.NewAuthService(repository.NewUserRepository(db), "test-secret", 0)
	apiKeyHandler := NewAPIKeyHandler(apiKeyRepo, authService)

	user := test.CreateTestUser(db)
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) { k.Name = "key1" })
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) { k.Name = "key2" })

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/keys", middleware.MockJWTAuthWithAdmin(adminUser.ID), apiKeyHandler.ListAPIKeys)

	req := httptest.NewRequest("GET", "/keys", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp []interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if len(resp) < 2 {
		t.Errorf("Expected at least 2 API keys, got %d", len(resp))
	}
}

func TestCreateAPIKeyHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)
	authService := service.NewAuthService(repository.NewUserRepository(db), "test-secret", 0)
	apiKeyHandler := NewAPIKeyHandler(apiKeyRepo, authService)

	_ = test.CreateTestUser(db)
	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/keys", middleware.MockJWTAuthWithAdmin(adminUser.ID), apiKeyHandler.CreateAPIKey)

	reqBody := map[string]interface{}{
		"name":              "test-key",
		"enabled":           true,
		"bind_to_all":       true,
		"log_details":       true,
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/keys", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d: %s", w.Code, w.Body.String())
	}
}

func TestCreateAPIKeyHandler_MissingName(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)
	authService := service.NewAuthService(repository.NewUserRepository(db), "test-secret", 0)
	apiKeyHandler := NewAPIKeyHandler(apiKeyRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/keys", middleware.MockJWTAuthWithAdmin(adminUser.ID), apiKeyHandler.CreateAPIKey)

	reqBody := map[string]interface{}{
		"enabled": true,
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/keys", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing name, got %d", w.Code)
	}
}

func TestUpdateAPIKeyHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)
	authService := service.NewAuthService(repository.NewUserRepository(db), "test-secret", 0)
	apiKeyHandler := NewAPIKeyHandler(apiKeyRepo, authService)

	user := test.CreateTestUser(db)
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Name = "original-name"
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.PUT("/keys/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), apiKeyHandler.UpdateAPIKey)

	reqBody := map[string]interface{}{
		"name":    "updated-name",
		"enabled": true,
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("PUT", "/keys/1", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestDeleteAPIKeyHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)
	authService := service.NewAuthService(repository.NewUserRepository(db), "test-secret", 0)
	apiKeyHandler := NewAPIKeyHandler(apiKeyRepo, authService)

	user := test.CreateTestUser(db)
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Name = "to-delete"
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.DELETE("/keys/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), apiKeyHandler.DeleteAPIKey)

	req := httptest.NewRequest("DELETE", "/keys/1", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGetAPIKeyHandler_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)
	authService := service.NewAuthService(repository.NewUserRepository(db), "test-secret", 0)
	apiKeyHandler := NewAPIKeyHandler(apiKeyRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.PUT("/keys/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), apiKeyHandler.UpdateAPIKey)

	reqBody := map[string]interface{}{
		"name": "test",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("PUT", "/keys/999", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status 404 for non-existent key, got %d", w.Code)
	}
}

func TestAPIKeyAuth_PasswordVerification(t *testing.T) {
	// Test that bcrypt password hashing works correctly
	password := "testpassword123"
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		t.Fatalf("Failed to hash password: %v", err)
	}

	// Verify correct password
	err = bcrypt.CompareHashAndPassword(hashedPassword, []byte(password))
	if err != nil {
		t.Errorf("Failed to verify correct password: %v", err)
	}

	// Verify incorrect password
	err = bcrypt.CompareHashAndPassword(hashedPassword, []byte("wrongpassword"))
	if err == nil {
		t.Error("Expected error for incorrect password, got nil")
	}
}