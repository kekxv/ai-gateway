package models

import (
	"time"
)

type Provider struct {
	ID            uint      `gorm:"primaryKey" json:"id"`
	Name          string    `gorm:"unique;not null" json:"name"`
	BaseURL       string    `gorm:"column:baseURL;not null" json:"baseURL"`
	APIKey        string    `gorm:"column:apiKey" json:"apiKey"`
	Type          string    `json:"type"`
	AutoLoadModels bool     `gorm:"column:autoLoadModels;default:false;not null" json:"autoLoadModels"`
	Disabled      bool      `gorm:"default:false;not null" json:"disabled"`
	UserID        *uint     `gorm:"column:userId" json:"userId"`
	CreatedAt     time.Time `gorm:"column:createdAt" json:"createdAt"`

	// Associations
	User          *User         `gorm:"foreignKey:UserID" json:"user,omitempty"`
	ProviderModels []ProviderModel `gorm:"foreignKey:ProviderID" json:"-"`
}

func (Provider) TableName() string {
	return "Provider"
}