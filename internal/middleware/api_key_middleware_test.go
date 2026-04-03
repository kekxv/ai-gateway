package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/test"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func TestAPIKeyAuth_MissingHeader(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)

	router := gin.New()
	router.Use(APIKeyAuth(apiKeyRepo))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for missing header, got %d", w.Code)
	}
}

func TestAPIKeyAuth_InvalidKey(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)

	router := gin.New()
	router.Use(APIKeyAuth(apiKeyRepo))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer invalid-key")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for invalid key, got %d", w.Code)
	}
}

func TestAPIKeyAuth_DisabledKey(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	disabledKey := uuid.New().String()
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Key = disabledKey
		k.Enabled = false
	})

	router := gin.New()
	router.Use(APIKeyAuth(apiKeyRepo))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+disabledKey)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for disabled key, got %d", w.Code)
	}
}

func TestAPIKeyAuth_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	validKey := uuid.New().String()
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Key = validKey
		k.Enabled = true
	})

	router := gin.New()
	router.Use(APIKeyAuth(apiKeyRepo))
	router.GET("/test", func(c *gin.Context) {
		apiKey := GetAPIKey(c)
		if apiKey != nil {
			c.JSON(http.StatusOK, gin.H{"apiKeyId": apiKey.ID})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "API key not found in context"})
		}
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+validKey)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200 for valid key, got %d: %s", w.Code, w.Body.String())
	}
}

func TestAPIKeyAuth_ExtractsKeyInfo(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	validKey := uuid.New().String()
	apiKey := test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Key = validKey
		k.Enabled = true
		k.Name = "Test Key Name"
	})

	router := gin.New()
	router.Use(APIKeyAuth(apiKeyRepo))
	router.GET("/test", func(c *gin.Context) {
		key := GetAPIKey(c)
		c.JSON(http.StatusOK, gin.H{
			"apiKeyId":   key.ID,
			"apiKeyName": key.Name,
			"userId":     key.UserID,
		})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+validKey)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", w.Code)
	}

	// Verify key info is correct
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["apiKeyId"] != float64(apiKey.ID) {
		t.Errorf("Expected apiKeyId %d, got %v", apiKey.ID, resp["apiKeyId"])
	}

	if resp["apiKeyName"] != "Test Key Name" {
		t.Errorf("Expected apiKeyName 'Test Key Name', got %v", resp["apiKeyName"])
	}
}

func TestAPIKeyAuth_WrongFormat(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	apiKeyRepo := repository.NewAPIKeyRepository(db)

	router := gin.New()
	router.Use(APIKeyAuth(apiKeyRepo))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Basic somekey") // Wrong format
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for wrong auth format, got %d", w.Code)
	}
}

func TestGetAPIKey_NotSet(t *testing.T) {
	router := gin.New()
	router.GET("/test", func(c *gin.Context) {
		key := GetAPIKey(c)
		if key == nil {
			c.JSON(http.StatusOK, gin.H{"apiKey": nil})
		} else {
			c.JSON(http.StatusOK, gin.H{"apiKey": key.ID})
		}
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["apiKey"] != nil {
		t.Errorf("Expected nil apiKey when not set, got %v", resp["apiKey"])
	}
}