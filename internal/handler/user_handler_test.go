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

func TestListUsersHandler_AdminAccess(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	// Create test users
	test.CreateTestUser(db, func(u *models.User) { u.Email = "user1@example.com" })
	test.CreateTestUser(db, func(u *models.User) { u.Email = "user2@example.com" })

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/users", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.ListUsers)

	req := httptest.NewRequest("GET", "/users", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp []interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if len(resp) < 2 {
		t.Errorf("Expected at least 2 users, got %d", len(resp))
	}
}

func TestGetUserHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "getuser@example.com"
	})

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/users/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.GetUser)

	req := httptest.NewRequest("GET", "/users/"+string(rune(user.ID+'0')), nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGetUserHandler_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.GET("/users/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.GetUser)

	req := httptest.NewRequest("GET", "/users/999", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status 404 for non-existent user, got %d", w.Code)
	}
}

func TestCreateUserHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/users", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.CreateUser)

	reqBody := map[string]interface{}{
		"email":    "newuser@example.com",
		"password": "password123",
		"role":     "USER",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/users", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d: %s", w.Code, w.Body.String())
	}
}

func TestCreateUserHandler_MissingFields(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/users", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.CreateUser)

	reqBody := map[string]interface{}{
		"email": "missingpassword@example.com",
		// missing password
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/users", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for missing fields, got %d", w.Code)
	}
}

func TestCreateUserHandler_ValidationError(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/users", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.CreateUser)

	reqBody := map[string]interface{}{
		"email":    "invalid-email",
		"password": "password123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/users", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for invalid email, got %d", w.Code)
	}
}

func TestCreateUserHandler_PasswordTooShort(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.POST("/users", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.CreateUser)

	reqBody := map[string]interface{}{
		"email":    "shortpass@example.com",
		"password": "short",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/users", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400 for short password, got %d", w.Code)
	}
}

func TestCreateUserHandler_UserAlreadyExists(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	// Create existing user
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "existing@example.com"
	})

	router := gin.New()
	router.POST("/users", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.CreateUser)

	reqBody := map[string]interface{}{
		"email":    "existing@example.com",
		"password": "password123",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("POST", "/users", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusConflict {
		t.Errorf("Expected status 409 for existing user, got %d", w.Code)
	}
}

func TestUpdateUserHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	_ = test.CreateTestUser(db, func(u *models.User) {
		u.Email = "updateuser@example.com"
	})
	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.PUT("/users/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.UpdateUser)

	reqBody := map[string]interface{}{
		"email": "updated@example.com",
		"role":  "USER",
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("PUT", "/users/1", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestDeleteUserHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	_ = test.CreateTestUser(db, func(u *models.User) {
		u.Email = "deleteuser@example.com"
	})
	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.DELETE("/users/:id", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.DeleteUser)

	req := httptest.NewRequest("DELETE", "/users/1", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestUpdateBalanceHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	_ = test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 100
	})
	adminUser := test.CreateTestAdmin(db, "admin@example.com")

	router := gin.New()
	router.PUT("/users/:id/balance", middleware.MockJWTAuthWithAdmin(adminUser.ID), userHandler.UpdateBalance)

	reqBody := map[string]interface{}{
		"amount": 500,
	}
	body, _ := json.Marshal(reqBody)

	req := httptest.NewRequest("PUT", "/users/1/balance", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestGetCurrentUserHandler_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "currentuser@example.com"
	})

	router := gin.New()
	router.GET("/me", middleware.MockJWTAuthWithUser(user.ID), userHandler.GetCurrentUser)

	req := httptest.NewRequest("GET", "/me", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp["email"] != "currentuser@example.com" {
		t.Errorf("Expected email 'currentuser@example.com', got %v", resp["email"])
	}
}

func TestGetCurrentUserHandler_Unauthorized(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	authService := service.NewAuthService(userRepo, "test-secret-key", 8*time.Hour)
	userHandler := NewUserHandler(userRepo, logRepo, authService)

	router := gin.New()
	router.GET("/me", middleware.MockJWTAuth(), userHandler.GetCurrentUser)

	req := httptest.NewRequest("GET", "/me", nil)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status 401 for unauthorized, got %d", w.Code)
	}
}