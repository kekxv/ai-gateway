package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/utils"
	"golang.org/x/crypto/bcrypt"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrUserDisabled       = errors.New("user is disabled")
	ErrUserExpired        = errors.New("user account has expired")
	ErrTOTPRequired       = errors.New("TOTP token required")
	ErrInvalidTOTP        = errors.New("invalid TOTP token")
	ErrUserNotFound       = errors.New("user not found")
	ErrUserExists         = errors.New("user already exists")
	ErrPasswordTooShort   = errors.New("password must be at least 8 characters")
)

type LoginRequest struct {
	Email     string `json:"email" binding:"required"`
	Password  string `json:"password" binding:"required"`
	TOTPToken string `json:"totpToken"`
}

type LoginResponse struct {
	Message string `json:"message"`
	Token   string `json:"token"`
	Role    string `json:"role"`
}

type RefreshResponse struct {
	Token string `json:"token"`
}

type ChangePasswordRequest struct {
	CurrentPassword string `json:"currentPassword" binding:"required"`
	NewPassword     string `json:"newPassword" binding:"required,min=8"`
}

type TOTPSetupResponse struct {
	Secret     string `json:"secret"`
	QRCodeData string `json:"qrCodeDataUrl"`
}

type AuthService struct {
	userRepo    *repository.UserRepository
	jwtSecret   string
	jwtExpiry   time.Duration
}

func NewAuthService(userRepo *repository.UserRepository, jwtSecret string, jwtExpiry time.Duration) *AuthService {
	return &AuthService{
		userRepo:    userRepo,
		jwtSecret:   jwtSecret,
		jwtExpiry:   jwtExpiry,
	}
}

// Login authenticates a user and returns a JWT token
func (s *AuthService) Login(ctx context.Context, req *LoginRequest) (*LoginResponse, error) {
	// Check for root user first login
	if req.Email == "root" {
		count, err := s.userRepo.Count(ctx)
		if err != nil {
			return nil, err
		}
		if count == 0 {
			// Create root admin user
			hashedPwd, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
			if err != nil {
				return nil, err
			}
			rootUser := &models.User{
				Email:    "root",
				Password: string(hashedPwd),
				Role:     "ADMIN",
			}
			if err := s.userRepo.Create(ctx, rootUser); err != nil {
				return nil, err
			}
		}
	}

	// Find user by email
	user, err := s.userRepo.FindByEmail(ctx, req.Email)
	if err != nil {
		return nil, ErrInvalidCredentials
	}

	// Verify password
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(req.Password)); err != nil {
		return nil, ErrInvalidCredentials
	}

	// Check if user is disabled
	if user.Disabled {
		return nil, ErrUserDisabled
	}

	// Check if user is expired
	if user.ValidUntil != nil && time.Now().After(*user.ValidUntil) {
		return nil, ErrUserExpired
	}

	// Check TOTP if enabled
	if user.TOTPEnabled {
		if req.TOTPToken == "" {
			return nil, ErrTOTPRequired
		}
		if !utils.ValidateTOTP(req.TOTPToken, user.TOTPSecret) {
			return nil, ErrInvalidTOTP
		}
	}

	// Generate JWT token
	token, err := utils.GenerateToken(user.ID, user.Email, user.Role, s.jwtSecret, s.jwtExpiry)
	if err != nil {
		return nil, err
	}

	return &LoginResponse{
		Message: "登录成功",
		Token:   token,
		Role:    user.Role,
	}, nil
}

// RefreshToken generates a new token for an authenticated user
func (s *AuthService) RefreshToken(ctx context.Context, userID uint) (*RefreshResponse, error) {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return nil, ErrUserNotFound
	}

	// Check if user is disabled
	if user.Disabled {
		return nil, ErrUserDisabled
	}

	// Check if user is expired
	if user.ValidUntil != nil && time.Now().After(*user.ValidUntil) {
		return nil, ErrUserExpired
	}

	// Generate new JWT token
	token, err := utils.GenerateToken(user.ID, user.Email, user.Role, s.jwtSecret, s.jwtExpiry)
	if err != nil {
		return nil, err
	}

	return &RefreshResponse{
		Token: token,
	}, nil
}

