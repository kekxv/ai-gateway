package test

import (
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

// SetupTestDB creates an in-memory SQLite database for testing
func SetupTestDB(t *testing.T) *gorm.DB {
	// Use shared-cache in-memory SQLite database for tests
	// cache=shared allows multiple connections to share the same in-memory database
	db, err := gorm.Open(sqlite.Open("file::memory:?cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatalf("Failed to connect to test database: %v", err)
	}

	// Auto migrate all models
	err = db.AutoMigrate(
		&models.User{},
		&models.Provider{},
		&models.Channel{},
		&models.Model{},
		&models.ModelRoute{},
		&models.GatewayAPIKey{},
		&models.Log{},
		&models.LogDetail{},
		&models.Settings{},
		&models.SchemaVersion{},
		&models.ChannelProvider{},
		&models.GatewayAPIKeyChannel{},
		&models.ChannelAllowedModel{},
		&models.ProviderModel{},
		&models.ModelAlias{},
		&models.ProviderType{},
		&models.Conversation{},
		&models.Message{},
	)
	if err != nil {
		t.Fatalf("Failed to migrate test database: %v", err)
	}

	return db
}

// CleanupTestDB closes the test database connection
func CleanupTestDB(db *gorm.DB) {
	sqlDB, _ := db.DB()
	sqlDB.Close()
}

// ClearTables clears all data from specified tables
func ClearTables(db *gorm.DB, tables ...interface{}) {
	for _, table := range tables {
		db.Where("1 = 1").Delete(table)
	}
}