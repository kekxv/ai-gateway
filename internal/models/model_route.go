package models

import (
	"time"
)

type ModelRoute struct {
	ID           uint        `gorm:"primaryKey" json:"id"`
	ModelID      uint        `gorm:"column:modelId;not null;index" json:"modelId"`
	ProviderID   uint        `gorm:"column:providerId;not null;index" json:"providerId"`
	Weight       int         `gorm:"default:1;not null" json:"weight"`
	Disabled     bool        `gorm:"default:false;not null" json:"disabled"`
	DisabledUntil *time.Time `gorm:"column:disabledUntil" json:"disabledUntil"`
	CreatedAt    time.Time   `gorm:"column:createdAt" json:"createdAt"`

	// Associations
	Model    Model    `gorm:"foreignKey:ModelID" json:"model,omitempty"`
	Provider Provider `gorm:"foreignKey:ProviderID" json:"provider,omitempty"`
}

func (ModelRoute) TableName() string {
	return "ModelRoute"
}