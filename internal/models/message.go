package models

import "time"

// Message represents a single message in a conversation
type Message struct {
	ID             uint      `json:"id" gorm:"primaryKey"`
	ConversationID uint      `json:"conversation_id" gorm:"index;not null"`
	Role           string    `json:"role" gorm:"type:varchar(20);not null"` // user, assistant, system
	Content        string    `json:"content" gorm:"type:text;not null"`
	Tokens         int       `json:"tokens"` // token count for this message
	CreatedAt      time.Time `json:"created_at" gorm:"autoCreateTime"`
}

// ChatContentPart represents a part of multimodal content
type ChatContentPart struct {
	Type     string            `json:"type"`           // "text", "image_url"
	Text     string            `json:"text,omitempty"` // For type "text"
	ImageURL *ChatMediaURL     `json:"image_url,omitempty"`
}

// ChatMediaURL represents a media URL or base64 data
type ChatMediaURL struct {
	URL    string `json:"url"`
	Detail string `json:"detail,omitempty"` // "auto", "low", "high" (for images)
}

// ChatRequest is the request body for sending a message
type ChatRequest struct {
	Content  string              `json:"content"`
	Parts    []ChatContentPart   `json:"parts,omitempty"` // For multimodal content
	Stream   bool                `json:"stream"`
	Settings ConversationSettings `json:"settings,omitempty"` // optional override settings
}

// ChatStreamEvent represents a streaming event
type ChatStreamEvent struct {
	Type    string `json:"type"` // content, done, error
	Content string `json:"content,omitempty"`
	Error   string `json:"error,omitempty"`
}