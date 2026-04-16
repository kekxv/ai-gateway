package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/service"
)

type AuthHandler struct {
	authService *service.AuthService
}

func NewAuthHandler(authService *service.AuthService) *AuthHandler {
	return &AuthHandler{authService: authService}
}

// Login handles user login
func (h *AuthHandler) Login(c *gin.Context) {
	var req service.LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.authService.Login(c.Request.Context(), &req)
	if err != nil {
		switch err {
		case service.ErrInvalidCredentials:
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid credentials"})
		case service.ErrUserDisabled:
			c.JSON(http.StatusForbidden, gin.H{"error": "User is disabled"})
		case service.ErrUserExpired:
			c.JSON(http.StatusForbidden, gin.H{"error": "User account has expired"})
		case service.ErrTOTPRequired:
			c.JSON(http.StatusBadRequest, gin.H{"error": "TOTP token required"})
		case service.ErrInvalidTOTP:
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid TOTP token"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, resp)
}

// RefreshToken handles token refresh
func (h *AuthHandler) RefreshToken(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	resp, err := h.authService.RefreshToken(c.Request.Context(), userID)
	if err != nil {
		switch err {
		case service.ErrUserNotFound:
			c.JSON(http.StatusUnauthorized, gin.H{"error": "User not found"})
		case service.ErrUserDisabled:
			c.JSON(http.StatusForbidden, gin.H{"error": "User is disabled"})
		case service.ErrUserExpired:
			c.JSON(http.StatusForbidden, gin.H{"error": "User account has expired"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, resp)
}

// ChangePassword handles password change
func (h *AuthHandler) ChangePassword(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	var req service.ChangePasswordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.authService.ChangePassword(c.Request.Context(), userID, &req); err != nil {
		switch err {
		case service.ErrInvalidCredentials:
			c.JSON(http.StatusBadRequest, gin.H{"error": "Current password is incorrect"})
		case service.ErrPasswordTooShort:
			c.JSON(http.StatusBadRequest, gin.H{"error": "New password must be at least 8 characters"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Password changed successfully"})
}

// SetupTOTP handles TOTP setup
func (h *AuthHandler) SetupTOTP(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	resp, err := h.authService.SetupTOTP(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}

// VerifyTOTP handles TOTP verification
func (h *AuthHandler) VerifyTOTP(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	var req struct {
		Token string `json:"token" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.authService.VerifyTOTP(c.Request.Context(), userID, req.Token); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "TOTP enabled successfully"})
}

// DisableTOTP handles TOTP disable
func (h *AuthHandler) DisableTOTP(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	var req struct {
		Password string `json:"password" binding:"required"`
		Token    string `json:"token" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.authService.DisableTOTPWithPassword(c.Request.Context(), userID, req.Password, req.Token); err != nil {
		switch err {
		case service.ErrInvalidCredentials:
			c.JSON(http.StatusBadRequest, gin.H{"error": "密码错误"})
		case service.ErrInvalidTOTP:
			c.JSON(http.StatusBadRequest, gin.H{"error": "验证码错误"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "TOTP disabled successfully"})
}