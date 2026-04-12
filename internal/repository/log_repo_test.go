package repository

import (
	"context"
	"testing"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/test"
)

func TestLogRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	log := &models.Log{
		APIKeyID:         &apiKey.ID,
		ModelName:        "gpt-4",
		ProviderName:     "openai",
		PromptTokens:     100,
		CompletionTokens: 50,
		TotalTokens:      150,
		Cost:             10,
		Latency:          500,
		Status:           200,
		CreatedAt:        time.Now(),
	}

	err := repo.Create(context.Background(), log)
	if err != nil {
		t.Fatalf("Failed to create log: %v", err)
	}

	if log.ID == 0 {
		t.Error("Expected log ID to be set after creation")
	}
}

func TestLogRepository_FindByID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	log := &models.Log{
		APIKeyID:     &apiKey.ID,
		ModelName:    "test-model",
		ProviderName: "test-provider",
		Status:       200,
		CreatedAt:    time.Now(),
	}
	db.Create(log)

	found, err := repo.FindByID(context.Background(), log.ID)
	if err != nil {
		t.Fatalf("Failed to find log: %v", err)
	}

	if found.ModelName != "test-model" {
		t.Errorf("Expected model 'test-model', got '%s'", found.ModelName)
	}
}

func TestLogRepository_List(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create multiple logs
	for i := 0; i < 25; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-4",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    time.Now(),
		}
		db.Create(log)
	}

	logs, total, err := repo.List(context.Background(), nil, "", 1, 10)
	if err != nil {
		t.Fatalf("Failed to list logs: %v", err)
	}

	if total != 25 {
		t.Errorf("Expected total 25, got %d", total)
	}

	if len(logs) != 10 {
		t.Errorf("Expected 10 logs on page 1, got %d", len(logs))
	}
}

func TestLogRepository_GetStatsByProvider(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create logs for different providers
	for i := 0; i < 5; i++ {
		log := &models.Log{
			APIKeyID:         &apiKey.ID,
			ModelName:        "gpt-4",
			ProviderName:     "openai",
			PromptTokens:     100,
			CompletionTokens: 50,
			TotalTokens:      150,
			Cost:             10,
			Status:           200,
			CreatedAt:        time.Now(),
		}
		db.Create(log)
	}

	for i := 0; i < 3; i++ {
		log := &models.Log{
			APIKeyID:         &apiKey.ID,
			ModelName:        "claude",
			ProviderName:     "anthropic",
			PromptTokens:     200,
			CompletionTokens: 100,
			TotalTokens:      300,
			Cost:             20,
			Status:           200,
			CreatedAt:        time.Now(),
		}
		db.Create(log)
	}

	now := time.Now()
	start := now.AddDate(0, 0, -30)

	stats, err := repo.GetStatsByProvider(context.Background(), start, now)
	if err != nil {
		t.Fatalf("Failed to get stats by provider: %v", err)
	}

	if len(stats) < 2 {
		t.Errorf("Expected at least 2 providers in stats, got %d", len(stats))
	}
}

func TestLogRepository_GetStatsByModel(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create logs for different models
	for i := 0; i < 5; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-4",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    time.Now(),
		}
		db.Create(log)
	}

	for i := 0; i < 3; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-3.5-turbo",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    time.Now(),
		}
		db.Create(log)
	}

	now := time.Now()
	start := now.AddDate(0, 0, -30)

	stats, err := repo.GetStatsByModel(context.Background(), start, now)
	if err != nil {
		t.Fatalf("Failed to get stats by model: %v", err)
	}

	if len(stats) < 2 {
		t.Errorf("Expected at least 2 models in stats, got %d", len(stats))
	}
}

func TestLogRepository_GetDailyUsage(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create logs for today
	for i := 0; i < 5; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-4",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    time.Now(),
		}
		db.Create(log)
	}

	// Create logs for yesterday
	yesterday := time.Now().AddDate(0, 0, -1)
	for i := 0; i < 3; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-4",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    yesterday,
		}
		db.Create(log)
	}

	now := time.Now()
	start := now.AddDate(0, 0, -7)

	daily, err := repo.GetDailyUsage(context.Background(), start, now)
	if err != nil {
		t.Fatalf("Failed to get daily usage: %v", err)
	}

	if len(daily) == 0 {
		t.Error("Expected daily usage data")
	}
}

func TestLogRepository_GetTotalStats(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create logs
	for i := 0; i < 10; i++ {
		log := &models.Log{
			APIKeyID:         &apiKey.ID,
			ModelName:        "gpt-4",
			ProviderName:     "openai",
			PromptTokens:     100,
			CompletionTokens: 50,
			TotalTokens:      150,
			Cost:             10,
			Status:           200,
			CreatedAt:        time.Now(),
		}
		db.Create(log)
	}

	now := time.Now()
	start := now.AddDate(0, 0, -30)

	requests, tokens, cost, err := repo.GetTotalStats(context.Background(), start, now)
	if err != nil {
		t.Fatalf("Failed to get total stats: %v", err)
	}

	if requests != 10 {
		t.Errorf("Expected 10 requests, got %d", requests)
	}

	if tokens != 1500 {
		t.Errorf("Expected 1500 tokens, got %d", tokens)
	}

	if cost != 100 {
		t.Errorf("Expected 100 cost, got %d", cost)
	}
}

func TestLogRepository_GetUserTokenStats(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create logs for this user
	for i := 0; i < 5; i++ {
		log := &models.Log{
			APIKeyID:         &apiKey.ID,
			ModelName:        "gpt-4",
			ProviderName:     "openai",
			PromptTokens:     100,
			CompletionTokens: 50,
			TotalTokens:      150,
			Status:           200,
			CreatedAt:        time.Now(),
		}
		db.Create(log)
	}

	prompt, completion, total, err := repo.GetUserTokenStats(context.Background(), user.ID)
	if err != nil {
		t.Fatalf("Failed to get user token stats: %v", err)
	}

	if prompt != 500 {
		t.Errorf("Expected 500 prompt tokens, got %d", prompt)
	}

	if completion != 250 {
		t.Errorf("Expected 250 completion tokens, got %d", completion)
	}

	if total != 750 {
		t.Errorf("Expected 750 total tokens, got %d", total)
	}
}

func TestLogRepository_GetUserModelUsage(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewLogRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	// Create logs for different models
	for i := 0; i < 3; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-4",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    time.Now(),
		}
		db.Create(log)
	}

	for i := 0; i < 2; i++ {
		log := &models.Log{
			APIKeyID:     &apiKey.ID,
			ModelName:    "gpt-3.5-turbo",
			ProviderName: "openai",
			Status:       200,
			CreatedAt:    time.Now(),
		}
		db.Create(log)
	}

	stats, err := repo.GetUserModelUsage(context.Background(), user.ID)
	if err != nil {
		t.Fatalf("Failed to get user model usage: %v", err)
	}

	if len(stats) < 2 {
		t.Errorf("Expected at least 2 models in stats, got %d", len(stats))
	}
}