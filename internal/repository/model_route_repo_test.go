package repository

import (
	"context"
	"testing"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/test"
)

func TestModelRouteRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db)
	model := test.CreateTestModel(db)

	route := &models.ModelRoute{
		ModelID:    model.ID,
		ProviderID: provider.ID,
		Weight:     5,
		Disabled:   false,
	}

	err := repo.Create(context.Background(), route)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	if route.ID == 0 {
		t.Error("Expected route ID to be set after creation")
	}
}

func TestModelRouteRepository_FindEligibleRoutes(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 1
		r.Disabled = false
	})

	routes, err := repo.FindEligibleRoutes(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindEligibleRoutes failed: %v", err)
	}

	if len(routes) != 1 {
		t.Errorf("Expected 1 eligible route, got %d", len(routes))
	}
}

func TestModelRouteRepository_FindEligibleRoutes_ExcludeDisabled(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	// Create enabled route
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 1
		r.Disabled = false
	})

	// Create disabled route
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 2
		r.Disabled = true
	})

	routes, err := repo.FindEligibleRoutes(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindEligibleRoutes failed: %v", err)
	}

	// Should only return 1 route (the enabled one)
	if len(routes) != 1 {
		t.Errorf("Expected 1 eligible route (disabled excluded), got %d", len(routes))
	}
}

func TestModelRouteRepository_FindEligibleRoutes_ExcludeDisabledProvider(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	enabledProvider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "Enabled Provider"
		p.Disabled = false
	})
	disabledProvider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "Disabled Provider"
		p.Disabled = true
	})
	model := test.CreateTestModel(db)

	// Route to enabled provider
	test.CreateTestModelRoute(db, model.ID, enabledProvider.ID, func(r *models.ModelRoute) {
		r.Disabled = false
	})

	// Route to disabled provider
	test.CreateTestModelRoute(db, model.ID, disabledProvider.ID, func(r *models.ModelRoute) {
		r.Disabled = false
	})

	routes, err := repo.FindEligibleRoutes(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindEligibleRoutes failed: %v", err)
	}

	// Should only return route to enabled provider
	if len(routes) != 1 {
		t.Errorf("Expected 1 eligible route (disabled provider excluded), got %d", len(routes))
	}

	if len(routes) > 0 && routes[0].ProviderID != enabledProvider.ID {
		t.Errorf("Expected route to enabled provider")
	}
}

func TestModelRouteRepository_FindEligibleRoutes_ExcludeDisabledUntil(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	// Route with expired disabledUntil (should be eligible)
	futureTime := time.Now().Add(10 * time.Minute)
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Disabled = false
		r.DisabledUntil = &futureTime
	})

	routes, err := repo.FindEligibleRoutes(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindEligibleRoutes failed: %v", err)
	}

	// Should return 0 routes (route is temporarily disabled)
	if len(routes) != 0 {
		t.Errorf("Expected 0 eligible routes (route disabled until future), got %d", len(routes))
	}
}

func TestModelRouteRepository_FindByModel(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db)
	model := test.CreateTestModel(db)

	test.CreateTestModelRoute(db, model.ID, provider.ID)

	routes, err := repo.FindByModel(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindByModel failed: %v", err)
	}

	if len(routes) != 1 {
		t.Errorf("Expected 1 route, got %d", len(routes))
	}
}

func TestModelRouteRepository_UpdateWeight(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db)
	model := test.CreateTestModel(db)
	route := test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Weight = 1
	})

	err := repo.UpdateWeight(context.Background(), route.ID, 10)
	if err != nil {
		t.Fatalf("UpdateWeight failed: %v", err)
	}

	routes, _ := repo.FindByModel(context.Background(), model.ID)
	if routes[0].Weight != 10 {
		t.Errorf("Expected weight 10, got %d", routes[0].Weight)
	}
}

func TestModelRouteRepository_DisableUntil(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db)
	model := test.CreateTestModel(db)
	route := test.CreateTestModelRoute(db, model.ID, provider.ID)

	until := time.Now().Add(5 * time.Minute)
	err := repo.DisableUntil(context.Background(), route.ID, until)
	if err != nil {
		t.Fatalf("DisableUntil failed: %v", err)
	}

	routes, _ := repo.FindByModel(context.Background(), model.ID)
	if routes[0].DisabledUntil == nil {
		t.Error("Expected DisabledUntil to be set")
	}
}

func TestModelRouteRepository_CountEligible(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Disabled = false
	})
	model := test.CreateTestModel(db)

	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Disabled = false
	})
	test.CreateTestModelRoute(db, model.ID, provider.ID, func(r *models.ModelRoute) {
		r.Disabled = true // Should not be counted
	})

	count, err := repo.CountEligible(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("CountEligible failed: %v", err)
	}

	// Should count only 1 (the non-disabled route)
	if count != 1 {
		t.Errorf("Expected count 1, got %d", count)
	}
}

func TestModelRouteRepository_CountEligible_NoRoutes(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRouteRepository(db)

	model := test.CreateTestModel(db)
	// No routes created

	count, err := repo.CountEligible(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("CountEligible failed: %v", err)
	}

	if count != 0 {
		t.Errorf("Expected count 0 for no routes, got %d", count)
	}
}