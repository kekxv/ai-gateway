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
		var apiKey string

		// Method 1: Check x-api-key header (Anthropic style)
		xAPIKey := c.GetHeader("x-api-key")
		if xAPIKey != "" {
			apiKey = xAPIKey
		}

		// Method 2: Check Authorization header (OpenAI style)
		if apiKey == "" {
			authHeader := c.GetHeader("Authorization")
			if authHeader != "" {
				parts := strings.Split(authHeader, " ")
				if len(parts) == 2 && parts[0] == "Bearer" {
					apiKey = parts[1]
				}
			}
		}

		if apiKey == "" {
			c.JSON(http.StatusUnauthorized, gin.H{
				"type": "error",
				"error": gin.H{
					"type":    "authentication_error",
					"message": "Missing API key. Use x-api-key header or Authorization: Bearer <key>",
				},
			})
			c.Abort()
			return
		}

		keyData, err := apiKeyRepo.FindByKey(c.Request.Context(), apiKey)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{
				"type": "error",
				"error": gin.H{
					"type":    "authentication_error",
					"message": "Invalid API key",
				},
			})
			c.Abort()
			return
		}

		if !keyData.Enabled {
			c.JSON(http.StatusUnauthorized, gin.H{
				"type": "error",
				"error": gin.H{
					"type":    "authentication_error",
					"message": "API key is disabled",
				},
			})
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