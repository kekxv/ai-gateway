package models

import (
	"time"
)

type Model struct {
	ID               uint      `gorm:"primaryKey" json:"id"`
	Name             string    `gorm:"unique;not null" json:"name"`
	Alias            string    `gorm:"column:alias" json:"alias"`
	Description      string    `gorm:"column:description" json:"description"`
	InputTokenPrice  int64     `gorm:"column:inputTokenPrice" json:"inputTokenPrice"`
	OutputTokenPrice int64     `gorm:"column:outputTokenPrice" json:"outputTokenPrice"`
	UserID           *uint     `gorm:"column:userId" json:"userId"`
	CreatedAt        time.Time `gorm:"column:createdAt" json:"createdAt"`
	UpdatedAt        time.Time `gorm:"column:updatedAt" json:"updatedAt"`

	// Associations
	ModelRoutes []ModelRoute `gorm:"foreignKey:ModelID" json:"modelRoutes,omitempty"`
	Aliases     []string     `gorm:"-" json:"aliases,omitempty"`
}

func (Model) TableName() string {
	return "Model"
}