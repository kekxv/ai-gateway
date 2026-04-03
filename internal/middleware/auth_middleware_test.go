package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

func init() {
	gin.SetMode(gin.TestMode)
}

const testJWTSecret = "test-secret-key"

func generateTestToken(userID uint, email, role string, exp time.Time) string {
	claims := jwt.MapClaims{
		"userId": userID,
		"email":  email,
		"role":   role,
		"exp":    exp.Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, _ := token.SignedString([]byte(testJWTSecret))
	return tokenString
}

func TestJWTAuth_MissingHeader(t *testing.T) {
	router := gin.New()
	router.Use(JWTAuth(testJWTSecret))
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

func TestJWTAuth_InvalidFormat(t *testing.T) {
	router := gin.New()
	router.Use(JWTAuth(testJWTSecret))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "InvalidFormat")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for invalid format, got %d", w.Code)
	}
}

func TestJWTAuth_InvalidToken(t *testing.T) {
	router := gin.New()
	router.Use(JWTAuth(testJWTSecret))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer invalidtoken")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for invalid token, got %d", w.Code)
	}
}

func TestJWTAuth_ExpiredToken(t *testing.T) {
	router := gin.New()
	router.Use(JWTAuth(testJWTSecret))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	// Token expired 1 hour ago
	expiredToken := generateTestToken(1, "test@example.com", "USER", time.Now().Add(-1*time.Hour))

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+expiredToken)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for expired token, got %d", w.Code)
	}
}

func TestJWTAuth_Success(t *testing.T) {
	router := gin.New()
	router.Use(JWTAuth(testJWTSecret))
	router.GET("/test", func(c *gin.Context) {
		userID := GetUserID(c)
		c.JSON(http.StatusOK, gin.H{"userId": userID})
	})

	// Valid token
	validToken := generateTestToken(123, "test@example.com", "USER", time.Now().Add(1*time.Hour))

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+validToken)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200 for valid token, got %d", w.Code)
	}
}

func TestJWTAuth_ExtractsUserID(t *testing.T) {
	router := gin.New()
	router.Use(JWTAuth(testJWTSecret))
	router.GET("/test", func(c *gin.Context) {
		userID := GetUserID(c)
		email, _ := c.Get("email")
		role, _ := c.Get("role")
		c.JSON(http.StatusOK, gin.H{
			"userId": userID,
			"email":  email,
			"role":   role,
		})
	})

	validToken := generateTestToken(456, "extract@example.com", "ADMIN", time.Now().Add(1*time.Hour))

	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+validToken)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if resp["userId"] != float64(456) {
		t.Errorf("Expected userId 456, got %v", resp["userId"])
	}

	if resp["email"] != "extract@example.com" {
		t.Errorf("Expected email 'extract@example.com', got %v", resp["email"])
	}

	if resp["role"] != "ADMIN" {
		t.Errorf("Expected role 'ADMIN', got %v", resp["role"])
	}
}

func TestRequireRole_AdminRole(t *testing.T) {
	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set("role", "ADMIN")
		c.Next()
	})
	router.Use(RequireRole("ADMIN"))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200 for admin role, got %d", w.Code)
	}
}

func TestRequireRole_AdminCanAccessAny(t *testing.T) {
	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set("role", "ADMIN")
		c.Next()
	})
	router.Use(RequireRole("USER")) // Require USER role
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	// Admin should be able to access even if USER role is required
	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200 for admin accessing USER endpoint, got %d", w.Code)
	}
}

func TestRequireRole_InsufficientRole(t *testing.T) {
	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set("role", "USER")
		c.Next()
	})
	router.Use(RequireRole("ADMIN"))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("Expected status 403 for insufficient role, got %d", w.Code)
	}
}

func TestRequireRole_NoRoleSet(t *testing.T) {
	router := gin.New()
	// Don't set any role
	router.Use(RequireRole("ADMIN"))
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "success"})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for no role set, got %d", w.Code)
	}
}

func TestGetUserID_NotSet(t *testing.T) {
	router := gin.New()
	router.GET("/test", func(c *gin.Context) {
		userID := GetUserID(c)
		c.JSON(http.StatusOK, gin.H{"userId": userID})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["userId"] != float64(0) {
		t.Errorf("Expected userId 0 when not set, got %v", resp["userId"])
	}
}

func TestGetUserRole_NotSet(t *testing.T) {
	router := gin.New()
	router.GET("/test", func(c *gin.Context) {
		role := GetUserRole(c)
		c.JSON(http.StatusOK, gin.H{"role": role})
	})

	req := httptest.NewRequest("GET", "/test", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["role"] != "" {
		t.Errorf("Expected empty role when not set, got %v", resp["role"])
	}
}