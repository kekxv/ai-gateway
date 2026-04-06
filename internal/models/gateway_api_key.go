package models

import (
	"time"
)

type GatewayAPIKey struct {
	ID              uint        `gorm:"primaryKey" json:"id"`
	Key             string      `gorm:"unique;not null" json:"key"` // 返回完整 key，前端负责脱敏显示
	Name            string      `gorm:"not null" json:"name"`
	Enabled         bool        `gorm:"not null" json:"enabled"`
	BindToAllChannels bool      `gorm:"column:bindToAllChannels;default:false;not null" json:"bindToAllChannels"`
	LogDetails      bool        `gorm:"column:logDetails;default:true;not null" json:"logDetails"`
	IsChatKey       bool        `gorm:"column:isChatKey;default:false;not null" json:"isChatKey"` // Mark as chat-generated key for logging
	UserID          *uint       `gorm:"column:userId" json:"userId"`
	LastUsed        *time.Time  `gorm:"column:lastUsed" json:"lastUsed"`
	CreatedAt       time.Time   `gorm:"column:createdAt" json:"createdAt"`

	// Associations
	User     *User                  `gorm:"foreignKey:UserID" json:"user,omitempty"`
	Channels []GatewayAPIKeyChannel `gorm:"foreignKey:APIKeyID" json:"-"`
	// For API response - populated separately
	ChannelList []Channel `gorm:"-" json:"channels,omitempty"`
}

func (GatewayAPIKey) TableName() string {
	return "GatewayApiKey"
}