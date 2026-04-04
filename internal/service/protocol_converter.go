package service

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/kekxv/ai-gateway/internal/models"
)

// ProtocolType represents the protocol type for API requests
type ProtocolType string

const (
	ProtocolOpenAI    ProtocolType = "openai"
	ProtocolAnthropic ProtocolType = "anthropic"
	ProtocolGemini    ProtocolType = "gemini"
)

// GetProviderProtocol converts provider type string to ProtocolType
func GetProviderProtocol(providerType string) ProtocolType {
	switch strings.ToLower(providerType) {
	case "anthropic", "claude":
		return ProtocolAnthropic
	case "gemini":
		return ProtocolGemini
	default:
		return ProtocolOpenAI
	}
}

// ProtocolConverter handles conversion between different API protocols
type ProtocolConverter struct{}

// NewProtocolConverter creates a new protocol converter
func NewProtocolConverter() *ProtocolConverter {
	return &ProtocolConverter{}
}

// ConvertRequest converts a request from one protocol to another
func (c *ProtocolConverter) ConvertRequest(req interface{}, from, to ProtocolType) (interface{}, error) {
	if from == to {
		return req, nil
	}

	switch {
	case from == ProtocolOpenAI && to == ProtocolAnthropic:
		return c.openAIToAnthropicRequest(req.(*ChatRequest))
	case from == ProtocolAnthropic && to == ProtocolOpenAI:
		return c.anthropicToOpenAIRequest(req.(*models.AnthropicMessagesRequest))
	default:
		return nil, fmt.Errorf("unsupported protocol conversion: %s -> %s", from, to)
	}
}

// ConvertResponse converts a response from one protocol to another
func (c *ProtocolConverter) ConvertResponse(resp interface{}, from, to ProtocolType, modelName string) (interface{}, error) {
	if from == to {
		return resp, nil
	}

	switch {
	case from == ProtocolOpenAI && to == ProtocolAnthropic:
		return c.openAIToAnthropicResponse(resp.(*ChatResponse), modelName)
	case from == ProtocolAnthropic && to == ProtocolOpenAI:
		return c.anthropicToOpenAIResponse(resp.(*models.AnthropicMessagesResponse))
	default:
		return nil, fmt.Errorf("unsupported protocol conversion: %s -> %s", from, to)
	}
}

// OpenAI -> Anthropic Request Conversion
func (c *ProtocolConverter) openAIToAnthropicRequest(req *ChatRequest) (*models.AnthropicMessagesRequest, error) {
	anthropicReq := &models.AnthropicMessagesRequest{
		Model:       req.Model,
		MaxTokens:   req.MaxTokens,
		Stream:      req.Stream,
		Temperature: req.Temperature,
	}

	// Handle extra fields
	if req.Extra != nil {
		if topP, ok := req.Extra["top_p"].(float64); ok {
			anthropicReq.TopP = topP
		}
		if stop, ok := req.Extra["stop"].([]interface{}); ok {
			for _, s := range stop {
				if str, ok := s.(string); ok {
					anthropicReq.StopSequences = append(anthropicReq.StopSequences, str)
				}
			}
		}
	}

	// Convert messages - extract system message separately
	var messages []models.AnthropicMessage
	for _, msg := range req.Messages {
		if msg.Role == "system" {
			anthropicReq.System = msg.Content
		} else {
			messages = append(messages, models.AnthropicMessage{
				Role:    msg.Role,
				Content: models.AnthropicContent{StringContent: msg.Content},
			})
		}
	}
	anthropicReq.Messages = messages

	return anthropicReq, nil
}

// Anthropic -> OpenAI Request Conversion
func (c *ProtocolConverter) anthropicToOpenAIRequest(req *models.AnthropicMessagesRequest) (*ChatRequest, error) {
	openAIReq := &ChatRequest{
		Model:       req.Model,
		MaxTokens:   req.MaxTokens,
		Stream:      req.Stream,
		Temperature: req.Temperature,
		Extra:       make(map[string]interface{}),
	}

	// Add optional fields
	if req.TopP > 0 {
		openAIReq.Extra["top_p"] = req.TopP
	}
	if len(req.StopSequences) > 0 {
		openAIReq.Extra["stop"] = req.StopSequences
	}

	// Build messages - add system message first if present
	var messages []ChatMessage
	if req.System != "" {
		messages = append(messages, ChatMessage{
			Role:    "system",
			Content: req.System,
		})
	}

	// Convert messages
	for _, msg := range req.Messages {
		content := msg.Content.GetText()
		messages = append(messages, ChatMessage{
			Role:    msg.Role,
			Content: content,
		})
	}
	openAIReq.Messages = messages

	return openAIReq, nil
}

