package service

import (
	"context"
	"testing"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/test"
)

func TestGatewayService_FindModel_WithColon(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create model with colon in name
	test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "gpt-4:latest"
		m.Alias = ""
	})

	model, err := service.findModel(context.Background(), "gpt-4:latest")
	if err != nil {
		t.Fatalf("findModel failed: %v", err)
	}

	if model.Name != "gpt-4:latest" {
		t.Errorf("Expected model name 'gpt-4:latest', got '%s'", model.Name)
	}
}

func TestGatewayService_FindModel_WithoutColon(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create model with :latest suffix
	test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "gpt-4:latest"
		m.Alias = ""
	})

	// Test finding without colon - should auto-add :latest
	model, err := service.findModel(context.Background(), "gpt-4")
	if err != nil {
		t.Fatalf("findModel failed: %v", err)
	}

	if model.Name != "gpt-4:latest" {
		t.Errorf("Expected model name 'gpt-4:latest', got '%s'", model.Name)
	}
}

func TestGatewayService_FindModel_ByAlias(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create model with alias
	test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "gpt-4-turbo"
		m.Alias = "gpt4"
	})

	// Test finding by alias
	model, err := service.findModel(context.Background(), "gpt4")
	if err != nil {
		t.Fatalf("findModel failed: %v", err)
	}

	if model.Name != "gpt-4-turbo" {
		t.Errorf("Expected model name 'gpt-4-turbo', got '%s'", model.Name)
	}
}

func TestGatewayService_FindModel_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	_, err := service.findModel(context.Background(), "nonexistent")
	if err == nil {
		t.Error("Expected error for nonexistent model, got nil")
	}
}

func TestGatewayService_SelectRoute_SingleRoute(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create provider and model
	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	// Create single route
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 1
		r.Disabled = false
	})

	route, err := service.selectRoute(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("selectRoute failed: %v", err)
	}

	if route.ModelID != model.ID {
		t.Errorf("Expected model ID %d, got %d", model.ID, route.ModelID)
	}

	if route.ProviderID != provider.ID {
		t.Errorf("Expected provider ID %d, got %d", provider.ID, route.ProviderID)
	}
}

func TestGatewayService_SelectRoute_MultipleRoutes(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create providers and model
	provider1 := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "Provider1"
		p.Disabled = false
	})
	provider2 := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "Provider2"
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	// Create routes with different weights
	test.CreateTestModelRoute(db, model.ID, provider1.ID, func(r *models.ModelRoute) {
		r.Weight = 3
		r.Disabled = false
	})
	test.CreateTestModelRoute(db, model.ID, provider2.ID, func(r *models.ModelRoute) {
		r.Weight = 1
		r.Disabled = false
	})

	// Run multiple selections to test weighted random
	provider1Count := 0
	provider2Count := 0
	iterations := 100

	for i := 0; i < iterations; i++ {
		route, err := service.selectRoute(context.Background(), model.ID)
		if err != nil {
			t.Fatalf("selectRoute failed: %v", err)
		}

		if route.ProviderID == provider1.ID {
			provider1Count++
		} else if route.ProviderID == provider2.ID {
			provider2Count++
		}
	}

	// Provider1 should be selected more often (weight 3 vs 1)
	// Expected ratio is approximately 75:25
	if provider1Count < provider2Count {
		t.Errorf("Expected provider1 (weight 3) to be selected more than provider2 (weight 1), got %d:%d", provider1Count, provider2Count)
	}
}

func TestGatewayService_SelectRoute_NoRoutes(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	model := test.CreateTestModel(db)
	// No routes created

	_, err := service.selectRoute(context.Background(), model.ID)
	if err != ErrNoRouteAvailable {
		t.Errorf("Expected ErrNoRouteAvailable, got %v", err)
	}
}

func TestGatewayService_SelectRoute_DisabledRoute(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	// Create disabled route
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 1
		r.Disabled = true
	})

	_, err := service.selectRoute(context.Background(), model.ID)
	if err != ErrNoRouteAvailable {
		t.Errorf("Expected ErrNoRouteAvailable for disabled route, got %v", err)
	}
}

func TestGatewayService_SelectRoute_DisabledProvider(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create disabled provider
	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = true
	})
	model := test.CreateTestModel(db)

	// Create route for disabled provider
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 1
		r.Disabled = false
	})

	_, err := service.selectRoute(context.Background(), model.ID)
	if err != ErrNoRouteAvailable {
		t.Errorf("Expected ErrNoRouteAvailable for disabled provider, got %v", err)
	}
}

func TestGatewayService_CheckPermission_BindToAllChannels(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	// Create API key with BindToAllChannels
	apiKey := test.CreateTestAPIKey(db, nil, func(k *models.GatewayAPIKey) {
		k.BindToAllChannels = true
	})
	model := test.CreateTestModel(db)

	err := service.checkPermission(context.Background(), apiKey, model.ID)
	if err != nil {
		t.Errorf("Expected no error for BindToAllChannels, got %v", err)
	}
}

