package models

import "encoding/json"

// ResponseRequest represents the OpenAI Responses API request
type ResponseRequest struct {
	Model              string                 `json:"model"`
	Input              ResponseInput          `json:"input"`
	Instructions       string                 `json:"instructions,omitempty"`
	PreviousResponseID string                 `json:"previous_response_id,omitempty"`
	Tools              []ResponseTool         `json:"tools,omitempty"`
	ToolChoice         interface{}            `json:"tool_choice,omitempty"` // "none", "auto", "required", or specific tool
	Stream             bool                   `json:"stream,omitempty"`
	Temperature        *float64               `json:"temperature,omitempty"`
	TopP               *float64               `json:"top_p,omitempty"`
	MaxOutputTokens    int                    `json:"max_output_tokens,omitempty"`
	MaxToolCalls       int                    `json:"max_tool_calls,omitempty"`
	Metadata           map[string]interface{} `json:"metadata,omitempty"`
	Store              *bool                  `json:"store,omitempty"`
	Background         bool                   `json:"background,omitempty"`
	Conversation       *ConversationConfig    `json:"conversation,omitempty"`
	ParallelToolCalls  *bool                  `json:"parallel_tool_calls,omitempty"`
	Reasoning          *ReasoningConfig       `json:"reasoning,omitempty"`
	Truncation         string                 `json:"truncation,omitempty"` // "auto" or "disabled"
	Text               *ResponseTextConfig    `json:"text,omitempty"`
	TopLogprobs        int                    `json:"top_logprobs,omitempty"`
	User               string                 `json:"user,omitempty"`
	Include            []string               `json:"include,omitempty"`
	ServiceTier        string                 `json:"service_tier,omitempty"`
	SafetyIdentifier   string                 `json:"safety_identifier,omitempty"`
	PromptCacheKey     string                 `json:"prompt_cache_key,omitempty"`
	Verbosity          string                 `json:"verbosity,omitempty"` // "low", "medium", "high"
}

// ResponseInput can be a string or array of input items
type ResponseInput struct {
	StringInput string
	Items       []ResponseInputItem
}

// UnmarshalJSON handles both string and array formats for input
func (ri *ResponseInput) UnmarshalJSON(data []byte) error {
	// Try string first
	var str string
	if err := json.Unmarshal(data, &str); err == nil {
		ri.StringInput = str
		return nil
	}
	// Try array
	var items []ResponseInputItem
	if err := json.Unmarshal(data, &items); err != nil {
		return err
	}
	ri.Items = items
	return nil
}

// MarshalJSON handles both string and array formats for input
func (ri ResponseInput) MarshalJSON() ([]byte, error) {
	if ri.StringInput != "" && len(ri.Items) == 0 {
		return json.Marshal(ri.StringInput)
	}
	if len(ri.Items) > 0 {
		return json.Marshal(ri.Items)
	}
	// Empty input
	return json.Marshal("")
}

// IsEmpty checks if the input is empty
func (ri ResponseInput) IsEmpty() bool {
	return ri.StringInput == "" && len(ri.Items) == 0
}

// ResponseInputItem represents an item in the input array
type ResponseInputItem struct {
	Type      string          `json:"type,omitempty"`       // "message", "function_call", "function_call_output", etc.
	Role      string          `json:"role,omitempty"`       // "user", "assistant", "system", "developer"
	Content   ResponseContent `json:"content,omitempty"`    // string or []ContentPart
	Status    string          `json:"status,omitempty"`     // "in_progress", "completed", "incomplete"
	ID        string          `json:"id,omitempty"`
	CallID    string          `json:"call_id,omitempty"`
	Name      string          `json:"name,omitempty"`
	Arguments string          `json:"arguments,omitempty"`
	Output    string          `json:"output,omitempty"`
	Phase     string          `json:"phase,omitempty"`      // "commentary" or "final_answer"
}

// ResponseContent can be a string or array of content parts
type ResponseContent struct {
	StringContent string
	Parts         []ContentPart
}

// UnmarshalJSON handles both string and array formats for content
func (rc *ResponseContent) UnmarshalJSON(data []byte) error {
	// Try string first
	var str string
	if err := json.Unmarshal(data, &str); err == nil {
		rc.StringContent = str
		return nil
	}
	// Try array
	var parts []ContentPart
	if err := json.Unmarshal(data, &parts); err != nil {
		return err
	}
	rc.Parts = parts
	return nil
}

// MarshalJSON handles both string and array formats for content
func (rc ResponseContent) MarshalJSON() ([]byte, error) {
	if rc.StringContent != "" && len(rc.Parts) == 0 {
		return json.Marshal(rc.StringContent)
	}
	if len(rc.Parts) > 0 {
		return json.Marshal(rc.Parts)
	}
	return json.Marshal("")
}

