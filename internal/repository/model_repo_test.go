package repository

import (
	"context"
	"testing"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/test"
)

func TestModelRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	model := &models.Model{
		Name:             "test-model",
		Alias:            "tm",
		Description:      "Test model description",
		InputTokenPrice:  30,
		OutputTokenPrice: 60,
	}

	err := repo.Create(context.Background(), model)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	if model.ID == 0 {
		t.Error("Expected model ID to be set after creation")
	}
}

func TestModelRepository_FindByID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "findbyid-model"
	})

	found, err := repo.FindByID(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindByID failed: %v", err)
	}

	if found.Name != "findbyid-model" {
		t.Errorf("Expected name 'findbyid-model', got '%s'", found.Name)
	}
}

func TestModelRepository_FindByID_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	_, err := repo.FindByID(context.Background(), 999)
	if err == nil {
		t.Error("Expected error for non-existent model ID")
	}
}

func TestModelRepository_FindByName(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "findbyname-model"
	})

	found, err := repo.FindByName(context.Background(), "findbyname-model")
	if err != nil {
		t.Fatalf("FindByName failed: %v", err)
	}

	if found.Name != "findbyname-model" {
		t.Errorf("Expected name 'findbyname-model', got '%s'", found.Name)
	}
}

func TestModelRepository_FindByName_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	_, err := repo.FindByName(context.Background(), "nonexistent-model")
	if err == nil {
		t.Error("Expected error for non-existent model name")
	}
}

func TestModelRepository_FindByNameOrAlias_ByAlias(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "real-model-name"
		m.Alias = "alias-model"
	})

	// Find by alias
	found, err := repo.FindByNameOrAlias(context.Background(), "alias-model")
	if err != nil {
		t.Fatalf("FindByNameOrAlias failed: %v", err)
	}

	if found.Name != "real-model-name" {
		t.Errorf("Expected name 'real-model-name', got '%s'", found.Name)
	}
}

func TestModelRepository_FindByNameOrAlias_ByName(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "name-model"
		m.Alias = "alias-model"
	})

	// Find by name
	found, err := repo.FindByNameOrAlias(context.Background(), "name-model")
	if err != nil {
		t.Fatalf("FindByNameOrAlias failed: %v", err)
	}

	if found.Name != "name-model" {
		t.Errorf("Expected name 'name-model', got '%s'", found.Name)
	}
}

func TestModelRepository_List(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	// Create multiple models
	test.CreateTestModel(db, func(m *models.Model) { m.Name = "model1" })
	test.CreateTestModel(db, func(m *models.Model) { m.Name = "model2" })
	test.CreateTestModel(db, func(m *models.Model) { m.Name = "model3" })

	models, err := repo.List(context.Background(), nil)
	if err != nil {
		t.Fatalf("List failed: %v", err)
	}

	if len(models) < 3 {
		t.Errorf("Expected at least 3 models, got %d", len(models))
	}
}

func TestModelRepository_Update(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.Description = "Original description"
	})

	// Update description
	model.Description = "Updated description"
	err := repo.Update(context.Background(), model)
	if err != nil {
		t.Fatalf("Update failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), model.ID)
	if found.Description != "Updated description" {
		t.Errorf("Expected description 'Updated description', got '%s'", found.Description)
	}
}

func TestModelRepository_Delete(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.Name = "delete-model"
	})

	err := repo.Delete(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("Delete failed: %v", err)
	}

	_, err = repo.FindByID(context.Background(), model.ID)
	if err == nil {
		t.Error("Expected error after model deleted")
	}
}

func TestModelRepository_UpdatePrices(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewModelRepository(db)

	model := test.CreateTestModel(db, func(m *models.Model) {
		m.InputTokenPrice = 30
		m.OutputTokenPrice = 60
	})

	err := repo.UpdatePrices(context.Background(), model.ID, 50, 100)
	if err != nil {
		t.Fatalf("UpdatePrices failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), model.ID)
	if found.InputTokenPrice != 50 {
		t.Errorf("Expected input price 50, got %d", found.InputTokenPrice)
	}
	if found.OutputTokenPrice != 100 {
		t.Errorf("Expected output price 100, got %d", found.OutputTokenPrice)
	}
}

func TestModelRepository_FindWithRoutes(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	modelRepo := NewModelRepository(db)
	modelRouteRepo := NewModelRouteRepository(db)

	provider := test.CreateTestProvider(db)
	model := test.CreateTestModel(db)

	// Create route
	route := &models.ModelRoute{
		ModelID:    model.ID,
		ProviderID: provider.ID,
		Weight:     1,
	}
	_ = modelRouteRepo // avoid unused variable error
	modelRouteRepo.Create(context.Background(), route)

	found, err := modelRepo.FindWithRoutes(context.Background(), model.ID)
	if err != nil {
		t.Fatalf("FindWithRoutes failed: %v", err)
	}

	if found.Name != model.Name {
		t.Errorf("Expected model name '%s', got '%s'", model.Name, found.Name)
	}
}