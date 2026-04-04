package handler

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/service"
)

type UserHandler struct {
	userRepo    *repository.UserRepository
	logRepo     *repository.LogRepository
	authService *service.AuthService
}

func NewUserHandler(userRepo *repository.UserRepository, logRepo *repository.LogRepository, authService *service.AuthService) *UserHandler {
	return &UserHandler{userRepo: userRepo, logRepo: logRepo, authService: authService}
}

// ListUsers lists all users (admin only)
func (h *UserHandler) ListUsers(c *gin.Context) {
	users, err := h.userRepo.List(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, users)
}

// GetUser gets a user by ID
func (h *UserHandler) GetUser(c *gin.Context) {
	userID := parseUintParam(c.Param("id"))

	user, err := h.userRepo.FindByID(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	c.JSON(http.StatusOK, user)
}

// CreateUser creates a new user (admin only)
func (h *UserHandler) CreateUser(c *gin.Context) {
	var req struct {
		Email     string     `json:"email" binding:"required,email"`
		Password  string     `json:"password" binding:"required,min=8"`
		Role      string     `json:"role"`
		Disabled  bool       `json:"disabled"`
		ValidUntil *string   `json:"validUntil"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	role := req.Role
	if role == "" {
		role = "USER"
	}
	if role != "ADMIN" && role != "USER" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid role"})
		return
	}

	var validUntil *time.Time
	if req.ValidUntil != nil {
		t, err := time.Parse(time.RFC3339, *req.ValidUntil)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid validUntil format"})
			return
		}
		validUntil = &t
	}

	user, err := h.authService.CreateUser(c.Request.Context(), req.Email, req.Password, role, validUntil)
	if err != nil {
		if err == service.ErrUserExists {
			c.JSON(http.StatusConflict, gin.H{"error": "User already exists"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, user)
}

// UpdateUser updates a user (admin only)
func (h *UserHandler) UpdateUser(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Email     string  `json:"email"`
		Role      string  `json:"role"`
		Disabled  bool    `json:"disabled"`
		ValidUntil *string `json:"validUntil"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	user, err := h.userRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	if req.Email != "" {
		user.Email = req.Email
	}
	if req.Role != "" {
		if req.Role != "ADMIN" && req.Role != "USER" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid role"})
			return
		}
		user.Role = req.Role
	}
	user.Disabled = req.Disabled

	if req.ValidUntil != nil {
		t, err := time.Parse(time.RFC3339, *req.ValidUntil)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid validUntil format"})
			return
		}
		user.ValidUntil = &t
	}

	if err := h.userRepo.Update(c.Request.Context(), user); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, user)
}

// DeleteUser deletes a user (admin only)
func (h *UserHandler) DeleteUser(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	if err := h.userRepo.Delete(c.Request.Context(), id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "User deleted"})
}

// UpdateBalance updates a user's balance (admin only)
func (h *UserHandler) UpdateBalance(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Amount int64 `json:"amount" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.userRepo.UpdateBalance(c.Request.Context(), id, req.Amount); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Balance updated"})
}

// ToggleUserDisabled toggles user's disabled status (admin only)
func (h *UserHandler) ToggleUserDisabled(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	user, err := h.userRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	user.Disabled = !user.Disabled
	if err := h.userRepo.Update(c.Request.Context(), user); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, user)
}

// GetCurrentUser gets the current logged-in user
func (h *UserHandler) GetCurrentUser(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	user, err := h.userRepo.FindByID(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	c.JSON(http.StatusOK, user)
}

// GetUserStats gets stats for the current user
func (h *UserHandler) GetUserStats(c *gin.Context) {
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	ctx := c.Request.Context()

	// Get total token usage
	promptTokens, completionTokens, totalTokens, err := h.logRepo.GetUserTokenStats(ctx, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Get daily usage for the last 30 days
	now := time.Now()
	startDate := now.AddDate(0, 0, -30)
	dailyUsage, err := h.logRepo.GetUserDailyUsage(ctx, userID, startDate, now)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Get usage by model
	usageByModel, err := h.logRepo.GetUserModelUsage(ctx, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Build response
	dailyData := make([]gin.H, len(dailyUsage))
	for i, d := range dailyUsage {
		dailyData[i] = gin.H{
			"date":             d.Date,
			"requestCount":     d.RequestCount,
			"promptTokens":     d.PromptTokens,
			"completionTokens": d.CompletionTokens,
			"totalTokens":      d.TotalTokens,
			"cost":             d.Cost,
		}
	}

	modelData := make([]gin.H, len(usageByModel))
	for i, m := range usageByModel {
		modelData[i] = gin.H{
			"name":             m.Name,
			"requestCount":     m.RequestCount,
			"promptTokens":     m.PromptTokens,
			"completionTokens": m.CompletionTokens,
			"totalTokens":      m.TotalTokens,
			"cost":             m.Cost,
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"totalUsage": gin.H{
			"promptTokens":     promptTokens,
			"completionTokens": completionTokens,
			"totalTokens":      totalTokens,
		},
		"dailyUsage":  dailyData,
		"usageByModel": modelData,
	})
}

// parseUintParam parses a string to uint
func parseUintParam(s string) uint {
	var result uint
	for _, c := range s {
		if c >= '0' && c <= '9' {
			result = result*10 + uint(c-'0')
		}
	}
	return result
}

// Ensure models import is used
var _ = models.User{}