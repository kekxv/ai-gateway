package models

import (
	"time"
)

type User struct {
	ID          uint       `gorm:"primaryKey" json:"id"`
	Email       string     `gorm:"unique;not null" json:"email"`
	Password    string     `gorm:"not null" json:"-"`
	Role        string     `gorm:"default:USER;not null" json:"role"`
	Disabled    bool       `gorm:"default:false;not null" json:"disabled"`
	ValidUntil  *time.Time `gorm:"column:validUntil" json:"validUntil"`
	Balance     int64      `gorm:"default:0;not null" json:"balance"`
	TOTPSecret  string     `gorm:"column:totpSecret" json:"-"`
	TOTPEnabled bool       `gorm:"column:totpEnabled;default:false;not null" json:"totpEnabled"`
	CreatedAt   time.Time  `gorm:"column:createdAt" json:"createdAt"`
}

func (User) TableName() string {
	return "User"
}