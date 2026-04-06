package models

import (
	"encoding/json"
	"strings"
	"time"
)

type Provider struct {
	ID            uint      `gorm:"primaryKey" json:"id"`
	Name          string    `gorm:"unique;not null" json:"name"`
	BaseURL       string    `gorm:"column:baseURL;not null" json:"baseURL"`
	APIKey        string    `gorm:"column:apiKey" json:"-"` // 不直接暴露到 JSON
	Type          string    `gorm:"column:type" json:"type"` // Deprecated: use Types instead
	Types         string    `gorm:"column:types;type:text" json:"types"` // JSON array: ["openai", "anthropic"]
	AutoLoadModels bool     `gorm:"column:autoLoadModels;default:false;not null" json:"autoLoadModels"`
	Disabled      bool      `gorm:"default:false;not null" json:"disabled"`
	UserID        *uint     `gorm:"column:userId" json:"userId"`
	CreatedAt     time.Time `gorm:"column:createdAt" json:"createdAt"`

	// Masked API key for display (not stored in DB)
	APIKeyMasked string `gorm:"-" json:"apiKey"` // 脱敏后显示

	// Computed field (not stored)
	TypesList []string `gorm:"-" json:"typesList"` // For frontend display

	// Associations
	User          *User         `gorm:"foreignKey:UserID" json:"user,omitempty"`
	ProviderModels []ProviderModel `gorm:"foreignKey:ProviderID" json:"-"`
}

func (Provider) TableName() string {
	return "Provider"
}

// GetTypes returns the parsed types array
func (p *Provider) GetTypes() []string {
	if p.Types != "" {
		var types []string
		if err := json.Unmarshal([]byte(p.Types), &types); err == nil {
			return types
		}
	}
	// Fallback to legacy Type field
	if p.Type != "" {
		return []string{p.Type}
	}
	return []string{"openai"} // Default
}

// HasType checks if provider supports a specific type
func (p *Provider) HasType(typeName string) bool {
	for _, t := range p.GetTypes() {
		if strings.ToLower(t) == strings.ToLower(typeName) {
			return true
		}
	}
	return false
}

// SetTypes sets the types array and updates the Types JSON field
func (p *Provider) SetTypes(types []string) {
	if len(types) == 0 {
		p.Types = ""
		p.Type = "openai" // Default
	} else {
		typesJSON, _ := json.Marshal(types)
		p.Types = string(typesJSON)
		p.Type = types[0] // Primary type for backward compatibility
	}
	p.TypesList = types
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