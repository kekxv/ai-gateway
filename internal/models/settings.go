package models

import "time"

type Settings struct {
	Key   string `gorm:"primaryKey" json:"key"`
	Value string `gorm:"not null" json:"value"`
}

func (Settings) TableName() string {
	return "Settings"
}

type SchemaVersion struct {
	Version   int       `gorm:"primaryKey" json:"version"`
	AppliedAt time.Time `gorm:"default:CURRENT_TIMESTAMP" json:"appliedAt"`
}

func (SchemaVersion) TableName() string {
	return "SchemaVersion"
}