// OpenAI -> Anthropic Response Conversion
func (c *ProtocolConverter) openAIToAnthropicResponse(resp *ChatResponse, modelName string) (*models.AnthropicMessagesResponse, error) {
	anthropicResp := &models.AnthropicMessagesResponse{
		ID:    generateMessageID(),
		Type:  "message",
		Role:  "assistant",
		Model: modelName,
	}

	// Convert choices to content blocks
	var content []models.AnthropicContentBlock
	var stopReason string

	if len(resp.Choices) > 0 {
		choice := resp.Choices[0]
		if choice.Message != nil {
			content = append(content, models.AnthropicContentBlock{
				Type: "text",
				Text: choice.Message.Content,
			})
		}
		stopReason = convertFinishReasonToAnthropic(choice.FinishReason)
	}
	anthropicResp.Content = content
	anthropicResp.StopReason = stopReason

	// Convert usage
	if resp.Usage != nil {
		anthropicResp.Usage = &models.AnthropicUsage{
			InputTokens:  resp.Usage.PromptTokens,
			OutputTokens: resp.Usage.CompletionTokens,
		}
	}

	return anthropicResp, nil
}

// Anthropic -> OpenAI Response Conversion
func (c *ProtocolConverter) anthropicToOpenAIResponse(resp *models.AnthropicMessagesResponse) (*ChatResponse, error) {
	openAIResp := &ChatResponse{
		ID:     resp.ID,
		Object: "chat.completion",
		Model:  resp.Model,
	}

	// Convert content to message
	var content string
	for _, block := range resp.Content {
		if block.Type == "text" {
			content += block.Text
		}
	}

	openAIResp.Choices = []Choice{
		{
			Index: 0,
			Message: &ChatMessage{
				Role:    "assistant",
				Content: content,
			},
			FinishReason: convertStopReasonToOpenAI(resp.StopReason),
		},
	}

	// Convert usage
	if resp.Usage != nil {
		openAIResp.Usage = &Usage{
			PromptTokens:     resp.Usage.InputTokens,
			CompletionTokens: resp.Usage.OutputTokens,
			TotalTokens:      resp.Usage.InputTokens + resp.Usage.OutputTokens,
		}
	}

	return openAIResp, nil
}

// GenerateAnthropicStreamStart generates the initial message_start event
func (c *ProtocolConverter) GenerateAnthropicStreamStart(messageID, modelName string) string {
	event := models.AnthropicStreamEvent{
		Type: models.AnthropicEventMessageStart,
		Message: &models.AnthropicMessagesResponse{
			ID:      messageID,
			Type:    "message",
			Role:    "assistant",
			Content: []models.AnthropicContentBlock{},
			Model:   modelName,
		},
	}
	return formatSSE(models.AnthropicEventMessageStart, event)
}

// GenerateAnthropicContentBlockStart generates content_block_start event
func (c *ProtocolConverter) GenerateAnthropicContentBlockStart(index int) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockStart,
		Index: index,
		ContentBlock: &models.AnthropicContentBlock{
			Type: "text",
			Text: "",
		},
	}
	return formatSSE(models.AnthropicEventContentBlockStart, event)
}

// GenerateAnthropicContentDelta generates content_block_delta event
func (c *ProtocolConverter) GenerateAnthropicContentDelta(index int, text string) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockDelta,
		Index: index,
		Delta: &models.AnthropicDelta{
			Type: "text_delta",
			Text: text,
		},
	}
	return formatSSE(models.AnthropicEventContentBlockDelta, event)
}

// GenerateAnthropicContentBlockStop generates content_block_stop event
func (c *ProtocolConverter) GenerateAnthropicContentBlockStop(index int) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockStop,
		Index: index,
	}
	return formatSSE(models.AnthropicEventContentBlockStop, event)
}

