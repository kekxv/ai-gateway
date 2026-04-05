package models

import "time"

// Conversation represents a chat conversation
type Conversation struct {
	ID        uint      `json:"id" gorm:"primaryKey"`
	UserID    uint      `json:"user_id" gorm:"index;not null"`
	Title     string    `json:"title" gorm:"type:varchar(255)"`
	Model     string    `json:"model" gorm:"type:varchar(100);not null"`
	SystemPrompt string `json:"system_prompt" gorm:"type:text"`
	Settings  string    `json:"settings" gorm:"type:text"` // JSON string for model settings
	CreatedAt time.Time `json:"created_at" gorm:"autoCreateTime"`
	UpdatedAt time.Time `json:"updated_at" gorm:"autoUpdateTime"`
}

// ConversationSettings holds model settings for a conversation
type ConversationSettings struct {
	Temperature  float64 `json:"temperature,omitempty"`
	MaxTokens    int     `json:"max_tokens,omitempty"`
	TopP         float64 `json:"top_p,omitempty"`
	TopK         int     `json:"top_k,omitempty"`
	FrequencyPenalty float64 `json:"frequency_penalty,omitempty"`
	PresencePenalty  float64 `json:"presence_penalty,omitempty"`
}

// CreateConversationRequest is the request body for creating a conversation
type CreateConversationRequest struct {
	Title       string              `json:"title"`
	Model       string              `json:"model"`
	SystemPrompt string             `json:"system_prompt"`
	Settings    ConversationSettings `json:"settings"`
}

// UpdateConversationRequest is the request body for updating a conversation
type UpdateConversationRequest struct {
	Title       string              `json:"title"`
	Model       string              `json:"model"`
	SystemPrompt string             `json:"system_prompt"`
	Settings    ConversationSettings `json:"settings"`
}