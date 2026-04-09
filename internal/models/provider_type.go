package models

import (
	"time"
)

// ProviderType represents a type-specific configuration for a provider
// Each provider can have multiple types with different base URLs
type ProviderType struct {
	ProviderID uint      `gorm:"primaryKey;column:providerId;not null;index"`
	Type       string    `gorm:"primaryKey;column:type;not null;size:64"`
	BaseURL    string    `gorm:"column:baseURL;not null"`
	CreatedAt  time.Time `gorm:"column:createdAt;autoCreateTime"`

	// Association (not stored in JSON response by default)
	Provider Provider `gorm:"foreignKey:ProviderID" json:"-"`
}

func (ProviderType) TableName() string {
	return "ProviderType"
}