package utils

import (
	"crypto/rand"
	"encoding/base32"
	"encoding/base64"
	"fmt"
	"strings"

	"github.com/pquerna/otp/totp"
	"github.com/skip2/go-qrcode"
)

// GenerateTOTPSecret generates a new TOTP secret
func GenerateTOTPSecret(email string) (string, error) {
	key, err := totp.Generate(totp.GenerateOpts{
		Issuer:      "AI-Gateway",
		AccountName: email,
		SecretSize:  32,
	})
	if err != nil {
		return "", err
	}
	return key.Secret(), nil
}

// ValidateTOTP validates a TOTP code against the secret
func ValidateTOTP(code, secret string) bool {
	return totp.Validate(code, secret)
}

// GenerateQRCode generates a QR code image as base64 data URL
func GenerateQRCode(secret, email string) (string, error) {
	url := fmt.Sprintf("otpauth://totp/AI-Gateway:%s?secret=%s&issuer=AI-Gateway", email, secret)

	png, err := qrcode.Encode(url, qrcode.Medium, 256)
	if err != nil {
		return "", err
	}

	base64Img := base64.StdEncoding.EncodeToString(png)
	return "data:image/png;base64," + base64Img, nil
}

// GenerateRandomSecret generates a random secret for JWT or other purposes
func GenerateRandomSecret(length int) (string, error) {
	bytes := make([]byte, length)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return strings.ToUpper(base32.StdEncoding.EncodeToString(bytes))[:length], nil
}