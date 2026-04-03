package models

import (
	"time"
)

type LogDetail struct {
	ID           uint      `gorm:"primaryKey" json:"id"`
	LogID        uint      `gorm:"unique;not null;column:logId" json:"logId"`
	RequestBody  []byte    `gorm:"type:blob;column:requestBody" json:"-"`    // GZIP compressed
	ResponseBody []byte    `gorm:"type:blob;column:responseBody" json:"-"`  // GZIP compressed
	CreatedAt    time.Time `gorm:"column:createdAt" json:"createdAt"`
}

func (LogDetail) TableName() string {
	return "LogDetail"
}