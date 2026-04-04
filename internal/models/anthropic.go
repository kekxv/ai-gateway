package models

import "encoding/json"

// ================================== Anthropic Messages API Types ==================================

// AnthropicMessagesRequest represents Anthropic Messages API request
type AnthropicMessagesRequest struct {
	Model         string                    `json:"model"`
	MaxTokens     int                       `json:"max_tokens"`
	Messages      []AnthropicMessage        `json:"messages"`
	System        AnthropicSystem           `json:"system,omitempty"`
	Stream        bool                      `json:"stream,omitempty"`
	Temperature   float64                   `json:"temperature,omitempty"`
	TopP          float64                   `json:"top_p,omitempty"`
	TopK          int                       `json:"top_k,omitempty"`
	StopSequences []string                  `json:"stop_sequences,omitempty"`
	Tools         []AnthropicTool           `json:"tools,omitempty"`
	ToolChoice    *AnthropicToolChoice      `json:"tool_choice,omitempty"`
	Metadata      map[string]interface{}    `json:"metadata,omitempty"`
}

// AnthropicSystem can be string or array of content blocks
type AnthropicSystem struct {
	StringContent string
	Blocks        []AnthropicContentBlock
}

// UnmarshalJSON handles both string and array formats for system
func (as *AnthropicSystem) UnmarshalJSON(data []byte) error {
	// Try string first
	var str string
	if err := json.Unmarshal(data, &str); err == nil {
		as.StringContent = str
		return nil
	}
	// Try array
	var blocks []AnthropicContentBlock
	if err := json.Unmarshal(data, &blocks); err != nil {
		return err
	}
	as.Blocks = blocks
	return nil
}

// MarshalJSON handles both string and array formats for system
func (as AnthropicSystem) MarshalJSON() ([]byte, error) {
	if as.StringContent != "" && len(as.Blocks) == 0 {
		return json.Marshal(as.StringContent)
	}
	if len(as.Blocks) > 0 {
		return json.Marshal(as.Blocks)
	}
	return json.Marshal("")
}

// GetText extracts text content from the system
func (as AnthropicSystem) GetText() string {
	if as.StringContent != "" {
		return as.StringContent
	}
	// Combine all text blocks
	var result string
	for _, block := range as.Blocks {
		if block.Type == "text" {
			result += block.Text
		}
	}
	return result
}

// IsEmpty checks if the system is empty
func (as AnthropicSystem) IsEmpty() bool {
	return as.StringContent == "" && len(as.Blocks) == 0
}

// AnthropicMessage represents a message in Anthropic format
type AnthropicMessage struct {
	Role    string           `json:"role"`    // "user" or "assistant"
	Content AnthropicContent `json:"content"` // string or array of content blocks
}

// AnthropicContent can be string or array of content blocks
type AnthropicContent struct {
	StringContent string
	Blocks        []AnthropicContentBlock
}

// UnmarshalJSON handles both string and array formats for content
func (ac *AnthropicContent) UnmarshalJSON(data []byte) error {
	// Try string first
	var str string
	if err := json.Unmarshal(data, &str); err == nil {
		ac.StringContent = str
		return nil
	}
	// Try array
	var blocks []AnthropicContentBlock
	if err := json.Unmarshal(data, &blocks); err != nil {
		return err
	}
	ac.Blocks = blocks
	return nil
}

// MarshalJSON handles both string and array formats for content
func (ac AnthropicContent) MarshalJSON() ([]byte, error) {
	if ac.StringContent != "" && len(ac.Blocks) == 0 {
		return json.Marshal(ac.StringContent)
	}
	if len(ac.Blocks) > 0 {
		return json.Marshal(ac.Blocks)
	}
	return json.Marshal("")
}

// IsEmpty checks if the content is empty
func (ac AnthropicContent) IsEmpty() bool {
	return ac.StringContent == "" && len(ac.Blocks) == 0
}

// GetText extracts text content from the content
func (ac AnthropicContent) GetText() string {
	if ac.StringContent != "" {
		return ac.StringContent
	}
	for _, block := range ac.Blocks {
		if block.Type == "text" {
			return block.Text
		}
	}
	return ""
}

// AnthropicContentBlock for multimodal content
type AnthropicContentBlock struct {
	Type   string                  `json:"type"`             // "text", "image", "video", "tool_use", "tool_result"
	Text   string                  `json:"text,omitempty"`   // for text type
	Source *AnthropicMediaSource   `json:"source,omitempty"` // for image/video type

	// Tool use fields
	ID     string                  `json:"id,omitempty"`
	Name   string                  `json:"name,omitempty"`
	Input  map[string]interface{}  `json:"input,omitempty"`

	// Tool result fields
	ToolUseID string               `json:"tool_use_id,omitempty"`
	Content   interface{}          `json:"content,omitempty"`
	IsError   bool                 `json:"is_error,omitempty"`
}

