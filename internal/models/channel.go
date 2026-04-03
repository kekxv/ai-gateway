package models

import (
	"time"
)

type Channel struct {
	ID        uint      `gorm:"primaryKey" json:"id"`
	Name      string    `gorm:"unique;not null" json:"name"`
	Enabled   bool      `gorm:"default:true;not null" json:"enabled"`
	Shared    bool      `gorm:"default:false;not null" json:"shared"`
	UserID    *uint     `gorm:"column:userId" json:"userId"`
	CreatedAt time.Time `gorm:"column:createdAt" json:"createdAt"`
	UpdatedAt time.Time `gorm:"column:updatedAt" json:"updatedAt"`

	// Associations
	User          *User               `gorm:"foreignKey:UserID" json:"user,omitempty"`
	Providers     []ChannelProvider   `gorm:"foreignKey:ChannelID" json:"-"`
	AllowedModels []ChannelAllowedModel `gorm:"foreignKey:ChannelID" json:"-"`
}

func (Channel) TableName() string {
	return "Channel"
}