// ContentPart for multimodal content
type ContentPart struct {
	Type     string `json:"type"`              // "input_text", "input_image", "input_file"
	Text     string `json:"text,omitempty"`
	ImageURL string `json:"image_url,omitempty"`
	FileID   string `json:"file_id,omitempty"`
	FileURL  string `json:"file_url,omitempty"`
	FileData string `json:"file_data,omitempty"`
	Filename string `json:"filename,omitempty"`
	Detail   string `json:"detail,omitempty"`  // "auto", "low", "high", "original"
}

// ResponseTool definition
type ResponseTool struct {
	Type     string       `json:"type"`              // "function", "code_interpreter", "file_search", "web_search_preview", "mcp"
	Function *FunctionDef `json:"function,omitempty"`
}

// FunctionDef for function tool
type FunctionDef struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	Parameters  map[string]interface{} `json:"parameters,omitempty"`
	Strict      bool                   `json:"strict,omitempty"`
}

// ConversationConfig for conversation settings
type ConversationConfig struct {
	ID string `json:"id,omitempty"` // The unique ID of the conversation
}

// ReasoningConfig for reasoning models
type ReasoningConfig struct {
	Effort           string `json:"effort,omitempty"`           // "low", "medium", "high"
	GenerateSummary  string `json:"generate_summary,omitempty"` // "auto" or "always"
	Summary          string `json:"summary,omitempty"`          // "auto" or "concise"
}

// ResponseTextConfig for text output configuration
type ResponseTextConfig struct {
	Format    *TextFormat `json:"format,omitempty"`
	Verbosity string      `json:"verbosity,omitempty"` // "low", "medium", "high"
}

// TextFormat for output format configuration
type TextFormat struct {
	Type       string                 `json:"type"` // "text" or "json_schema"
	JsonSchema map[string]interface{} `json:"json_schema,omitempty"`
}

// ================================== Response Types ==================================

// Response represents the OpenAI Responses API response
type Response struct {
	ID                 string                 `json:"id"`
	Object             string                 `json:"object"`           // "response"
	CreatedAt          int64                  `json:"created_at"`
	Status             string                 `json:"status"`           // "queued", "in_progress", "completed", "failed", "cancelled"
	CompletedAt        *int64                 `json:"completed_at,omitempty"`
	Model              string                 `json:"model"`
	Output             []ResponseOutput       `json:"output"`
	Usage              *ResponseUsage         `json:"usage,omitempty"`
	PreviousResponseID string                 `json:"previous_response_id,omitempty"`
	Instructions       string                 `json:"instructions,omitempty"`
	Error              *ResponseError         `json:"error,omitempty"`
	Metadata           map[string]interface{} `json:"metadata,omitempty"`
	Background         bool                   `json:"background,omitempty"`
	MaxOutputTokens    int                    `json:"max_output_tokens,omitempty"`
	MaxToolCalls       int                    `json:"max_tool_calls,omitempty"`
	ParallelToolCalls  bool                   `json:"parallel_tool_calls,omitempty"`
	Temperature        float64                `json:"temperature,omitempty"`
	ToolChoice         interface{}            `json:"tool_choice,omitempty"`
	Tools              []ResponseTool         `json:"tools,omitempty"`
	TopP               float64                `json:"top_p,omitempty"`
	Truncation         string                 `json:"truncation,omitempty"`
	Store              bool                   `json:"store,omitempty"`
	Reasoning          *ReasoningConfig       `json:"reasoning,omitempty"`
	Text               *ResponseTextConfig    `json:"text,omitempty"`
	TopLogprobs        int                    `json:"top_logprobs,omitempty"`
	User               string                 `json:"user,omitempty"`
	ServiceTier        string                 `json:"service_tier,omitempty"`
	SafetyIdentifier   string                 `json:"safety_identifier,omitempty"`
	PromptCacheKey     string                 `json:"prompt_cache_key,omitempty"`
	IncompleteDetails  *IncompleteDetails     `json:"incomplete_details,omitempty"`
	Conversation       *ConversationConfig    `json:"conversation,omitempty"`
	OutputText         string                 `json:"output_text,omitempty"` // SDK convenience property
}

// ResponseOutput represents an output item
type ResponseOutput struct {
	Type      string          `json:"type"`       // "message", "function_call", "function_call_output", "reasoning", etc.
	ID        string          `json:"id"`
	Status    string          `json:"status"`     // "in_progress", "completed", "incomplete"
	Role      string          `json:"role,omitempty"`
	Content   []OutputContent `json:"content,omitempty"`
	CallID    string          `json:"call_id,omitempty"`
	Name      string          `json:"name,omitempty"`
	Arguments string          `json:"arguments,omitempty"`
	Output    string          `json:"output,omitempty"`
	Summary   string          `json:"summary,omitempty"`
	Phase     string          `json:"phase,omitempty"`  // "commentary" or "final_answer"
	CreatedBy string          `json:"created_by,omitempty"`
}

