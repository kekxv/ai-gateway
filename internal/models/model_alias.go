package models

import (
	"time"
)

// ModelAlias represents an alias for a model
// Each model has at least one alias (its name), and can have additional aliases
type ModelAlias struct {
	ModelID   uint      `gorm:"primaryKey;column:modelId;not null;index"`
	Alias     string    `gorm:"primaryKey;column:alias;not null;size:255"`
	CreatedAt time.Time `gorm:"column:createdAt;autoCreateTime"`
}

func (ModelAlias) TableName() string {
	return "ModelAlias"
}