package repository

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/test"
)

func TestAPIKeyRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	key := &models.GatewayAPIKey{
		Key:               uuid.New().String(),
		Name:              "Test Key",
		Enabled:           true,
		BindToAllChannels: true,
		UserID:            &user.ID,
	}

	err := repo.Create(context.Background(), key)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	if key.ID == 0 {
		t.Error("Expected API key ID to be set after creation")
	}
}

func TestAPIKeyRepository_FindByKey(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	testKey := uuid.New().String()
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Key = testKey
		k.Name = "Find Key Test"
	})

	found, err := repo.FindByKey(context.Background(), testKey)
	if err != nil {
		t.Fatalf("FindByKey failed: %v", err)
	}

	if found.Key != testKey {
		t.Errorf("Expected key '%s', got '%s'", testKey, found.Key)
	}
}

func TestAPIKeyRepository_FindByKey_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	_, err := repo.FindByKey(context.Background(), "nonexistent-key")
	if err == nil {
		t.Error("Expected error for non-existent key")
	}
}

func TestAPIKeyRepository_FindByID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)

	found, err := repo.FindByID(context.Background(), apiKey.ID)
	if err != nil {
		t.Fatalf("FindByID failed: %v", err)
	}

	if found.ID != apiKey.ID {
		t.Errorf("Expected ID %d, got %d", apiKey.ID, found.ID)
	}
}

func TestAPIKeyRepository_List(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)

	// Create multiple API keys
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Name = "Key 1"
	})
	test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Name = "Key 2"
	})

	keys, err := repo.List(context.Background(), &user.ID)
	if err != nil {
		t.Fatalf("List failed: %v", err)
	}

	if len(keys) < 2 {
		t.Errorf("Expected at least 2 keys for user, got %d", len(keys))
	}
}

func TestAPIKeyRepository_List_All(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user1 := test.CreateTestUser(db, func(u *models.User) { u.Email = "user1@test.com" })
	user2 := test.CreateTestUser(db, func(u *models.User) { u.Email = "user2@test.com" })

	test.CreateTestAPIKey(db, &user1.ID)
	test.CreateTestAPIKey(db, &user2.ID)

	// List all keys (nil userID)
	keys, err := repo.List(context.Background(), nil)
	if err != nil {
		t.Fatalf("List failed: %v", err)
	}

	if len(keys) < 2 {
		t.Errorf("Expected at least 2 keys total, got %d", len(keys))
	}
}

func TestAPIKeyRepository_Update(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Name = "Original Name"
	})

	// Update name
	apiKey.Name = "Updated Name"
	err := repo.Update(context.Background(), apiKey)
	if err != nil {
		t.Fatalf("Update failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), apiKey.ID)
	if found.Name != "Updated Name" {
		t.Errorf("Expected name 'Updated Name', got '%s'", found.Name)
	}
}

func TestAPIKeyRepository_Update_Enabled(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID, func(k *models.GatewayAPIKey) {
		k.Enabled = true
	})

	// Disable key
	apiKey.Enabled = false
	err := repo.Update(context.Background(), apiKey)
	if err != nil {
		t.Fatalf("Update failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), apiKey.ID)
	if found.Enabled {
		t.Error("Expected key to be disabled")
	}
}

func TestAPIKeyRepository_BindChannels(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)
	channel1 := test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "Channel 1" })
	channel2 := test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "Channel 2" })

	err := repo.BindChannels(context.Background(), apiKey.ID, []uint{channel1.ID, channel2.ID})
	if err != nil {
		t.Fatalf("BindChannels failed: %v", err)
	}

	channels, err := repo.GetChannels(context.Background(), apiKey.ID)
	if err != nil {
		t.Fatalf("GetChannels failed: %v", err)
	}

	if len(channels) != 2 {
		t.Errorf("Expected 2 channel bindings, got %d", len(channels))
	}
}

func TestAPIKeyRepository_GetChannels_Empty(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)
	// No channels bound

	channels, err := repo.GetChannels(context.Background(), apiKey.ID)
	if err != nil {
		t.Fatalf("GetChannels failed: %v", err)
	}

	if len(channels) != 0 {
		t.Errorf("Expected 0 channels, got %d", len(channels))
	}
}

func TestAPIKeyRepository_BindChannels_Replace(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewAPIKeyRepository(db)

	user := test.CreateTestUser(db)
	apiKey := test.CreateTestAPIKey(db, &user.ID)
	channel1 := test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "Channel 1" })
	channel2 := test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "Channel 2" })
	channel3 := test.CreateTestChannel(db, func(c *models.Channel) { c.Name = "Channel 3" })

	// Bind to channel 1 and 2
	repo.BindChannels(context.Background(), apiKey.ID, []uint{channel1.ID, channel2.ID})

	// Replace with only channel 3
	err := repo.BindChannels(context.Background(), apiKey.ID, []uint{channel3.ID})
	if err != nil {
		t.Fatalf("BindChannels failed: %v", err)
	}

	channels, _ := repo.GetChannels(context.Background(), apiKey.ID)
	if len(channels) != 1 {
		t.Errorf("Expected 1 channel after replace, got %d", len(channels))
	}

	if channels[0].ChannelID != channel3.ID {
		t.Errorf("Expected channel ID %d, got %d", channel3.ID, channels[0].ChannelID)
	}
}