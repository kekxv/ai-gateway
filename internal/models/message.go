package models

import (
	"encoding/json"
	"time"
)

// Message represents a single message in a conversation
type Message struct {
	ID             uint      `json:"id" gorm:"primaryKey"`
	ConversationID uint      `json:"conversation_id" gorm:"index;not null"`
	Role           string    `json:"role" gorm:"type:varchar(20);not null"` // user, assistant, system
	Content        string    `json:"content" gorm:"type:text;not null"`
	ToolCalls      string    `json:"tool_calls,omitempty" gorm:"type:text"` // JSON-encoded tool calls
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

// ToolDefinition represents a tool definition for function calling
type ToolDefinition struct {
	Type     string           `json:"type"` // "function"
	Function ToolFunctionSpec `json:"function"`
}

// ToolFunctionSpec represents the function specification
type ToolFunctionSpec struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	Parameters  map[string]interface{} `json:"parameters"` // JSON Schema
}

// ChatRequest is the request body for sending a message
type ChatRequest struct {
	Content           string               `json:"content"`
	Parts             []ChatContentPart    `json:"parts,omitempty"`    // For multimodal content
	Messages          []ChatRequestMessage `json:"messages,omitempty"` // For full chat history (regenerate)
	Stream            bool                 `json:"stream"`
	Settings          ConversationSettings `json:"settings,omitempty"` // optional override settings
	Tools             []ToolDefinition     `json:"tools,omitempty"`    // optional tools for function calling
	DeleteAfterID     *uint                `json:"delete_after_id,omitempty"` // for regenerate: delete messages after this ID (nil = no delete, 0 = delete all)
}

// ChatRequestMessage represents a message in the chat history
type ChatRequestMessage struct {
	Role      string          `json:"role"`
	Content   json.RawMessage `json:"content"`    // Raw JSON to support string or array format
	ToolCalls json.RawMessage `json:"tool_calls,omitempty"`
}

// ChatStreamEvent represents a streaming event
type ChatStreamEvent struct {
	Type    string `json:"type"` // content, done, error
	Content string `json:"content,omitempty"`
	Error   string `json:"error,omitempty"`
}