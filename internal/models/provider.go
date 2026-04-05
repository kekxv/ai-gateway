package models

import (
	"time"
)

type Provider struct {
	ID            uint      `gorm:"primaryKey" json:"id"`
	Name          string    `gorm:"unique;not null" json:"name"`
	BaseURL       string    `gorm:"column:baseURL;not null" json:"baseURL"`
	APIKey        string    `gorm:"column:apiKey" json:"-"` // 不直接暴露到 JSON
	Type          string    `json:"type"`
	AutoLoadModels bool     `gorm:"column:autoLoadModels;default:false;not null" json:"autoLoadModels"`
	Disabled      bool      `gorm:"default:false;not null" json:"disabled"`
	UserID        *uint     `gorm:"column:userId" json:"userId"`
	CreatedAt     time.Time `gorm:"column:createdAt" json:"createdAt"`

	// Masked API key for display (not stored in DB)
	APIKeyMasked string `gorm:"-" json:"apiKey"` // 脱敏后显示

	// Associations
	User          *User         `gorm:"foreignKey:UserID" json:"user,omitempty"`
	ProviderModels []ProviderModel `gorm:"foreignKey:ProviderID" json:"-"`
}

func (Provider) TableName() string {
	return "Provider"
}

// MaskAPIKey returns a masked version of the API key for display
// Format: prefix(8) + "..." + suffix(4), e.g., "sk-abc123...xyz7"
func MaskAPIKey(key string) string {
	if key == "" {
		return ""
	}

	prefixLen := 8
	suffixLen := 4

	if len(key) <= prefixLen+suffixLen {
		// Key too short, show only prefix and suffix with less characters
		if len(key) <= 4 {
			return "****"
		}
		return key[:2] + "****" + key[len(key)-2:]
	}

	return key[:prefixLen] + "..." + key[len(key)-suffixLen:]
}