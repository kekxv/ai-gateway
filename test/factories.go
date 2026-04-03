package test

import (
	"time"

	"github.com/google/uuid"
	"github.com/kekxv/ai-gateway/internal/models"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

// CreateTestUser creates a test user with default values
func CreateTestUser(db *gorm.DB, overrides ...func(*models.User)) *models.User {
	hashedPassword, _ := bcrypt.GenerateFromPassword([]byte("password123"), bcrypt.DefaultCost)

	user := &models.User{
		Email:       "test@example.com",
		Password:    string(hashedPassword),
		Role:        "USER",
		Disabled:    false,
		Balance:     1000,
		TOTPEnabled: false,
		CreatedAt:   time.Now(),
	}

	for _, override := range overrides {
		override(user)
	}

	db.Create(user)
	return user
}

// CreateTestAdmin creates a test admin user
func CreateTestAdmin(db *gorm.DB, email string) *models.User {
	return CreateTestUser(db, func(u *models.User) {
		u.Email = email
		u.Role = "ADMIN"
	})
}

// CreateTestProvider creates a test provider
func CreateTestProvider(db *gorm.DB, overrides ...func(*models.Provider)) *models.Provider {
	provider := &models.Provider{
		Name:          "Test Provider",
		BaseURL:       "https://api.example.com",
		APIKey:        "test-api-key",
		Type:          "openai",
		AutoLoadModels: false,
		Disabled:      false,
		CreatedAt:     time.Now(),
	}

	for _, override := range overrides {
		override(provider)
	}

	db.Create(provider)
	return provider
}

// CreateTestModel creates a test model
func CreateTestModel(db *gorm.DB, overrides ...func(*models.Model)) *models.Model {
	model := &models.Model{
		Name:             "gpt-4",
		Alias:            "",
		Description:      "Test model",
		InputTokenPrice:  30,  // $0.03 per 1K tokens
		OutputTokenPrice: 60,  // $0.06 per 1K tokens
		CreatedAt:        time.Now(),
		UpdatedAt:        time.Now(),
	}

	for _, override := range overrides {
		override(model)
	}

	db.Create(model)
	return model
}

// CreateTestModelRoute creates a test model route
func CreateTestModelRoute(db *gorm.DB, modelID, providerID uint, overrides ...func(*models.ModelRoute)) *models.ModelRoute {
	route := &models.ModelRoute{
		ModelID:    modelID,
		ProviderID: providerID,
		Weight:     1,
		Disabled:   false,
		CreatedAt:  time.Now(),
	}

	for _, override := range overrides {
		override(route)
	}

	db.Create(route)
	return route
}

// CreateTestAPIKey creates a test API key
func CreateTestAPIKey(db *gorm.DB, userID *uint, overrides ...func(*models.GatewayAPIKey)) *models.GatewayAPIKey {
	key := &models.GatewayAPIKey{
		Key:               uuid.New().String(),
		Name:              "Test Key",
		Enabled:           true,
		BindToAllChannels: true,
		LogDetails:        true,
		UserID:            userID,
		CreatedAt:         time.Now(),
	}

	for _, override := range overrides {
		override(key)
	}

	db.Create(key)
	return key
}

// CreateTestChannel creates a test channel
func CreateTestChannel(db *gorm.DB, overrides ...func(*models.Channel)) *models.Channel {
	channel := &models.Channel{
		Name:      "Test Channel",
		Enabled:   true,
		Shared:    false,
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	for _, override := range overrides {
		override(channel)
	}

	db.Create(channel)
	return channel
}

// CreateTestLog creates a test log entry
func CreateTestLog(db *gorm.DB, apiKeyID uint, overrides ...func(*models.Log)) *models.Log {
	log := &models.Log{
		Latency:          100,
		PromptTokens:     100,
		CompletionTokens: 50,
		TotalTokens:      150,
		Cost:             100,
		Status:           200,
		APIKeyID:         apiKeyID,
		ModelName:        "gpt-4",
		ProviderName:     "Test Provider",
		CreatedAt:        time.Now(),
	}

	for _, override := range overrides {
		override(log)
	}

	db.Create(log)
	return log
}