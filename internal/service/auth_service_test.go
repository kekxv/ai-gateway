package service

import (
	"context"
	"testing"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/test"
	"golang.org/x/crypto/bcrypt"
)

func TestAuthService_Login_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	// Create a test user
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "login@example.com"
	})

	req := &LoginRequest{
		Email:    "login@example.com",
		Password: "password123",
	}

	resp, err := authService.Login(context.Background(), req)
	if err != nil {
		t.Fatalf("Login failed: %v", err)
	}

	if resp.Message != "登录成功" {
		t.Errorf("Expected message '登录成功', got '%s'", resp.Message)
	}

	if resp.Token == "" {
		t.Error("Expected token to be returned")
	}

	if resp.Role != "USER" {
		t.Errorf("Expected role 'USER', got '%s'", resp.Role)
	}
}

func TestAuthService_Login_InvalidCredentials(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "wrongpass@example.com"
	})

	req := &LoginRequest{
		Email:    "wrongpass@example.com",
		Password: "wrongpassword",
	}

	_, err := authService.Login(context.Background(), req)
	if err != ErrInvalidCredentials {
		t.Errorf("Expected ErrInvalidCredentials, got %v", err)
	}
}

func TestAuthService_Login_UserNotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	req := &LoginRequest{
		Email:    "nonexistent@example.com",
		Password: "password123",
	}

	_, err := authService.Login(context.Background(), req)
	if err != ErrInvalidCredentials {
		t.Errorf("Expected ErrInvalidCredentials, got %v", err)
	}
}

func TestAuthService_Login_UserDisabled(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "disabled@example.com"
		u.Disabled = true
	})

	req := &LoginRequest{
		Email:    "disabled@example.com",
		Password: "password123",
	}

	_, err := authService.Login(context.Background(), req)
	if err != ErrUserDisabled {
		t.Errorf("Expected ErrUserDisabled, got %v", err)
	}
}

func TestAuthService_Login_UserExpired(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	pastTime := time.Now().Add(-24 * time.Hour)
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "expired@example.com"
		u.ValidUntil = &pastTime
	})

	req := &LoginRequest{
		Email:    "expired@example.com",
		Password: "password123",
	}

	_, err := authService.Login(context.Background(), req)
	if err != ErrUserExpired {
		t.Errorf("Expected ErrUserExpired, got %v", err)
	}
}

func TestAuthService_Login_TOTPRequired(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "totp@example.com"
		u.TOTPEnabled = true
		u.TOTPSecret = "JBSWY3DPEHPK3PXP"
	})

	req := &LoginRequest{
		Email:    "totp@example.com",
		Password: "password123",
	}

	_, err := authService.Login(context.Background(), req)
	if err != ErrTOTPRequired {
		t.Errorf("Expected ErrTOTPRequired, got %v", err)
	}
}

func TestAuthService_Login_RootUserCreation(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	// No users exist yet
	req := &LoginRequest{
		Email:    "root",
		Password: "rootpassword",
	}

	resp, err := authService.Login(context.Background(), req)
	if err != nil {
		t.Fatalf("Login failed: %v", err)
	}

	if resp.Role != "ADMIN" {
		t.Errorf("Expected role 'ADMIN', got '%s'", resp.Role)
	}

	// Verify user was created
	user, _ := userRepo.FindByEmail(context.Background(), "root")
	if user == nil {
		t.Error("Root user was not created")
	}
}

func TestAuthService_ChangePassword_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "changepass@example.com"
	})

	req := &ChangePasswordRequest{
		CurrentPassword: "password123",
		NewPassword:     "newpassword123",
	}

	err := authService.ChangePassword(context.Background(), user.ID, req)
	if err != nil {
		t.Fatalf("ChangePassword failed: %v", err)
	}

	// Verify new password works
	updatedUser, _ := userRepo.FindByID(context.Background(), user.ID)
	if bcrypt.CompareHashAndPassword([]byte(updatedUser.Password), []byte("newpassword123")) != nil {
		t.Error("Password was not updated correctly")
	}
}

func TestAuthService_ChangePassword_WrongCurrentPassword(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	user := test.CreateTestUser(db)

	req := &ChangePasswordRequest{
		CurrentPassword: "wrongpassword",
		NewPassword:     "newpassword123",
	}

	err := authService.ChangePassword(context.Background(), user.ID, req)
	if err != ErrInvalidCredentials {
		t.Errorf("Expected ErrInvalidCredentials, got %v", err)
	}
}

func TestAuthService_ChangePassword_PasswordTooShort(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	user := test.CreateTestUser(db)

	req := &ChangePasswordRequest{
		CurrentPassword: "password123",
		NewPassword:     "short",
	}

	err := authService.ChangePassword(context.Background(), user.ID, req)
	if err != ErrPasswordTooShort {
		t.Errorf("Expected ErrPasswordTooShort, got %v", err)
	}
}

func TestAuthService_CreateUser_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	user, err := authService.CreateUser(context.Background(), "newuser@example.com", "password123", "USER", nil)
	if err != nil {
		t.Fatalf("CreateUser failed: %v", err)
	}

	if user.Email != "newuser@example.com" {
		t.Errorf("Expected email 'newuser@example.com', got '%s'", user.Email)
	}

	if user.Role != "USER" {
		t.Errorf("Expected role 'USER', got '%s'", user.Role)
	}
}

func TestAuthService_CreateUser_UserExists(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "existing@example.com"
	})

	_, err := authService.CreateUser(context.Background(), "existing@example.com", "password123", "USER", nil)
	if err != ErrUserExists {
		t.Errorf("Expected ErrUserExists, got %v", err)
	}
}

func TestAuthService_SetupTOTP_Success(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	authService := NewAuthService(userRepo, "test-secret", 8*time.Hour)

	user := test.CreateTestUser(db)

	resp, err := authService.SetupTOTP(context.Background(), user.ID)
	if err != nil {
		t.Fatalf("SetupTOTP failed: %v", err)
	}

	if resp.Secret == "" {
		t.Error("Expected secret to be returned")
	}

	if resp.QRCodeData == "" {
		t.Error("Expected QR code data URL to be returned")
	}
}