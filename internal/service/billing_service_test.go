package service

import (
	"context"
	"testing"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/test"
)

// MockUserRepo for billing service tests
type MockUserRepo struct {
	UpdateBalanceFunc    func(ctx context.Context, id uint, amount int64) error
	SubtractBalanceFunc  func(ctx context.Context, id uint, amount int64) error
}

func (m *MockUserRepo) UpdateBalance(ctx context.Context, id uint, amount int64) error {
	if m.UpdateBalanceFunc != nil {
		return m.UpdateBalanceFunc(ctx, id, amount)
	}
	return nil
}

func (m *MockUserRepo) SubtractBalance(ctx context.Context, id uint, amount int64) error {
	if m.SubtractBalanceFunc != nil {
		return m.SubtractBalanceFunc(ctx, id, amount)
	}
	return nil
}

func TestBillingService_CalculateCost_Basic(t *testing.T) {
	mockRepo := &MockUserRepo{}
	service := NewBillingService(mockRepo)

	// Test basic cost calculation
	// Input: 1000 prompt tokens, 500 completion tokens
	// Price: $0.03/1K input, $0.06/1K output
	cost := service.CalculateCost(1000, 500, 30, 60)

	expected := int64(30 + 30) // 1000/1000*30 + 500/1000*60 = 30 + 30 = 60
	if cost != expected {
		t.Errorf("Expected cost %d, got %d", expected, cost)
	}
}

func TestBillingService_CalculateCost_ZeroTokens(t *testing.T) {
	mockRepo := &MockUserRepo{}
	service := NewBillingService(mockRepo)

	cost := service.CalculateCost(0, 0, 30, 60)
	if cost != 0 {
		t.Errorf("Expected cost 0 for zero tokens, got %d", cost)
	}
}

func TestBillingService_CalculateCost_LargeNumbers(t *testing.T) {
	mockRepo := &MockUserRepo{}
	service := NewBillingService(mockRepo)

	// Test with large token counts
	// 100K prompt tokens, 50K completion tokens
	cost := service.CalculateCost(100000, 50000, 30, 60)

	expected := int64(3000 + 3000) // 100*30 + 50*60 = 3000 + 3000 = 6000
	if cost != expected {
		t.Errorf("Expected cost %d, got %d", expected, cost)
	}
}

func TestBillingService_CalculateCost_PartialTokens(t *testing.T) {
	mockRepo := &MockUserRepo{}
	service := NewBillingService(mockRepo)

	// Test with partial thousands
	// 500 prompt tokens, 250 completion tokens
	cost := service.CalculateCost(500, 250, 30, 60)

	expected := int64(15 + 15) // 0.5*30 + 0.25*60 = 15 + 15 = 30
	if cost != expected {
		t.Errorf("Expected cost %d, got %d", expected, cost)
	}
}

func TestBillingService_DeductAndDistribute_FromAPIKeyUser(t *testing.T) {
	var updatedUserID uint
	var updatedAmount int64

	mockRepo := &MockUserRepo{
		SubtractBalanceFunc: func(ctx context.Context, id uint, amount int64) error {
			updatedUserID = id
			updatedAmount = amount
			return nil
		},
	}

	service := NewBillingService(mockRepo)

	apiKeyUserID := uint(1)
	var channelOwnerUserID *uint // No channel owner

	err := service.DeductAndDistribute(context.Background(), &apiKeyUserID, channelOwnerUserID, 100)
	if err != nil {
		t.Fatalf("DeductAndDistribute failed: %v", err)
	}

	if updatedUserID != apiKeyUserID {
		t.Errorf("Expected user ID %d, got %d", apiKeyUserID, updatedUserID)
	}

	if updatedAmount != 100 {
		t.Errorf("Expected amount 100, got %d", updatedAmount)
	}
}

func TestBillingService_DeductAndDistribute_ToChannelOwner(t *testing.T) {
	var updatedUserID uint
	var updatedAmount int64

	mockRepo := &MockUserRepo{
		UpdateBalanceFunc: func(ctx context.Context, id uint, amount int64) error {
			updatedUserID = id
			updatedAmount = amount
			return nil
		},
	}

	service := NewBillingService(mockRepo)

	apiKeyUserID := uint(1)
	channelOwnerUserID := uint(2)

	err := service.DeductAndDistribute(context.Background(), &apiKeyUserID, &channelOwnerUserID, 100)
	if err != nil {
		t.Fatalf("DeductAndDistribute failed: %v", err)
	}

	if updatedUserID != channelOwnerUserID {
		t.Errorf("Expected user ID %d (channel owner), got %d", channelOwnerUserID, updatedUserID)
	}

	if updatedAmount != 100 {
		t.Errorf("Expected amount 100, got %d", updatedAmount)
	}
}

func TestBillingService_DeductAndDistribute_SameUser(t *testing.T) {
	var subtractedUserID uint
	var subtractedAmount int64

	mockRepo := &MockUserRepo{
		SubtractBalanceFunc: func(ctx context.Context, id uint, amount int64) error {
			subtractedUserID = id
			subtractedAmount = amount
			return nil
		},
	}

	service := NewBillingService(mockRepo)

	apiKeyUserID := uint(1)
	channelOwnerUserID := uint(1) // Same user

	err := service.DeductAndDistribute(context.Background(), &apiKeyUserID, &channelOwnerUserID, 100)
	if err != nil {
		t.Fatalf("DeductAndDistribute failed: %v", err)
	}

	if subtractedUserID != apiKeyUserID {
		t.Errorf("Expected user ID %d, got %d", apiKeyUserID, subtractedUserID)
	}

	if subtractedAmount != 100 {
		t.Errorf("Expected amount 100, got %d", subtractedAmount)
	}
}

func TestBillingService_DeductAndDistribute_ZeroCost(t *testing.T) {
	mockRepo := &MockUserRepo{}

	service := NewBillingService(mockRepo)

	apiKeyUserID := uint(1)

	err := service.DeductAndDistribute(context.Background(), &apiKeyUserID, nil, 0)
	if err != nil {
		t.Fatalf("DeductAndDistribute failed: %v", err)
	}

	// Should not call any repo methods for zero cost
}

func TestBillingService_DeductAndDistribute_NilUserID(t *testing.T) {
	mockRepo := &MockUserRepo{}

	service := NewBillingService(mockRepo)

	err := service.DeductAndDistribute(context.Background(), nil, nil, 100)
	if err != nil {
		t.Fatalf("DeductAndDistribute failed: %v", err)
	}

	// Should handle nil user IDs gracefully
}

// Integration test with real database
func TestBillingService_Integration(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	userRepo := repository.NewUserRepository(db)
	service := NewBillingService(userRepo)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 1000
	})

	// Test deduct
	err := service.DeductAndDistribute(context.Background(), &user.ID, nil, 100)
	if err != nil {
		t.Fatalf("DeductAndDistribute failed: %v", err)
	}

	// Verify balance was updated
	updatedUser, _ := userRepo.FindByID(context.Background(), user.ID)
	if updatedUser.Balance != 900 {
		t.Errorf("Expected balance 900, got %d", updatedUser.Balance)
	}

	// Test add balance
	userRepo.UpdateBalance(context.Background(), user.ID, 200)

	updatedUser, _ = userRepo.FindByID(context.Background(), user.ID)
	if updatedUser.Balance != 1100 {
		t.Errorf("Expected balance 1100, got %d", updatedUser.Balance)
	}
}