// AnthropicMediaSource for image/video content
type AnthropicMediaSource struct {
	Type      string `json:"type"`                // "base64" or "url"
	MediaType string `json:"media_type,omitempty"` // "image/jpeg", "image/png", "video/mp4", etc.
	Data      string `json:"data,omitempty"`
	URL       string `json:"url,omitempty"`
}

// AnthropicImageSource is an alias for backward compatibility
type AnthropicImageSource = AnthropicMediaSource

// AnthropicTool definition
type AnthropicTool struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	InputSchema map[string]interface{} `json:"input_schema"`
}

// AnthropicToolChoice for tool selection
type AnthropicToolChoice struct {
	Type string `json:"type"` // "auto", "any", "tool"
	Name string `json:"name,omitempty"` // Required when type is "tool"
}

// ================================== Anthropic Response Types ==================================

// AnthropicMessagesResponse represents Anthropic Messages API response
type AnthropicMessagesResponse struct {
	ID           string                    `json:"id"`
	Type         string                    `json:"type"`         // "message"
	Role         string                    `json:"role"`         // "assistant"
	Content      []AnthropicContentBlock   `json:"content"`
	Model        string                    `json:"model"`
	StopReason   string                    `json:"stop_reason"`  // "end_turn", "max_tokens", "stop_sequence", "tool_use"
	StopSequence string                    `json:"stop_sequence,omitempty"`
	Usage        *AnthropicUsage           `json:"usage"`
}

// AnthropicUsage for token tracking
type AnthropicUsage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

// ================================== Anthropic Streaming Types ==================================

// AnthropicStreamEvent represents a streaming event
type AnthropicStreamEvent struct {
	Type         string                    `json:"type"`
	Index        int                       `json:"index,omitempty"`
	Message      *AnthropicMessagesResponse `json:"message,omitempty"`
	ContentBlock *AnthropicContentBlock    `json:"content_block,omitempty"`
	Delta        *AnthropicDelta           `json:"delta,omitempty"`
	Usage        *AnthropicUsage           `json:"usage,omitempty"`
	Error        *AnthropicErrorDetail     `json:"error,omitempty"`
}

// AnthropicDelta for streaming content changes
type AnthropicDelta struct {
	Type       string `json:"type,omitempty"`       // "text_delta", "input_json_delta"
	Text       string `json:"text,omitempty"`
	StopReason string `json:"stop_reason,omitempty"`
}

// AnthropicErrorDetail for error details in streaming
type AnthropicErrorDetail struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

// Stream event type constants
const (
	AnthropicEventMessageStart      = "message_start"
	AnthropicEventContentBlockStart = "content_block_start"
	AnthropicEventContentBlockDelta = "content_block_delta"
	AnthropicEventContentBlockStop  = "content_block_stop"
	AnthropicEventMessageDelta      = "message_delta"
	AnthropicEventMessageStop       = "message_stop"
	AnthropicEventPing              = "ping"
	AnthropicEventError             = "error"
)

// Stop reason constants
const (
	AnthropicStopEndTurn     = "end_turn"
	AnthropicStopMaxTokens   = "max_tokens"
	AnthropicStopSequence    = "stop_sequence"
	AnthropicStopToolUse     = "tool_use"
)

// ================================== Anthropic Error Types ==================================

// AnthropicError represents an Anthropic API error response
type AnthropicError struct {
	Type  string              `json:"type"`
	Error AnthropicErrorDetail `json:"error"`
}

// AnthropicErrorDetail contains the error details
type AnthropicErrorResponse struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

// Error type constants
const (
	AnthropicErrorInvalidRequest  = "invalid_request_error"
	AnthropicErrorAuthentication  = "authentication_error"
	AnthropicErrorPermission      = "permission_error"
	AnthropicErrorNotFound        = "not_found_error"
	AnthropicErrorRateLimit       = "rate_limit_error"
	AnthropicErrorAPI             = "api_error"
	AnthropicErrorOverloaded      = "overloaded_error"
)

// NewAnthropicError creates a new Anthropic error response
func NewAnthropicError(errorType, message string) AnthropicError {
	return AnthropicError{
		Type: "error",
		Error: AnthropicErrorDetail{
			Type:    errorType,
			Message: message,
		},
	}
}