package service

import (
	"context"
)

type BillingService struct {
	userRepo UserRepoInterface
}

type UserRepoInterface interface {
	UpdateBalance(ctx context.Context, id uint, amount int64) error
	SubtractBalance(ctx context.Context, id uint, amount int64) error
}

func NewBillingService(userRepo UserRepoInterface) *BillingService {
	return &BillingService{userRepo: userRepo}
}

// CalculateCost calculates the cost based on token usage and prices
// Prices are per 1000 tokens
func (s *BillingService) CalculateCost(promptTokens, completionTokens int, inputPrice, outputPrice int64) int64 {
	cost := int64(float64(promptTokens)/1000*float64(inputPrice) +
		float64(completionTokens)/1000*float64(outputPrice))
	return cost
}

// DeductAndDistribute deducts cost from user and distributes to channel owner if applicable
func (s *BillingService) DeductAndDistribute(ctx context.Context, apiKeyUserID, channelOwnerUserID *uint, cost int64) error {
	if cost <= 0 {
		return nil
	}

	// Handle nil API key user ID
	if apiKeyUserID == nil {
		return nil
	}

	// If there's a channel owner and it's different from the API key user
	if channelOwnerUserID != nil && *channelOwnerUserID != *apiKeyUserID {
		// Channel owner receives the cost (shared channel revenue)
		return s.userRepo.UpdateBalance(ctx, *channelOwnerUserID, cost)
	}

	// Otherwise, deduct from API key user
	return s.userRepo.SubtractBalance(ctx, *apiKeyUserID, cost)
}