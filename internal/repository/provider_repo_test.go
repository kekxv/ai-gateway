package repository

import (
	"context"
	"fmt"
	"testing"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/test"
)

func TestProviderRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	provider := &models.Provider{
		Name:           "test-provider",
		BaseURL:        "https://api.test.com",
		APIKey:         "test-key",
		Type:           "openai",
		AutoLoadModels: true,
		Disabled:       false,
	}

	err := repo.Create(context.Background(), provider)
	if err != nil {
		t.Fatalf("Failed to create provider: %v", err)
	}

	if provider.ID == 0 {
		t.Error("Expected provider ID to be set after creation")
	}
}

func TestProviderRepository_FindByID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	// Create a provider first
	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "find-test"
	})

	// Find by ID
	found, err := repo.FindByID(context.Background(), provider.ID)
	if err != nil {
		t.Fatalf("Failed to find provider: %v", err)
	}

	if found.Name != "find-test" {
		t.Errorf("Expected name 'find-test', got '%s'", found.Name)
	}
}

func TestProviderRepository_FindByID_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	_, err := repo.FindByID(context.Background(), 999)
	if err == nil {
		t.Error("Expected error for non-existent provider")
	}
}

func TestProviderRepository_List(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	// Create multiple providers
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider1" })
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider2" })
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "provider3" })

	providers, err := repo.List(context.Background(), nil)
	if err != nil {
		t.Fatalf("Failed to list providers: %v", err)
	}

	if len(providers) < 3 {
		t.Errorf("Expected at least 3 providers, got %d", len(providers))
	}
}

func TestProviderRepository_ListWithCount(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	// Create multiple providers
	for i := 0; i < 15; i++ {
		test.CreateTestProvider(db, func(p *models.Provider) {
			p.Name = fmt.Sprintf("provider-%d", i)
		})
	}

	// Test pagination
	providers, total, err := repo.ListWithCount(context.Background(), nil, 1, 10)
	if err != nil {
		t.Fatalf("Failed to list providers with count: %v", err)
	}

	if total != 15 {
		t.Errorf("Expected total 15, got %d", total)
	}

	if len(providers) != 10 {
		t.Errorf("Expected 10 providers on page 1, got %d", len(providers))
	}

	// Test second page
	providers2, _, err := repo.ListWithCount(context.Background(), nil, 2, 10)
	if err != nil {
		t.Fatalf("Failed to list providers on page 2: %v", err)
	}

	if len(providers2) != 5 {
		t.Errorf("Expected 5 providers on page 2, got %d", len(providers2))
	}
}

func TestProviderRepository_Update(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "original-name"
	})

	provider.Name = "updated-name"
	provider.BaseURL = "https://updated.com"

	err := repo.Update(context.Background(), provider)
	if err != nil {
		t.Fatalf("Failed to update provider: %v", err)
	}

	// Verify update
	found, _ := repo.FindByID(context.Background(), provider.ID)
	if found.Name != "updated-name" {
		t.Errorf("Expected name 'updated-name', got '%s'", found.Name)
	}
}

func TestProviderRepository_Delete(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	provider := test.CreateTestProvider(db, func(p *models.Provider) {
		p.Name = "to-delete"
	})

	err := repo.Delete(context.Background(), provider.ID)
	if err != nil {
		t.Fatalf("Failed to delete provider: %v", err)
	}

	// Verify deletion
	_, err = repo.FindByID(context.Background(), provider.ID)
	if err == nil {
		t.Error("Expected error finding deleted provider")
	}
}

func TestProviderRepository_Count(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewProviderRepository(db)

	// Create providers
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "p1" })
	test.CreateTestProvider(db, func(p *models.Provider) { p.Name = "p2" })

	count, err := repo.Count(context.Background())
	if err != nil {
		t.Fatalf("Failed to count providers: %v", err)
	}

	if count < 2 {
		t.Errorf("Expected at least 2 providers, got %d", count)
	}
}

func TestChannelRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewChannelRepository(db)

	channel := &models.Channel{
		Name:    "test-channel",
		Enabled: true,
	}

	err := repo.Create(context.Background(), channel)
	if err != nil {
		t.Fatalf("Failed to create channel: %v", err)
	}

	if channel.ID == 0 {
		t.Error("Expected channel ID to be set after creation")
	}
}

func TestChannelRepository_FindByID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewChannelRepository(db)

	channel := test.CreateTestChannel(db, func(c *models.Channel) {
		c.Name = "find-test"
	})

	found, err := repo.FindByID(context.Background(), channel.ID)
	if err != nil {
		t.Fatalf("Failed to find channel: %v", err)
	}

	if found.Name != "find-test" {
		t.Errorf("Expected name 'find-test', got '%s'", found.Name)
	}
}

func TestChannelRepository_List(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewChannelRepository(db)

	test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "channel1" })
	test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "channel2" })

	channels, err := repo.List(context.Background(), nil)
	if err != nil {
		t.Fatalf("Failed to list channels: %v", err)
	}

	if len(channels) < 2 {
		t.Errorf("Expected at least 2 channels, got %d", len(channels))
	}
}

func TestChannelRepository_Update(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewChannelRepository(db)

	channel := test.CreateTestChannel(db, func(c *models.Channel) {
		c.Name = "original"
	})

	channel.Name = "updated"
	err := repo.Update(context.Background(), channel)
	if err != nil {
		t.Fatalf("Failed to update channel: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), channel.ID)
	if found.Name != "updated" {
		t.Errorf("Expected name 'updated', got '%s'", found.Name)
	}
}

func TestChannelRepository_Delete(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewChannelRepository(db)

	channel := test.CreateTestChannel(db, func(c *models.Channel) {
		c.Name = "to-delete"
	})

	err := repo.Delete(context.Background(), channel.ID)
	if err != nil {
		t.Fatalf("Failed to delete channel: %v", err)
	}

	_, err = repo.FindByID(context.Background(), channel.ID)
	if err == nil {
		t.Error("Expected error finding deleted channel")
	}
}