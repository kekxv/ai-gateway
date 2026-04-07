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
		&models.Conversation{},
		&models.Message{},
	}

	// Create tables that don't exist
	for _, m := range allModels {
		if !db.Migrator().HasTable(m) {
			if err := db.AutoMigrate(m); err != nil {
				return nil, fmt.Errorf("failed to create table: %w", err)
			}
		}
	}

	// Manually add new columns for existing tables (avoiding GORM SQLite migration bug)
	// Add requestHeaders column to Log table
	if !columnExists(db, "Log", "requestHeaders") {
		db.Exec("ALTER TABLE `Log` ADD COLUMN `requestHeaders` TEXT")
	}
	// Add responseHeaders column to Log table
	if !columnExists(db, "Log", "responseHeaders") {
		db.Exec("ALTER TABLE `Log` ADD COLUMN `responseHeaders` TEXT")
	}
	// Add types column to Provider table
	if !columnExists(db, "Provider", "types") {
		db.Exec("ALTER TABLE `Provider` ADD COLUMN `types` TEXT")
	}
	// Add isChatKey column to GatewayApiKey table
	if !columnExists(db, "GatewayApiKey", "isChatKey") {
		db.Exec("ALTER TABLE `GatewayApiKey` ADD COLUMN `isChatKey` INTEGER DEFAULT 0 NOT NULL")
	}

	// Fix apiKeyId to allow NULL for chat logs
	// SQLite doesn't support ALTER COLUMN, so we need to recreate the table
	fixLogTableNullableAPIKeyID(db)

	// Add createdAt column to LogDetail if not exists
	if !columnExists(db, "LogDetail", "createdAt") {
		db.Exec("ALTER TABLE `LogDetail` ADD COLUMN `createdAt` DATETIME DEFAULT CURRENT_TIMESTAMP")
	}

	// Add tool_calls column to Message table if not exists
	if !columnExists(db, "messages", "tool_calls") {
		db.Exec("ALTER TABLE `messages` ADD COLUMN `tool_calls` TEXT")
	}

	return db, nil
}

// columnExists checks if a column exists in a table
func columnExists(db *gorm.DB, tableName, columnName string) bool {
	var count int
	// pragma_table_info doesn't support parameterized table names, use string formatting
	db.Raw(fmt.Sprintf("SELECT COUNT(*) FROM pragma_table_info('%s') WHERE name = ?", tableName), columnName).Scan(&count)
	return count > 0
}

// fixLogTableNullableAPIKeyID recreates the Log table with nullable apiKeyId
// SQLite doesn't support ALTER COLUMN, so we need to recreate the table
func fixLogTableNullableAPIKeyID(db *gorm.DB) {
	// Check if the table exists
	if !db.Migrator().HasTable(&models.Log{}) {
		return
	}

	// Check if apiKeyId has NOT NULL constraint
	var notNull int
	db.Raw("SELECT `notnull` FROM pragma_table_info('Log') WHERE name = 'apiKeyId'").Scan(&notNull)
	if notNull == 0 {
		// Already nullable, no need to fix
		return
	}

	// Recreate the table with nullable apiKeyId
	db.Exec(`
		CREATE TABLE IF NOT EXISTS Log_new (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			latency INTEGER NOT NULL DEFAULT 0,
			promptTokens INTEGER NOT NULL DEFAULT 0,
			completionTokens INTEGER NOT NULL DEFAULT 0,
			totalTokens INTEGER NOT NULL DEFAULT 0,
			cost INTEGER NOT NULL DEFAULT 0,
			status INTEGER NOT NULL DEFAULT 200,
			errorMessage TEXT,
			apiKeyId INTEGER,
			modelName TEXT,
			providerName TEXT,
			ownerChannelId INTEGER,
			ownerChannelUserId INTEGER,
			requestHeaders TEXT,
			responseHeaders TEXT,
			createdAt DATETIME
		)
	`)

	// Copy data from old table
	db.Exec(`
		INSERT INTO Log_new (id, latency, promptTokens, completionTokens, totalTokens, cost, status, errorMessage, apiKeyId, modelName, providerName, ownerChannelId, ownerChannelUserId, requestHeaders, responseHeaders, createdAt)
		SELECT id, latency, promptTokens, completionTokens, totalTokens, cost, status, errorMessage, apiKeyId, modelName, providerName, ownerChannelId, ownerChannelUserId, requestHeaders, responseHeaders, createdAt FROM Log
	`)

	// Drop old table
	db.Exec(`DROP TABLE Log`)

	// Rename new table
	db.Exec(`ALTER TABLE Log_new RENAME TO Log`)

	// Recreate index
	db.Exec(`CREATE INDEX IF NOT EXISTS idx_log_api_key_id ON Log(apiKeyId)`)
	db.Exec(`CREATE INDEX IF NOT EXISTS idx_log_created_at ON Log(createdAt)`)
}