// OutputContent for output content parts
type OutputContent struct {
	Type        string       `json:"type"`           // "output_text", "refusal"
	Text        string       `json:"text,omitempty"`
	Annotations []Annotation `json:"annotations,omitempty"`
	Logprobs    []Logprob    `json:"logprobs,omitempty"`
	Refusal     string       `json:"refusal,omitempty"`
}

// Annotation for citations/references
type Annotation struct {
	Type        string `json:"type"`        // "file_citation", "url_citation", "container_file_citation", "file_path"
	FileID      string `json:"file_id,omitempty"`
	Filename    string `json:"filename,omitempty"`
	URL         string `json:"url,omitempty"`
	Title       string `json:"title,omitempty"`
	StartIndex  int    `json:"start_index,omitempty"`
	EndIndex    int    `json:"end_index,omitempty"`
	Index       int    `json:"index,omitempty"`
	ContainerID string `json:"container_id,omitempty"`
}

// Logprob for token log probabilities
type Logprob struct {
	Token       string        `json:"token"`
	Bytes       []int         `json:"bytes,omitempty"`
	Logprob     float64       `json:"logprob"`
	TopLogprobs []TopLogprob  `json:"top_logprobs,omitempty"`
}

// TopLogprob for top log probability entries
type TopLogprob struct {
	Token   string  `json:"token"`
	Bytes   []int   `json:"bytes,omitempty"`
	Logprob float64 `json:"logprob"`
}

// ResponseUsage tracks token usage
type ResponseUsage struct {
	InputTokens       int                `json:"input_tokens"`
	OutputTokens      int                `json:"output_tokens"`
	TotalTokens       int                `json:"total_tokens"`
	InputTokensDetails  *InputTokensDetails  `json:"input_tokens_details,omitempty"`
	OutputTokensDetails *OutputTokensDetails `json:"output_tokens_details,omitempty"`
}

// InputTokensDetails for detailed input token breakdown
type InputTokensDetails struct {
	CachedTokens int `json:"cached_tokens"`
}

// OutputTokensDetails for detailed output token breakdown
type OutputTokensDetails struct {
	ReasoningTokens int `json:"reasoning_tokens"`
}

// ResponseError for error responses
type ResponseError struct {
	Type    string `json:"type"`
	Message string `json:"message"`
	Code    string `json:"code,omitempty"`
}

// IncompleteDetails for incomplete response details
type IncompleteDetails struct {
	Reason string `json:"reason"` // "max_output_tokens", "content_filter", etc.
}

// ================================== Streaming Event Types ==================================

// ResponseStreamEvent represents a streaming event
type ResponseStreamEvent struct {
	Type         string          `json:"type"`
	Response     *Response       `json:"response,omitempty"`
	Item         *ResponseOutput `json:"item,omitempty"`
	Part         *OutputContent  `json:"part,omitempty"`
	Delta        string          `json:"delta,omitempty"`
	OutputIndex  int             `json:"output_index,omitempty"`
	ContentIndex int             `json:"content_index,omitempty"`
	ItemID       string          `json:"item_id,omitempty"`
	SequenceNumber int           `json:"sequence_number,omitempty"`
	Obfuscation  string          `json:"obfuscation,omitempty"`
}

// Event type constants for Responses API streaming
const (
	EventResponseCreated           = "response.created"
	EventResponseInProgress        = "response.in_progress"
	EventResponseQueued            = "response.queued"
	EventResponseOutputItemAdded   = "response.output_item.added"
	EventResponseContentPartAdded  = "response.content_part.added"
	EventResponseOutputTextDelta   = "response.output_text.delta"
	EventResponseOutputTextDone    = "response.output_text.done"
	EventResponseContentPartDone   = "response.content_part.done"
	EventResponseOutputItemDone    = "response.output_item.done"
	EventResponseCompleted         = "response.completed"
	EventResponseFailed            = "response.failed"
	EventResponseCancelled         = "response.cancelled"
	EventResponseError            = "response.error"
)

// ================================== Compact Request ==================================

// CompactRequest for POST /responses/compact
type CompactRequest struct {
	Input        ResponseInput `json:"input,omitempty"`
	Model        string        `json:"model,omitempty"`
	Instructions string        `json:"instructions,omitempty"`
}

// ================================== Delete Response ==================================

// DeleteResponse for DELETE response
type DeleteResponse struct {
	ID      string `json:"id"`
	Object  string `json:"object"` // "response"
	Deleted bool   `json:"deleted"`
}

// ================================== Cancel Response ==================================

// CancelResponse for POST /responses/:id/cancel
type CancelResponse struct {
	ID     string `json:"id"`
	Object string `json:"object"` // "response"
	Status string `json:"status"` // "cancelled"
}