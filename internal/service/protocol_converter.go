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
			anthropicReq.System = msg.Content.GetText()
		} else {
			// Convert content - handle multimodal
			var content models.AnthropicContent
			if msg.Content.StringContent != "" {
				content = models.AnthropicContent{StringContent: msg.Content.StringContent}
			} else if len(msg.Content.Parts) > 0 {
				// Convert OpenAI content parts to Anthropic content blocks
				var blocks []models.AnthropicContentBlock
				for _, part := range msg.Content.Parts {
					switch part.Type {
					case "text":
						blocks = append(blocks, models.AnthropicContentBlock{
							Type: "text",
							Text: part.Text,
						})
					case "image_url":
						if part.ImageURL != nil {
							blocks = append(blocks, convertOpenAIMediaToAnthropic("image", part.ImageURL.URL))
						}
					case "video_url":
						if part.VideoURL != nil {
							blocks = append(blocks, convertOpenAIMediaToAnthropic("video", part.VideoURL.URL))
						}
					}
				}
				content = models.AnthropicContent{Blocks: blocks}
			}
			messages = append(messages, models.AnthropicMessage{
				Role:    msg.Role,
				Content: content,
			})
		}
	}
	anthropicReq.Messages = messages

	return anthropicReq, nil
}

// convertOpenAIMediaToAnthropic converts OpenAI media URL to Anthropic media block
func convertOpenAIMediaToAnthropic(mediaType string, url string) models.AnthropicContentBlock {
	// Check if it's a base64 data URL
	if strings.HasPrefix(url, "data:") {
		// Parse data URL: data:image/jpeg;base64,<data> or data:video/mp4;base64,<data>
		parts := strings.SplitN(url, ",", 2)
		if len(parts) == 2 {
			mimeInfo := parts[0] // data:image/jpeg;base64
			data := parts[1]

			// Extract media type
			mimeType := ""
			if strings.HasPrefix(mimeInfo, "data:") {
				mimeType = strings.TrimPrefix(mimeInfo, "data:")
				mimeType = strings.Split(mimeType, ";")[0]
			}

			return models.AnthropicContentBlock{
				Type: mediaType, // "image" or "video"
				Source: &models.AnthropicMediaSource{
					Type:      "base64",
					MediaType: mimeType,
					Data:      data,
				},
			}
		}
	}

	// For URL-based media
	return models.AnthropicContentBlock{
		Type: mediaType, // "image" or "video"
		Source: &models.AnthropicMediaSource{
			Type: "url",
			URL:  url,
		},
	}
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
			Content: ChatMessageContent{StringContent: req.System},
		})
	}

	// Convert messages
	for _, msg := range req.Messages {
		content := convertAnthropicContentToOpenAI(msg.Content)
		messages = append(messages, ChatMessage{
			Role:    msg.Role,
			Content: content,
		})
	}
	openAIReq.Messages = messages

	return openAIReq, nil
}

// convertAnthropicContentToOpenAI converts Anthropic content to OpenAI format
func convertAnthropicContentToOpenAI(content models.AnthropicContent) ChatMessageContent {
	// Simple string content
	if content.StringContent != "" {
		return ChatMessageContent{StringContent: content.StringContent}
	}

	// Convert content blocks
	if len(content.Blocks) > 0 {
		var parts []ChatContentPart
		for _, block := range content.Blocks {
			switch block.Type {
			case "text":
				parts = append(parts, ChatContentPart{
					Type: "text",
					Text: block.Text,
				})
			case "image":
				if block.Source != nil {
					var url string
					if block.Source.Type == "base64" {
						url = fmt.Sprintf("data:%s;base64,%s", block.Source.MediaType, block.Source.Data)
					} else {
						url = block.Source.URL
					}
					parts = append(parts, ChatContentPart{
						Type:     "image_url",
						ImageURL: &ChatImageURL{URL: url},
					})
				}
			case "video":
				if block.Source != nil {
					var url string
					if block.Source.Type == "base64" {
						url = fmt.Sprintf("data:%s;base64,%s", block.Source.MediaType, block.Source.Data)
					} else {
						url = block.Source.URL
					}
					parts = append(parts, ChatContentPart{
						Type:     "video_url",
						VideoURL: &ChatMediaURL{URL: url},
					})
				}
			}
		}

		// If only text, simplify to string
		if len(parts) == 1 && parts[0].Type == "text" {
			return ChatMessageContent{StringContent: parts[0].Text}
		}
		return ChatMessageContent{Parts: parts}
	}

	return ChatMessageContent{}
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
				Text: choice.Message.Content.GetText(),
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
				Content: ChatMessageContent{StringContent: content},
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