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
	"github.com/kekxv/ai-gateway/test"
)

func TestListProvidersHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	// Create test providers
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider1" })
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider2" })

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/providers", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.ListProviders)

	req := httptest.NewRequest("GET", "/providers", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp []interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if len(resp) < 2 {
		t.Errorf("Expected at least 2 providers, got %d", len(resp))
	}
}

func TestCreateProviderHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/providers", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.CreateProvider)

	reqBody := map[string]interface{}{
		"name":     "openai",
		"baseURL":  "https://api.openai.com",
		"apiKey":   "test-key",
		"type":     "openai",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/providers", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d: %s", w.Code, w.Body.String())
	}
}

func TestCreateProviderHandler_MissingName(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/providers", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.CreateProvider)

	reqBody := map[string]interface{}{
		"baseURL": "https://api.openai.com",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/providers", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing name, got %d", w.Code)
	}
}

func TestGetProviderHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "test-provider"
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/providers/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.GetProvider)

	req := httptest.NewRequest("GET", "/providers/1", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["name"] != "test-provider" {
		t.Errorf("Expected name 'test-provider', got %v", resp["name"])
	}
}

func TestGetProviderHandler_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/providers/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.GetProvider)

	req := httptest.NewRequest("GET", "/providers/999", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status 404 for non-existent provider, got %d", w.Code)
	}
}

func TestUpdateProviderHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "original-name"
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.PUT("/providers/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.UpdateProvider)

	reqBody := map[string]interface{}{
		"name": "updated-name",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("PUT", "/providers/1", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestDeleteProviderHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	providerRepo := repository.NewProviderRepository(db)
	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	providerHandler := NewProviderHandler(providerRepo, modelRepo, modelRouteRepo)

	test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "to-delete"
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.DELETE("/providers/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), providerHandler.DeleteProvider)

	req := httptest.NewRequest("DELETE", "/providers/1", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}