package utils

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestGenerateAndParseToken(t *testing.T) {
	secret := "test-secret-key"
	userID := uint(123)
	email := "test@example.com"
	role := "ADMIN"
	expiry := 8 * time.Hour

	token, err := GenerateToken(userID, email, role, secret, expiry)
	if err != nil {
		t.Fatalf("GenerateToken failed: %v", err)
	}

	if token == "" {
		t.Fatal("Token is empty")
	}

	claims, err := ParseToken(token, secret)
	if err != nil {
		t.Fatalf("ParseToken failed: %v", err)
	}

	if claims.UserID != userID {
		t.Errorf("Expected UserID %d, got %d", userID, claims.UserID)
	}

	if claims.Email != email {
		t.Errorf("Expected Email %s, got %s", email, claims.Email)
	}

	if claims.Role != role {
		t.Errorf("Expected Role %s, got %s", role, claims.Role)
	}
}

func TestParseTokenInvalid(t *testing.T) {
	secret := "test-secret-key"

	// Test with invalid token
	_, err := ParseToken("invalid-token", secret)
	if err == nil {
		t.Error("Expected error for invalid token, got nil")
	}

	// Test with wrong secret
	token, _ := GenerateToken(1, "test@example.com", "USER", "correct-secret", 8*time.Hour)
	_, err = ParseToken(token, secret)
	if err == nil {
		t.Error("Expected error for wrong secret, got nil")
	}
}

func TestTokenExpiry(t *testing.T) {
	secret := "test-secret-key"

	// Create token that's already expired
	claims := &JWTClaims{
		UserID: 1,
		Email:  "test@example.com",
		Role:   "USER",
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-1 * time.Hour)),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, _ := token.SignedString([]byte(secret))

	_, err := ParseToken(tokenString, secret)
	if err == nil {
		t.Error("Expected error for expired token, got nil")
	}
}