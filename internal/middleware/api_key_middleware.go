package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
)

func APIKeyAuth(apiKeyRepo *repository.APIKeyRepository) gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: Missing Authorization header"})
			c.Abort()
			return
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: Invalid Authorization header format"})
			c.Abort()
			return
		}

		apiKey := parts[1]
		keyData, err := apiKeyRepo.FindByKey(c.Request.Context(), apiKey)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: Invalid API Key"})
			c.Abort()
			return
		}

		if !keyData.Enabled {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: API Key is disabled"})
			c.Abort()
			return
		}

		// Update lastUsed asynchronously
		go func() {
			ctx := context.Background()
			apiKeyRepo.UpdateLastUsed(ctx, keyData.ID)
		}()

		// Store API key info in context
		c.Set("apiKey", keyData)
		c.Set("apiKeyId", keyData.ID)
		c.Set("userId", keyData.UserID)

		c.Next()
	}
}

func GetAPIKey(c *gin.Context) *models.GatewayAPIKey {
	if apiKey, exists := c.Get("apiKey"); exists {
		return apiKey.(*models.GatewayAPIKey)
	}
	return nil
}