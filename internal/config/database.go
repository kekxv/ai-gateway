package config

import (
	"fmt"

	"github.com/glebarez/sqlite"
	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func InitDatabase(dbPath string) (*gorm.DB, error) {
	config := &gorm.Config{
		Logger: logger.Default.LogMode(logger.Error),
	}

	db, err := gorm.Open(sqlite.Open(dbPath), config)
	if err != nil {
		return nil, fmt.Errorf("failed to connect database: %w", err)
	}

	// Enable foreign keys
	db.Exec("PRAGMA foreign_keys = ON")

	// List of all models
	allModels := []interface{}{
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
	}

	// Only migrate tables that don't exist yet (for backward compatibility)
	var modelsToMigrate []interface{}
	for _, m := range allModels {
		if !db.Migrator().HasTable(m) {
			modelsToMigrate = append(modelsToMigrate, m)
		}
	}

	if len(modelsToMigrate) > 0 {
		err = db.AutoMigrate(modelsToMigrate...)
		if err != nil {
			return nil, fmt.Errorf("failed to migrate database: %w", err)
		}
	}

	return db, nil
}