func TestGatewayService_CheckPermission_SpecificChannels(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	user := test.CreateTestUser(db)
	model := test.CreateTestModel(db)

	// Create channel and bind model to it
	channel := test.CreateTestChannel(db)
	channelRepo.BindModels(context.Background(), channel.ID, []uint{model.ID})

	// Create API key bound to specific channel
	apiKey := test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.BindToAllChannels = false
	})
	apiKeyRepo.BindChannels(context.Background(), apiKey.ID, []uint{channel.ID})

	err := service.checkPermission(context.Background(), apiKey, model.ID)
	if err != nil {
		t.Errorf("Expected no error for model allowed in bound channel, got %v", err)
	}
}

func TestGatewayService_CheckPermission_NoPermission(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	user := test.CreateTestUser(db)
	model := test.CreateTestModel(db)

	// Create channel but don't bind the model
	channel := test.CreateTestChannel(db)

	// Create API key bound to specific channel
	apiKey := test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.BindToAllChannels = false
	})
	apiKeyRepo.BindChannels(context.Background(), apiKey.ID, []uint{channel.ID})

	err := service.checkPermission(context.Background(), apiKey, model.ID)
	if err != ErrPermissionDenied {
		t.Errorf("Expected ErrPermissionDenied, got %v", err)
	}
}

func TestGatewayService_CheckPermission_NoChannelsBound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	user := test.CreateTestUser(db)
	model := test.CreateTestModel(db)

	// Create API key without binding to any channel
	apiKey := test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.BindToAllChannels = false
	})

	err := service.checkPermission(context.Background(), apiKey, model.ID)
	if err != ErrPermissionDenied {
		t.Errorf("Expected ErrPermissionDenied, got %v", err)
	}
}

func TestGatewayService_CheckBalance_Sufficient(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 1000
	})

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.InputTokenPrice = 30
		m.OutputTokenPrice = 60
	})

	err := service.checkBalance(context.Background(), &user.ID, model)
	if err != nil {
		t.Errorf("Expected no error for sufficient balance, got %v", err)
	}
}

func TestGatewayService_CheckBalance_Insufficient(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 0
	})

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.InputTokenPrice = 30
		m.OutputTokenPrice = 60
	})

	err := service.checkBalance(context.Background(), &user.ID, model)
	if err != ErrInsufficientBalance {
		t.Errorf("Expected ErrInsufficientBalance, got %v", err)
	}
}

func TestGatewayService_CheckBalance_NoPricing(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 0
	})

	// Model with no pricing
	model := test.CreateTestModel(db, func(m *models.Model) {
		m.InputTokenPrice = 0
		m.OutputTokenPrice = 0
	})

	err := service.checkBalance(context.Background(), &user.ID, model)
	if err != nil {
		t.Errorf("Expected no error for model without pricing, got %v", err)
	}
}

func TestGatewayService_CheckBalance_NilUserID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := repository.NewModelRepository(db)
	modelRouteRepo := repository.NewModelRouteRepository(db)
	apiKeyRepo := repository.NewAPIKeyRepository(db)
	channelRepo := repository.NewChannelRepository(db)
	userRepo := repository.NewUserRepository(db)
	logRepo := repository.NewLogRepository(db)
	logDetailRepo := repository.NewLogDetailRepository(db)
	billingService := NewBillingService(userRepo)

	service := NewGatewayService(
		modelRepo, modelRouteRepo, apiKeyRepo, channelRepo, userRepo,
		logRepo, logDetailRepo, billingService, nil,
	)

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.InputTokenPrice = 30
		m.OutputTokenPrice = 60
	})

	err := service.checkBalance(context.Background(), nil, model)
	if err != nil {
		t.Errorf("Expected no error for nil user ID, got %v", err)
	}
}

func TestWeightedRandomSelect_SingleWeight(t *testing.T) {
	weights := []int{5}
	idx := weightedRandomSelect(weights)
	if idx != 0 {
		t.Errorf("Expected index 0 for single weight, got %d", idx)
	}
}

func TestWeightedRandomSelect_ZeroWeights(t *testing.T) {
	weights := []int{0, 0, 0}
	idx := weightedRandomSelect(weights)
	// Should return last index when all weights are 0
	if idx != len(weights)-1 {
		t.Errorf("Expected last index %d for zero weights, got %d", len(weights)-1, idx)
	}
}

func TestWeightedRandomSelect_EqualWeights(t *testing.T) {
	weights := []int{1, 1, 1}
	// Test distribution
	counts := make(map[int]int)
	iterations := 300

	for i := 0; i < iterations; i++ {
		idx := weightedRandomSelect(weights)
		counts[idx]++
	}

	// Each index should get roughly equal selections
	for idx, count := range counts {
		if count < 50 || count > 150 {
			t.Errorf("Index %d has unexpected count %d (expected roughly 100)", idx, count)
		}
	}
}

func TestWeightedRandomSelect_DifferentWeights(t *testing.T) {
	weights := []int{10, 1}
	// Weight 10 should be selected ~10x more often than weight 1
	count0 := 0
	count1 := 0
	iterations := 1000

	for i := 0; i < iterations; i++ {
		idx := weightedRandomSelect(weights)
		if idx == 0 {
			count0++
		} else {
			count1++
		}
	}

	// count0 should be approximately 90% of iterations
	expectedCount0 := iterations * 10 / 11
	if count0 < expectedCount0-50 || count0 > expectedCount0+50 {
		t.Errorf("Weight 10 index count %d not close to expected %d", count0, expectedCount0)
	}
}