// GenerateAnthropicMessageDelta generates message_delta event with stop reason and usage
func (c *ProtocolConverter) GenerateAnthropicMessageDelta(stopReason string, outputTokens int) string {
	event := models.AnthropicStreamEvent{
		Type: models.AnthropicEventMessageDelta,
		Delta: &models.AnthropicDelta{
			StopReason: stopReason,
		},
		Usage: &models.AnthropicUsage{
			OutputTokens: outputTokens,
		},
	}
	return formatSSE(models.AnthropicEventMessageDelta, event)
}

// GenerateAnthropicMessageStop generates message_stop event
func (c *ProtocolConverter) GenerateAnthropicMessageStop() string {
	event := models.AnthropicStreamEvent{
		Type: models.AnthropicEventMessageStop,
	}
	return formatSSE(models.AnthropicEventMessageStop, event)
}

// ConvertOpenAIStreamChunkToAnthropic converts an OpenAI stream chunk to Anthropic format
func (c *ProtocolConverter) ConvertOpenAIStreamChunkToAnthropic(chunk *StreamChunk, messageID string, contentIndex int, state *StreamConversionState) string {
	var result strings.Builder

	// Send message_start if this is the first chunk
	if !state.MessageStarted {
		result.WriteString(c.GenerateAnthropicStreamStart(messageID, ""))
		result.WriteString("\n")
		state.MessageStarted = true
	}

	// Send content_block_start if this is the first content
	if !state.ContentBlockStarted && len(chunk.Choices) > 0 && chunk.Choices[0].Delta.Content != "" {
		result.WriteString(c.GenerateAnthropicContentBlockStart(contentIndex))
		result.WriteString("\n")
		state.ContentBlockStarted = true
	}

	// Send content delta
	for _, choice := range chunk.Choices {
		if choice.Delta.Content != "" {
			result.WriteString(c.GenerateAnthropicContentDelta(contentIndex, choice.Delta.Content))
			result.WriteString("\n")
			state.AccumulatedContent += choice.Delta.Content
		}

		// Handle finish reason
		if choice.FinishReason != nil && *choice.FinishReason != "" {
			// Close content block
			if state.ContentBlockStarted {
				result.WriteString(c.GenerateAnthropicContentBlockStop(contentIndex))
				result.WriteString("\n")
			}

			// Send message_delta with stop reason
			stopReason := convertFinishReasonToAnthropic(*choice.FinishReason)
			estimatedTokens := len(state.AccumulatedContent) / 4 // rough estimate
			result.WriteString(c.GenerateAnthropicMessageDelta(stopReason, estimatedTokens))
			result.WriteString("\n")

			// Send message_stop
			result.WriteString(c.GenerateAnthropicMessageStop())
			result.WriteString("\n")
		}
	}

	return result.String()
}

// StreamConversionState tracks state during stream conversion
type StreamConversionState struct {
	MessageStarted      bool
	ContentBlockStarted bool
	AccumulatedContent  string
}

// Helper functions

func generateMessageID() string {
	return "msg_" + strings.ReplaceAll(uuid.New().String(), "-", "")[:24]
}

func convertFinishReasonToAnthropic(reason string) string {
	switch reason {
	case "stop":
		return models.AnthropicStopEndTurn
	case "length":
		return models.AnthropicStopMaxTokens
	case "content_filter":
		return models.AnthropicStopSequence
	case "tool_calls":
		return models.AnthropicStopToolUse
	default:
		return models.AnthropicStopEndTurn
	}
}

func convertStopReasonToOpenAI(reason string) string {
	switch reason {
	case models.AnthropicStopEndTurn:
		return "stop"
	case models.AnthropicStopMaxTokens:
		return "length"
	case models.AnthropicStopSequence:
		return "stop"
	case models.AnthropicStopToolUse:
		return "tool_calls"
	default:
		return "stop"
	}
}

func formatSSE(eventType string, data interface{}) string {
	jsonData, _ := json.Marshal(data)
	return fmt.Sprintf("event: %s\ndata: %s\n", eventType, string(jsonData))
}