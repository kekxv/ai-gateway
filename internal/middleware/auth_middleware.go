package middleware

import (
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

func JWTAuth(jwtSecret string) gin.HandlerFunc {
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

		tokenString := parts[1]
		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			return []byte(jwtSecret), nil
		})

		if err != nil || !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: Invalid token"})
			c.Abort()
			return
		}

		claims, ok := token.Claims.(jwt.MapClaims)
		if !ok {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: Invalid token claims"})
			c.Abort()
			return
		}

		// Check token expiration
		if exp, ok := claims["exp"].(float64); ok {
			if time.Now().Unix() > int64(exp) {
				c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: Token expired"})
				c.Abort()
				return
			}
		}

		// Store user info in context
		c.Set("userId", uint(claims["userId"].(float64)))
		c.Set("email", claims["email"].(string))
		c.Set("role", claims["role"].(string))

		c.Next()
	}
}

func RequireRole(role string) gin.HandlerFunc {
	return func(c *gin.Context) {
		userRole, exists := c.Get("role")
		if !exists {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized: No role found"})
			c.Abort()
			return
		}

		if userRole != role && userRole != "ADMIN" {
			c.JSON(http.StatusForbidden, gin.H{"error": "Forbidden: Insufficient permissions"})
			c.Abort()
			return
		}

		c.Next()
	}
}

func GetUserID(c *gin.Context) uint {
	if userID, exists := c.Get("userId"); exists {
		return userID.(uint)
	}
	return 0
}

func GetUserRole(c *gin.Context) string {
	if role, exists := c.Get("role"); exists {
		return role.(string)
	}
	return ""
}

// CurrentUser represents the current authenticated user
type CurrentUser struct {
	ID    uint
	Email string
	Role  string
}

// GetCurrentUser gets the current user info from context
func GetCurrentUser(c *gin.Context) *CurrentUser {
	userID, exists := c.Get("userId")
	if !exists {
		return nil
	}
	email, _ := c.Get("email")
	role, _ := c.Get("role")

	return &CurrentUser{
		ID:    userID.(uint),
		Email: email.(string),
		Role:  role.(string),
	}
}

// MockJWTAuth creates a mock JWT auth middleware for testing (no user)
func MockJWTAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Don't set any user info - simulates missing auth
		c.Next()
	}
}

// MockJWTAuthWithUser creates a mock JWT auth middleware with a specific user ID
func MockJWTAuthWithUser(userID uint) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Set("userId", userID)
		c.Set("email", "test@example.com")
		c.Set("role", "USER")
		c.Next()
	}
}

// MockJWTAuthWithAdmin creates a mock JWT auth middleware with admin role
func MockJWTAuthWithAdmin(userID uint) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Set("userId", userID)
		c.Set("email", "admin@example.com")
		c.Set("role", "ADMIN")
		c.Next()
	}
}