package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

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

func TestLoginHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/login", authHandler.Login)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "loginhandler@example.com"
	})

	reqBody := service.LoginRequest{
		Email:    "loginhandler@example.com",
		Password: "password123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/login", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["token"] == "" {
		t.Error("Expected token in response")
	}
}

func TestLoginHandler_MissingFields(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/login", authHandler.Login)

	reqBody := map[string]string{
		"email": "", // missing password
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/login", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing fields, got %d", w.Code)
	}
}

func TestLoginHandler_InvalidCredentials(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/login", authHandler.Login)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "invalidcreds@example.com"
	})

	reqBody := service.LoginRequest{
		Email:    "invalidcreds@example.com",
		Password: "wrongpassword",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/login", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for invalid credentials, got %d", w.Code)
	}
}

func TestLoginHandler_UserNotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/login", authHandler.Login)

	reqBody := service.LoginRequest{
		Email:    "nonexistent@example.com",
		Password: "password123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/login", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for user not found, got %d", w.Code)
	}
}

func TestLoginHandler_DisabledUser(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/login", authHandler.Login)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "disabled@example.com"
		u.Disabled = true
	})

	reqBody := service.LoginRequest{
		Email:    "disabled@example.com",
		Password: "password123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/login", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("Expected status 403 for disabled user, got %d", w.Code)
	}
}

func TestLoginHandler_RootUserCreation(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/login", authHandler.Login)

	// No users exist - root login should create admin user
	reqBody := service.LoginRequest{
		Email:    "root",
		Password: "rootpassword",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/login", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200 for root user creation, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["role"] != "ADMIN" {
		t.Errorf("Expected role ADMIN for root user, got %v", resp["role"])
	}
}

func TestChangePasswordHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "changepass@example.com"
	})

	router := gin.New()
	router.POST("/change-password", middleware.MockJWTAuthWithUser(user.ID), authHandler.ChangePassword)

	reqBody := service.ChangePasswordRequest{
		CurrentPassword: "password123",
		NewPassword:     "newpassword123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/change-password", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestChangePasswordHandler_WrongCurrentPassword(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	user := test.CreateTestUser(db)

	router := gin.New()
	router.POST("/change-password", middleware.MockJWTAuthWithUser(user.ID), authHandler.ChangePassword)

	reqBody := service.ChangePasswordRequest{
		CurrentPassword: "wrongpassword",
		NewPassword:     "newpassword123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/change-password", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for wrong password, got %d", w.Code)
	}
}

func TestChangePasswordHandler_PasswordTooShort(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	user := test.CreateTestUser(db)

	router := gin.New()
	router.POST("/change-password", middleware.MockJWTAuthWithUser(user.ID), authHandler.ChangePassword)

	reqBody := service.ChangePasswordRequest{
		CurrentPassword: "password123",
		NewPassword:     "short",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/change-password", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for short password, got %d", w.Code)
	}
}

func TestSetupTOTPHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	user := test.CreateTestUser(db)

	router := gin.New()
	router.POST("/setup-totp", middleware.MockJWTAuthWithUser(user.ID), authHandler.SetupTOTP)

	req := httptest.NewRequest("POST", "/setup-totp", nil)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["secret"] == "" {
		t.Error("Expected secret in response")
	}
}

func TestChangePasswordHandler_Unauthorized(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	authHandler := NewAuthHandler(authService)

	router := gin.New()
	router.POST("/change-password", middleware.MockJWTAuth(), authHandler.ChangePassword)

	reqBody := service.ChangePasswordRequest{
		CurrentPassword: "password123",
		NewPassword:     "newpassword123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/change-password", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for unauthorized, got %d", w.Code)
	}
}