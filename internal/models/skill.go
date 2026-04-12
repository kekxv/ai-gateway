package models

import (
	"time"
)

// Skill represents an Agent Skill following the agentskills.io standard
type Skill struct {
	ID           uint      `gorm:"primaryKey" json:"id"`
	UserID       uint      `gorm:"index;not null" json:"user_id"`
	Name         string    `gorm:"type:varchar(64);uniqueIndex:skill_name_user;not null" json:"name"`
	DisplayName  string    `gorm:"type:varchar(200)" json:"display_name"`
	Description  string    `gorm:"type:text;not null" json:"description"`
	Location     string    `gorm:"type:varchar(500)" json:"location"`
	Instructions string    `gorm:"type:text" json:"instructions"`
	License      string    `gorm:"type:varchar(100)" json:"license"`
	Compatibility string   `gorm:"type:text" json:"compatibility"`
	Metadata     string    `gorm:"type:text" json:"metadata"`
	AllowedTools string    `gorm:"type:text" json:"allowed_tools"`
	Source       string    `gorm:"type:varchar(20);default:database" json:"source"`
	Enabled      bool      `gorm:"default:true;not null" json:"enabled"`
	CreatedAt    time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt    time.Time `gorm:"autoUpdateTime" json:"updated_at"`

	// Associations
	User          *User          `gorm:"foreignKey:UserID" json:"user,omitempty"`
	SkillResources []SkillResource `gorm:"foreignKey:SkillID" json:"resources,omitempty"`
}

func (Skill) TableName() string {
	return "Skill"
}

// SkillResource represents resources associated with a skill (scripts, references, assets)
type SkillResource struct {
	ID        uint      `gorm:"primaryKey" json:"id"`
	SkillID   uint      `gorm:"index;not null" json:"skill_id"`
	Type      string    `gorm:"type:varchar(20);not null" json:"type"`
	Name      string    `gorm:"type:varchar(100);not null" json:"name"`
	Path      string    `gorm:"type:varchar(500)" json:"path"`
	Content   string    `gorm:"type:text" json:"content"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
}

func (SkillResource) TableName() string {
	return "SkillResource"
}

// SkillCatalogItem represents the lightweight catalog view (Tier 1 disclosure)
type SkillCatalogItem struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Location    string `json:"location"`
	Source      string `json:"source"`
	Enabled     bool   `json:"enabled"`
}

// CreateSkillRequest for creating a new skill
type CreateSkillRequest struct {
	Name          string `json:"name" binding:"required"`
	DisplayName   string `json:"display_name"`
	Description   string `json:"description" binding:"required"`
	Location      string `json:"location"`
	Instructions  string `json:"instructions"`
	License       string `json:"license"`
	Compatibility string `json:"compatibility"`
	Metadata      string `json:"metadata"`
	AllowedTools  string `json:"allowed_tools"`
	Source        string `json:"source"`
	Enabled       bool   `json:"enabled"`
}

// UpdateSkillRequest for updating a skill
type UpdateSkillRequest struct {
	DisplayName   string `json:"display_name"`
	Description   string `json:"description"`
	Instructions  string `json:"instructions"`
	License       string `json:"license"`
	Compatibility string `json:"compatibility"`
	Metadata      string `json:"metadata"`
	AllowedTools  string `json:"allowed_tools"`
	Enabled       bool   `json:"enabled"`
}