// ChangePassword changes a user's password
func (s *AuthService) ChangePassword(ctx context.Context, userID uint, req *ChangePasswordRequest) error {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return ErrUserNotFound
	}

	// Verify current password
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(req.CurrentPassword)); err != nil {
		return ErrInvalidCredentials
	}

	// Validate new password length
	if len(req.NewPassword) < 8 {
		return ErrPasswordTooShort
	}

	// Hash new password
	hashedPwd, err := bcrypt.GenerateFromPassword([]byte(req.NewPassword), bcrypt.DefaultCost)
	if err != nil {
		return err
	}

	user.Password = string(hashedPwd)
	return s.userRepo.Update(ctx, user)
}

// SetupTOTP sets up TOTP for a user
func (s *AuthService) SetupTOTP(ctx context.Context, userID uint) (*TOTPSetupResponse, error) {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return nil, ErrUserNotFound
	}

	secret, err := utils.GenerateTOTPSecret(user.Email)
	if err != nil {
		return nil, err
	}

	// Store secret temporarily (will be confirmed on verify)
	user.TOTPSecret = secret
	if err := s.userRepo.Update(ctx, user); err != nil {
		return nil, err
	}

	qrCodeData, err := utils.GenerateQRCode(secret, user.Email)
	if err != nil {
		return nil, err
	}

	return &TOTPSetupResponse{
		Secret:     secret,
		QRCodeData: qrCodeData,
	}, nil
}

// VerifyTOTP verifies and enables TOTP for a user
func (s *AuthService) VerifyTOTP(ctx context.Context, userID uint, token string) error {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return ErrUserNotFound
	}

	if user.TOTPSecret == "" {
		return errors.New("TOTP not set up")
	}

	if !utils.ValidateTOTP(token, user.TOTPSecret) {
		return ErrInvalidTOTP
	}

	user.TOTPEnabled = true
	return s.userRepo.Update(ctx, user)
}

// DisableTOTP disables TOTP for a user
func (s *AuthService) DisableTOTP(ctx context.Context, userID uint, token string) error {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return ErrUserNotFound
	}

	// Verify token before disabling
	if user.TOTPEnabled {
		if !utils.ValidateTOTP(token, user.TOTPSecret) {
			return ErrInvalidTOTP
		}
	}

	user.TOTPEnabled = false
	user.TOTPSecret = ""
	return s.userRepo.Update(ctx, user)
}

// DisableTOTPWithPassword disables TOTP for a user with password verification
func (s *AuthService) DisableTOTPWithPassword(ctx context.Context, userID uint, password, token string) error {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return ErrUserNotFound
	}

	// Verify password first
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(password)); err != nil {
		return ErrInvalidCredentials
	}

	// Verify token before disabling
	if user.TOTPEnabled {
		if !utils.ValidateTOTP(token, user.TOTPSecret) {
			return ErrInvalidTOTP
		}
	}

	user.TOTPEnabled = false
	user.TOTPSecret = ""
	return s.userRepo.Update(ctx, user)
}

// CreateUser creates a new user (admin only)
func (s *AuthService) CreateUser(ctx context.Context, email, password, role string, validUntil *time.Time) (*models.User, error) {
	// Check if user exists
	_, err := s.userRepo.FindByEmail(ctx, email)
	if err == nil {
		return nil, ErrUserExists
	}

	// Hash password
	hashedPwd, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}

	user := &models.User{
		Email:     email,
		Password:  string(hashedPwd),
		Role:      role,
		ValidUntil: validUntil,
	}

	if err := s.userRepo.Create(ctx, user); err != nil {
		return nil, err
	}

	return user, nil
}

// GenerateAPIKey generates a random API key
func GenerateAPIKey() (string, error) {
	bytes := make([]byte, 16)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}