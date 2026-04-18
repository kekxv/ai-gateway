package service

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

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
	case from == ProtocolAnthropic && to == ProtocolGemini:
		return c.anthropicToGeminiRequest(req.(*models.AnthropicMessagesRequest))
	case from == ProtocolOpenAI && to == ProtocolGemini:
		return c.openAIToGeminiRequest(req.(*ChatRequest))
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
	case from == ProtocolGemini && to == ProtocolAnthropic:
		return c.geminiToAnthropicResponse(resp.(*models.GeminiGenerateContentResponse), modelName)
	case from == ProtocolGemini && to == ProtocolOpenAI:
		return c.geminiToOpenAIResponse(resp.(*models.GeminiGenerateContentResponse), modelName)
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

	// Map OpenAI/Ollama reasoning to Anthropic Thinking
	if req.Think != nil && !*req.Think {
		anthropicReq.Thinking = &models.AnthropicThinkingConfig{
			Type: "disabled",
		}
	} else if req.ReasoningEffort != "" {
		if req.ReasoningEffort == "none" {
			anthropicReq.Thinking = &models.AnthropicThinkingConfig{
				Type: "disabled",
			}
		} else {
			// Enable thinking and set budget based on effort
			budget := 1024 // Default
			switch req.ReasoningEffort {
			case "low":
				budget = 1024
			case "medium":
				budget = 4096
			case "high":
				budget = 8192
			}
			anthropicReq.Thinking = &models.AnthropicThinkingConfig{
				Type:         "enabled",
				BudgetTokens: budget,
			}
			// When thinking is enabled, max_tokens must be greater than budget_tokens
			if anthropicReq.MaxTokens <= budget {
				anthropicReq.MaxTokens = budget + 1024
			}
		}
	} else if req.Thinking != nil {
		// Pass through direct thinking config if present
		anthropicReq.Thinking = &models.AnthropicThinkingConfig{
			Type:         req.Thinking.Type,
			BudgetTokens: req.Thinking.BudgetTokens,
		}
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
			anthropicReq.System = models.AnthropicSystem{StringContent: msg.Content.GetText()}
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
	if req.TopK > 0 {
		openAIReq.Extra["top_k"] = req.TopK
	}
	if len(req.StopSequences) > 0 {
		openAIReq.Extra["stop"] = req.StopSequences
	}

	// Map Tools
	if len(req.Tools) > 0 {
		var tools []ToolDefinition
		for _, t := range req.Tools {
			tools = append(tools, ToolDefinition{
				Type: "function",
				Function: ToolFunctionSpec{
					Name:        t.Name,
					Description: t.Description,
					Parameters:  cleanSchemaForGemini(t.InputSchema),
				},
			})
		}
		openAIReq.Tools = tools
	}

	// Map ToolChoice
	if req.ToolChoice != nil {
		switch req.ToolChoice.Type {
		case "auto":
			openAIReq.Extra["tool_choice"] = "auto"
		case "any":
			openAIReq.Extra["tool_choice"] = "required"
		case "tool":
			openAIReq.Extra["tool_choice"] = map[string]interface{}{
				"type": "function",
				"function": map[string]string{
					"name": req.ToolChoice.Name,
				},
			}
		}
	}

	// Map Anthropic Thinking to OpenAI/Ollama parameters
	if req.Thinking != nil {
		if req.Thinking.Type == "disabled" {
			think := false
			openAIReq.Think = &think
			openAIReq.ReasoningEffort = "none"
		} else if req.Thinking.Type == "enabled" {
			think := true
			openAIReq.Think = &think
			// Budget tokens don't have a direct OpenAI equivalent but we can store it in Extra
			openAIReq.Extra["thinking_budget_tokens"] = req.Thinking.BudgetTokens
		}
	}

	// Build messages - add system message first if present
	var messages []ChatMessage
	if !req.System.IsEmpty() {
		messages = append(messages, ChatMessage{
			Role:    "system",
			Content: ChatMessageContent{StringContent: req.System.GetText()},
		})
	}

	// Convert messages
	for _, msg := range req.Messages {
		var toolCalls []ToolCall
		var toolResultMessages []ChatMessage

		// Pre-scan for tool results and tool calls
		var otherBlocks []models.AnthropicContentBlock
		if len(msg.Content.Blocks) > 0 {
			for _, block := range msg.Content.Blocks {
				if block.Type == "tool_result" {
					var resultText string
					switch v := block.Content.(type) {
					case string:
						resultText = v
					case []interface{}:
						// Handle array of blocks in tool_result
						for _, b := range v {
							if bm, ok := b.(map[string]interface{}); ok {
								if bt, ok := bm["type"].(string); ok && bt == "text" {
									if txt, ok := bm["text"].(string); ok {
										resultText += txt
									}
								}
							}
						}
					default:
						b, _ := json.Marshal(v)
						resultText = string(b)
					}
					toolResultMessages = append(toolResultMessages, ChatMessage{
						Role:       "tool",
						ToolCallID: block.ToolUseID,
						Content:    ChatMessageContent{StringContent: resultText},
					})
				} else if block.Type == "tool_use" {
					inputJson, _ := json.Marshal(block.Input)
					toolCalls = append(toolCalls, ToolCall{
						ID:   block.ID,
						Type: "function",
						Function: FunctionCall{
							Name:      block.Name,
							Arguments: string(inputJson),
						},
					})
				} else {
					otherBlocks = append(otherBlocks, block)
				}
			}
		}

		// Convert remaining content (text, image, thinking)
		var content ChatMessageContent
		if len(otherBlocks) > 0 {
			content = convertAnthropicContentToOpenAI(models.AnthropicContent{Blocks: otherBlocks})
		} else if msg.Content.StringContent != "" {
			content = ChatMessageContent{StringContent: msg.Content.StringContent}
		}

		// If we have content or tool calls, add the message
		if content.StringContent != "" || len(content.Parts) > 0 || len(toolCalls) > 0 {
			messages = append(messages, ChatMessage{
				Role:      msg.Role,
				Content:   content,
				ToolCalls: toolCalls,
			})
		}

		// Add any tool result messages
		if len(toolResultMessages) > 0 {
			messages = append(messages, toolResultMessages...)
		}
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
			case "thinking":
				// Convert thinking to text wrapped in <think> tags for OpenAI
				parts = append(parts, ChatContentPart{
					Type: "text",
					Text: "<think>" + block.Thinking + "</think>",
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
			case "tool_result":
				var resultText string
				switch v := block.Content.(type) {
				case string:
					resultText = v
				case []interface{}:
					for _, b := range v {
						if bm, ok := b.(map[string]interface{}); ok {
							if bt, ok := bm["type"].(string); ok && bt == "text" {
								if txt, ok := bm["text"].(string); ok {
									resultText += txt
								}
							}
						}
					}
				default:
					b, _ := json.Marshal(v)
					resultText = string(b)
				}
				parts = append(parts, ChatContentPart{
					Type: "text",
					Text: resultText,
				})
			}
		}

		// If we only have one text part, return as simple string
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
			// Add reasoning (thinking) if present
			if reasoning := choice.Message.Reasoning; reasoning != "" {
				content = append(content, models.AnthropicContentBlock{
					Type:     "thinking",
					Thinking: reasoning,
				})
			}

			// Add text content if present
			if text := choice.Message.Content.GetText(); text != "" {
				content = append(content, models.AnthropicContentBlock{
					Type: "text",
					Text: text,
				})
			}

			// Add tool calls
			for _, tc := range choice.Message.ToolCalls {
				var input map[string]interface{}
				json.Unmarshal([]byte(tc.Function.Arguments), &input)
				content = append(content, models.AnthropicContentBlock{
					Type:  "tool_use",
					ID:    tc.ID,
					Name:  tc.Function.Name,
					Input: input,
				})
			}
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
	var reasoning string
	var toolCalls []ToolCall

	for _, block := range resp.Content {
		switch block.Type {
		case "text":
			content += block.Text
		case "thinking":
			reasoning += block.Thinking
		case "tool_use":
			inputJson, _ := json.Marshal(block.Input)
			toolCalls = append(toolCalls, ToolCall{
				ID:   block.ID,
				Type: "function",
				Function: FunctionCall{
					Name:      block.Name,
					Arguments: string(inputJson),
				},
			})
		}
	}

	openAIResp.Choices = []Choice{
		{
			Index: 0,
			Message: &ChatMessage{
				Role:      "assistant",
				Content:   ChatMessageContent{StringContent: content},
				Reasoning: reasoning,
				ToolCalls: toolCalls,
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
			Usage:   &models.AnthropicUsage{InputTokens: 0, OutputTokens: 0}, // Default usage to avoid null pointer errors
		},
	}
	return formatSSE(models.AnthropicEventMessageStart, event)
}

// GenerateAnthropicContentBlockStart generates content_block_start event
func (c *ProtocolConverter) GenerateAnthropicContentBlockStart(index int, blockType string) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockStart,
		Index: index,
		ContentBlock: &models.AnthropicContentBlock{
			Type: blockType,
		},
	}
	if blockType == "text" {
		event.ContentBlock.Text = ""
	} else if blockType == "thinking" {
		event.ContentBlock.Thinking = ""
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

// GenerateAnthropicThinkingDelta generates content_block_delta event for thinking
func (c *ProtocolConverter) GenerateAnthropicThinkingDelta(index int, thinking string) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockDelta,
		Index: index,
		Delta: &models.AnthropicDelta{
			Type:     "thinking_delta",
			Thinking: thinking,
		},
	}
	return formatSSE(models.AnthropicEventContentBlockDelta, event)
}

// GenerateAnthropicSignatureDelta generates content_block_delta event for signature
func (c *ProtocolConverter) GenerateAnthropicSignatureDelta(index int, signature string) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockDelta,
		Index: index,
		Delta: &models.AnthropicDelta{
			Type:      "signature_delta",
			Signature: signature,
		},
	}
	return formatSSE(models.AnthropicEventContentBlockDelta, event)
}

// GenerateAnthropicToolUseBlockStart generates content_block_start event for tool_use
func (c *ProtocolConverter) GenerateAnthropicToolUseBlockStart(index int, id, name string) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockStart,
		Index: index,
		ContentBlock: &models.AnthropicContentBlock{
			Type: "tool_use",
			ID:   id,
			Name: name,
		},
	}
	return formatSSE(models.AnthropicEventContentBlockStart, event)
}

// GenerateAnthropicToolUseDelta generates content_block_delta event for tool_use input
func (c *ProtocolConverter) GenerateAnthropicToolUseDelta(index int, inputDelta string) string {
	event := models.AnthropicStreamEvent{
		Type:  models.AnthropicEventContentBlockDelta,
		Index: index,
		Delta: &models.AnthropicDelta{
			Type:        "input_json_delta",
			PartialJSON: inputDelta,
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
func (c *ProtocolConverter) ConvertOpenAIStreamChunkToAnthropic(chunk *StreamChunk, messageID string, modelName string, contentIndex *int, state *StreamConversionState) string {
	var result strings.Builder

	// Send message_start if this is the first chunk
	if !state.MessageStarted {
		result.WriteString(c.GenerateAnthropicStreamStart(messageID, modelName))
		state.MessageStarted = true
	}

	// Send content delta
	for _, choice := range chunk.Choices {
		// Handle Tool Calls
		if len(choice.Delta.ToolCalls) > 0 {
			for _, tc := range choice.Delta.ToolCalls {
				// If we have a new tool call or switched tool call
				if state.LastToolIndex != tc.Index {
					// Stop previous tool call if it was active
					if state.ToolUseStarted {
						result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
						*contentIndex++
					}
					// If we were thinking or having content, stop them
					if state.ThinkingStarted || state.ContentBlockStarted {
						result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
						*contentIndex++
						state.ThinkingStarted = false
						state.ContentBlockStarted = false
					}

					// Start new tool use block
					state.ToolUseStarted = true
					state.LastToolIndex = tc.Index
					result.WriteString(c.GenerateAnthropicToolUseBlockStart(*contentIndex, tc.ID, tc.Function.Name))
				}

				// Handle tool call input delta
				if tc.Function.Arguments != "" {
					result.WriteString(c.GenerateAnthropicToolUseDelta(*contentIndex, tc.Function.Arguments))
					state.AccumulatedContent += tc.Function.Arguments
				}
			}
			continue
		}

		// Handle Reasoning (Thinking) - support both Reasoning (Ollama/Gemma) and ReasoningContent (O1/O3)
		reasoning := choice.Delta.Reasoning
		if reasoning == "" {
			reasoning = choice.Delta.ReasoningContent
		}

		if reasoning != "" {
			if !state.ThinkingStarted {
				// If we were doing tool use, stop it
				if state.ToolUseStarted {
					result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
					*contentIndex++
					state.ToolUseStarted = false
					state.LastToolIndex = -1
				}
				// If we had content, stop it
				if state.ContentBlockStarted {
					result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
					*contentIndex++
					state.ContentBlockStarted = false
				}

				result.WriteString(c.GenerateAnthropicContentBlockStart(*contentIndex, "thinking"))
				state.ThinkingStarted = true
			}
			result.WriteString(c.GenerateAnthropicThinkingDelta(*contentIndex, reasoning))
			state.AccumulatedContent += reasoning
			continue
		}

		// If we were thinking and now have content, stop thinking block and start text block
		if state.ThinkingStarted && choice.Delta.Content != "" {
			result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
			*contentIndex++
			state.ThinkingStarted = false
			state.ContentBlockStarted = false
		}

		// If we were doing tool use and now have content, stop tool use block and start text block
		if state.ToolUseStarted && choice.Delta.Content != "" {
			result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
			*contentIndex++
			state.ToolUseStarted = false
			state.LastToolIndex = -1
			state.ContentBlockStarted = false
		}

		// Handle Content
		if choice.Delta.Content != "" {
			if !state.ContentBlockStarted {
				result.WriteString(c.GenerateAnthropicContentBlockStart(*contentIndex, "text"))
				state.ContentBlockStarted = true
			}
			result.WriteString(c.GenerateAnthropicContentDelta(*contentIndex, choice.Delta.Content))
			state.AccumulatedContent += choice.Delta.Content
		}

		// Handle finish reason
		if choice.FinishReason != nil && *choice.FinishReason != "" && !state.MessageFinished {
			// Close current block
			if state.ContentBlockStarted || state.ThinkingStarted || state.ToolUseStarted {
				result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
			}

			// Send message_delta with stop reason
			stopReason := convertFinishReasonToAnthropic(*choice.FinishReason)
			estimatedTokens := len(state.AccumulatedContent) / 4 // rough estimate
			result.WriteString(c.GenerateAnthropicMessageDelta(stopReason, estimatedTokens))

			// Send message_stop
			result.WriteString(c.GenerateAnthropicMessageStop())
			state.MessageFinished = true
		}
	}

	return result.String()
}

// StreamConversionState tracks state during stream conversion
type StreamConversionState struct {
	MessageStarted      bool
	GeminiStarted       bool // To track if Gemini stream started (Gemini stream is an array)
	ThinkingStarted     bool
	ContentBlockStarted bool
	ToolUseStarted      bool
	LastToolIndex       int
	MessageFinished     bool
	AccumulatedContent  string
	Signature           string // To track signature for signature_delta
}

// Anthropic -> Gemini Request Conversion
func (c *ProtocolConverter) anthropicToGeminiRequest(req *models.AnthropicMessagesRequest) (*models.GeminiGenerateContentRequest, error) {
	geminiReq := &models.GeminiGenerateContentRequest{
		Contents: make([]models.GeminiContent, 0),
	}

	// 1. System Instruction
	if !req.System.IsEmpty() {
		geminiReq.SystemInstruction = &models.GeminiContent{
			Role: "system",
			Parts: []models.GeminiPart{
				{Text: req.System.GetText()},
			},
		}
	}

	// 2. Messages
	for _, msg := range req.Messages {
		role := "user"
		if msg.Role == "assistant" {
			role = "model"
		}

		parts := make([]models.GeminiPart, 0)
		if msg.Content.StringContent != "" {
			parts = append(parts, models.GeminiPart{Text: msg.Content.StringContent})
		}

		for _, block := range msg.Content.Blocks {
			switch block.Type {
			case "text":
				parts = append(parts, models.GeminiPart{Text: block.Text})
			case "thinking":
				// Gemini 2.0 Thinking models use specific parts or config
				parts = append(parts, models.GeminiPart{
					Text:    block.Thinking,
					Thought: true,
				})
			case "image":
				if block.Source != nil {
					parts = append(parts, models.GeminiPart{
						InlineData: &models.GeminiInlineData{
							MimeType: block.Source.MediaType,
							Data:     block.Source.Data,
						},
					})
				}
			case "tool_use":
				parts = append(parts, models.GeminiPart{
					FunctionCall: &models.GeminiFunctionCall{
						Name: block.Name,
						Args: block.Input,
					},
				})
			case "tool_result":
				var result map[string]interface{}
				switch v := block.Content.(type) {
				case string:
					result = map[string]interface{}{"output": v}
				case map[string]interface{}:
					result = v
				default:
					result = map[string]interface{}{"output": v}
				}

				// Find original tool name for Gemini (it requires Name, not ID)
				toolName := block.ToolUseID
				// Try to find the tool name from the messages history if ToolUseID is actually an ID
				// Anthropic uses random IDs, but Gemini expects the function name
				found := false
				for i := len(req.Messages) - 1; i >= 0; i-- {
					msg := req.Messages[i]
					if msg.Role == "assistant" {
						for _, b := range msg.Content.Blocks {
							if b.Type == "tool_use" && b.ID == block.ToolUseID {
								toolName = b.Name
								found = true
								break
							}
						}
					}
					if found {
						break
					}
				}

				parts = append(parts, models.GeminiPart{
					FunctionResponse: &models.GeminiFunctionResponse{
						Name:     toolName,
						Response: result,
					},
				})
			}
		}

		if len(parts) > 0 {
			geminiReq.Contents = append(geminiReq.Contents, models.GeminiContent{
				Role:  role,
				Parts: parts,
			})
		}
	}

	// 3. Tools
	if len(req.Tools) > 0 {
		declarations := make([]models.GeminiFunctionDeclaration, 0)
		for _, t := range req.Tools {
			declarations = append(declarations, models.GeminiFunctionDeclaration{
				Name:        t.Name,
				Description: t.Description,
				Parameters:  cleanSchemaForGemini(t.InputSchema),
			})
		}
		geminiReq.Tools = []models.GeminiTool{{FunctionDeclarations: declarations}}
	}

	// 4. Tool Choice
	if req.ToolChoice != nil {
		geminiReq.ToolConfig = &models.GeminiToolConfig{
			FunctionCallingConfig: &models.GeminiFunctionCallingConfig{},
		}
		switch req.ToolChoice.Type {
		case "auto":
			geminiReq.ToolConfig.FunctionCallingConfig.Mode = "AUTO"
		case "any":
			geminiReq.ToolConfig.FunctionCallingConfig.Mode = "ANY"
		case "tool":
			geminiReq.ToolConfig.FunctionCallingConfig.Mode = "ANY"
			geminiReq.ToolConfig.FunctionCallingConfig.AllowedFunctionNames = []string{req.ToolChoice.Name}
		case "none":
			geminiReq.ToolConfig.FunctionCallingConfig.Mode = "NONE"
		}
	}

	// 5. Generation Config
	geminiReq.GenerationConfig = &models.GeminiGenerationConfig{
		Temperature: &req.Temperature,
	}
	if req.MaxTokens > 0 {
		geminiReq.GenerationConfig.MaxOutputTokens = &req.MaxTokens
	}
	if req.TopP > 0 {
		topP := req.TopP
		geminiReq.GenerationConfig.TopP = &topP
	}
	if req.TopK > 0 {
		topK := req.TopK
		geminiReq.GenerationConfig.TopK = &topK
	}
	if len(req.StopSequences) > 0 {
		geminiReq.GenerationConfig.StopSequences = req.StopSequences
	}

	// Mapping Anthropic Thinking to Gemini Thinking
	if req.Thinking != nil && req.Thinking.Type == "enabled" {
		geminiReq.GenerationConfig.ThinkingConfig = &models.GeminiThinkingConfig{
			IncludeThoughts: true,
		}
	}

	// 6. Safety Settings (Default to BLOCK_NONE for coding/gateway use)
	categories := []string{
		"HARM_CATEGORY_HARASSMENT",
		"HARM_CATEGORY_HATE_SPEECH",
		"HARM_CATEGORY_SEXUALLY_EXPLICIT",
		"HARM_CATEGORY_DANGEROUS_CONTENT",
		"HARM_CATEGORY_CIVIC_INTEGRITY",
	}
	for _, cat := range categories {
		geminiReq.SafetySettings = append(geminiReq.SafetySettings, models.GeminiSafetySetting{
			Category:  cat,
			Threshold: "BLOCK_NONE",
		})
	}

	return geminiReq, nil
}

// OpenAI -> Gemini Request Conversion
func (c *ProtocolConverter) openAIToGeminiRequest(req *ChatRequest) (*models.GeminiGenerateContentRequest, error) {
	geminiReq := &models.GeminiGenerateContentRequest{
		Contents: make([]models.GeminiContent, 0),
	}

	// 1. System Instruction & Messages
	for _, msg := range req.Messages {
		if msg.Role == "system" {
			geminiReq.SystemInstruction = &models.GeminiContent{
				Role: "system",
				Parts: []models.GeminiPart{
					{Text: msg.Content.GetText()},
				},
			}
			continue
		}

		role := "user"
		if msg.Role == "assistant" {
			role = "model"
		}

		parts := make([]models.GeminiPart, 0)
		if msg.Reasoning != "" {
			parts = append(parts, models.GeminiPart{
				Text:    msg.Reasoning,
				Thought: true,
			})
		}
		if msg.Content.StringContent != "" {
			parts = append(parts, models.GeminiPart{Text: msg.Content.StringContent})
		}

		for _, part := range msg.Content.Parts {
			switch part.Type {
			case "text":
				parts = append(parts, models.GeminiPart{Text: part.Text})
			case "image_url":
				if part.ImageURL != nil {
					if strings.HasPrefix(part.ImageURL.URL, "data:") {
						metaAndData := strings.SplitN(part.ImageURL.URL, ",", 2)
						if len(metaAndData) == 2 {
							meta := metaAndData[0]
							data := metaAndData[1]
							mediaType := strings.TrimSuffix(strings.TrimPrefix(meta, "data:"), ";base64")
							parts = append(parts, models.GeminiPart{
								InlineData: &models.GeminiInlineData{
									MimeType: mediaType,
									Data:     data,
								},
							})
						}
					}
				}
			}
		}

		// Handle Tool Calls in Assistant message
		for _, tc := range msg.ToolCalls {
			var args map[string]interface{}
			json.Unmarshal([]byte(tc.Function.Arguments), &args)
			parts = append(parts, models.GeminiPart{
				FunctionCall: &models.GeminiFunctionCall{
					Name: tc.Function.Name,
					Args: args,
				},
			})
		}

		// Handle Tool Result
		if msg.Role == "tool" {
			var result map[string]interface{}
			if err := json.Unmarshal([]byte(msg.Content.GetText()), &result); err != nil {
				result = map[string]interface{}{"output": msg.Content.GetText()}
			}

			// Find original tool name for Gemini (it requires Name, not ID)
			toolName := msg.ToolCallID
			found := false
			for i := len(req.Messages) - 1; i >= 0; i-- {
				m := req.Messages[i]
				if m.Role == "assistant" {
					for _, tc := range m.ToolCalls {
						if tc.ID == msg.ToolCallID {
							toolName = tc.Function.Name
							found = true
							break
						}
					}
				}
				if found {
					break
				}
			}

			parts = append(parts, models.GeminiPart{
				FunctionResponse: &models.GeminiFunctionResponse{
					Name:     toolName,
					Response: result,
				},
			})
		}

		if len(parts) > 0 {
			geminiReq.Contents = append(geminiReq.Contents, models.GeminiContent{
				Role:  role,
				Parts: parts,
			})
		}
	}

	// 2. Tools
	if len(req.Tools) > 0 {
		declarations := make([]models.GeminiFunctionDeclaration, 0)
		for _, t := range req.Tools {
			declarations = append(declarations, models.GeminiFunctionDeclaration{
				Name:        t.Function.Name,
				Description: t.Function.Description,
				Parameters:  cleanSchemaForGemini(t.Function.Parameters),
			})
		}
		geminiReq.Tools = []models.GeminiTool{{FunctionDeclarations: declarations}}
	}

	// 3. Generation Config
	geminiReq.GenerationConfig = &models.GeminiGenerationConfig{
		Temperature: &req.Temperature,
	}
	if req.MaxTokens > 0 {
		geminiReq.GenerationConfig.MaxOutputTokens = &req.MaxTokens
	}
	if req.Extra != nil {
		if topP, ok := req.Extra["top_p"].(float64); ok {
			geminiReq.GenerationConfig.TopP = &topP
		}
	}

	// Handle Think parameter (DeepSeek/Ollama format: false to disable thinking)
	if req.Think != nil && !*req.Think {
		geminiReq.GenerationConfig.ThinkingConfig = &models.GeminiThinkingConfig{
			ThinkingLevel: "NONE",
		}
	}

	// Handle ReasoningEffort -> Gemini ThinkingLevel
	if req.ReasoningEffort != "" {
		thinkingLevel := ""
		switch req.ReasoningEffort {
		case "none":
			thinkingLevel = "NONE"
		case "low":
			thinkingLevel = "LOW"
		case "medium":
			thinkingLevel = "MEDIUM"
		case "high":
			thinkingLevel = "HIGH"
		}
		if thinkingLevel != "" {
			geminiReq.GenerationConfig.ThinkingConfig = &models.GeminiThinkingConfig{
				ThinkingLevel: thinkingLevel,
			}
		}
	}
	// Handle GenerationConfig.ThinkingConfig if present
	if req.GenerationConfig != nil && req.GenerationConfig.ThinkingConfig != nil {
		geminiReq.GenerationConfig.ThinkingConfig = &models.GeminiThinkingConfig{
			ThinkingLevel: req.GenerationConfig.ThinkingConfig.ThinkingLevel,
		}
	}

	return geminiReq, nil
}

// Gemini -> Anthropic Response Conversion
func (c *ProtocolConverter) geminiToAnthropicResponse(resp *models.GeminiGenerateContentResponse, modelName string) (*models.AnthropicMessagesResponse, error) {
	// Initialize with empty Content and default Usage to avoid null pointer errors
	anthropicResp := &models.AnthropicMessagesResponse{
		ID:      generateMessageID(),
		Type:    "message",
		Role:    "assistant",
		Model:   modelName,
		Content: []models.AnthropicContentBlock{},
		Usage:   &models.AnthropicUsage{InputTokens: 0, OutputTokens: 0},
	}

	// Handle empty candidates - add empty text block to satisfy Anthropic SDK
	if len(resp.Candidates) == 0 {
		anthropicResp.Content = []models.AnthropicContentBlock{
			{Type: "text", Text: ""},
		}
		anthropicResp.StopReason = models.AnthropicStopEndTurn
		return anthropicResp, nil
	}

	candidate := resp.Candidates[0]
	anthropicResp.StopReason = convertGeminiFinishReasonToAnthropic(candidate.FinishReason)

	// Handle empty Parts - add empty text block to satisfy Anthropic SDK
	if len(candidate.Content.Parts) == 0 {
		anthropicResp.Content = []models.AnthropicContentBlock{
			{Type: "text", Text: ""},
		}
		return anthropicResp, nil
	}

	for _, part := range candidate.Content.Parts {
		if part.Thought {
			anthropicResp.Content = append(anthropicResp.Content, models.AnthropicContentBlock{
				Type:     "thinking",
				Thinking: part.Text,
			})
		} else if part.Text != "" {
			anthropicResp.Content = append(anthropicResp.Content, models.AnthropicContentBlock{
				Type: "text",
				Text: part.Text,
			})
		}
		if part.FunctionCall != nil {
			anthropicResp.Content = append(anthropicResp.Content, models.AnthropicContentBlock{
				Type:  "tool_use",
				ID:    generateMessageID(), // Gemini doesn't have call ID in response, we generate one
				Name:  part.FunctionCall.Name,
				Input: part.FunctionCall.Args,
			})
			anthropicResp.StopReason = models.AnthropicStopToolUse
		}
	}

	// Update Usage if available
	if resp.UsageMetadata != nil {
		anthropicResp.Usage = &models.AnthropicUsage{
			InputTokens:  resp.UsageMetadata.PromptTokenCount,
			OutputTokens: resp.UsageMetadata.CandidatesTokenCount,
		}
	}

	return anthropicResp, nil
}

// Gemini -> OpenAI Response Conversion
func (c *ProtocolConverter) geminiToOpenAIResponse(resp *models.GeminiGenerateContentResponse, modelName string) (*ChatResponse, error) {
	// Initialize with default Usage to avoid null pointer errors
	openAIResp := &ChatResponse{
		ID:      "chatcmpl-" + strings.ReplaceAll(uuid.New().String(), "-", ""),
		Object:  "chat.completion",
		Created: time.Now().Unix(),
		Model:   modelName,
		Usage:   &Usage{PromptTokens: 0, CompletionTokens: 0, TotalTokens: 0},
	}

	// Handle empty candidates - add empty message to satisfy OpenAI format
	if len(resp.Candidates) == 0 {
		openAIResp.Choices = []Choice{
			{
				Index:        0,
				Message:      &ChatMessage{Role: "assistant", Content: ChatMessageContent{StringContent: ""}},
				FinishReason: "stop",
			},
		}
		return openAIResp, nil
	}

	candidate := resp.Candidates[0]
	message := &ChatMessage{
		Role: "assistant",
	}

	var contentBuilder strings.Builder
	for _, part := range candidate.Content.Parts {
		if part.Thought {
			contentBuilder.WriteString("<think>")
			contentBuilder.WriteString(part.Text)
			contentBuilder.WriteString("</think>")
		} else if part.Text != "" {
			contentBuilder.WriteString(part.Text)
		}
		if part.FunctionCall != nil {
			message.ToolCalls = append(message.ToolCalls, ToolCall{
				ID:   generateMessageID(),
				Type: "function",
				Function: FunctionCall{
					Name:      part.FunctionCall.Name,
					Arguments: func() string { b, _ := json.Marshal(part.FunctionCall.Args); return string(b) }(),
				},
			})
		}
	}
	message.Content = ChatMessageContent{StringContent: contentBuilder.String()}

	openAIResp.Choices = []Choice{
		{
			Index:        0,
			Message:      message,
			FinishReason: strings.ToLower(candidate.FinishReason),
		},
	}
	if openAIResp.Choices[0].FinishReason == "" {
		openAIResp.Choices[0].FinishReason = "stop"
	}

	// Update Usage if available
	if resp.UsageMetadata != nil {
		openAIResp.Usage = &Usage{
			PromptTokens:     resp.UsageMetadata.PromptTokenCount,
			CompletionTokens: resp.UsageMetadata.CandidatesTokenCount,
			TotalTokens:      resp.UsageMetadata.TotalTokenCount,
		}
	}

	return openAIResp, nil
}

// ConvertGeminiStreamChunkToAnthropic converts a Gemini stream chunk to Anthropic format
func (c *ProtocolConverter) ConvertGeminiStreamChunkToAnthropic(chunk *models.GeminiGenerateContentResponse, messageID string, modelName string, contentIndex *int, state *StreamConversionState) string {
	var result strings.Builder

	if !state.MessageStarted {
		result.WriteString(c.GenerateAnthropicStreamStart(messageID, modelName))
		state.MessageStarted = true
	}

	if len(chunk.Candidates) > 0 {
		candidate := chunk.Candidates[0]

		for _, part := range candidate.Content.Parts {
			// Handle Thinking (Gemini 2.0 Thinking models use thought: true)
			if part.Thought {
				if !state.ThinkingStarted {
					if state.ContentBlockStarted {
						result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
						*contentIndex++
						state.ContentBlockStarted = false
					}
					result.WriteString(c.GenerateAnthropicContentBlockStart(*contentIndex, "thinking"))
					state.ThinkingStarted = true
				}
				result.WriteString(c.GenerateAnthropicThinkingDelta(*contentIndex, part.Text))
				state.AccumulatedContent += part.Text
				continue
			}

			// Transition from thinking to text if needed
			if state.ThinkingStarted && part.Text != "" {
				result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
				*contentIndex++
				state.ThinkingStarted = false
			}

			if part.Text != "" {
				if !state.ContentBlockStarted {
					result.WriteString(c.GenerateAnthropicContentBlockStart(*contentIndex, "text"))
					state.ContentBlockStarted = true
				}
				result.WriteString(c.GenerateAnthropicContentDelta(*contentIndex, part.Text))
				state.AccumulatedContent += part.Text
			}

			if part.FunctionCall != nil {
				if state.ContentBlockStarted {
					result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
					*contentIndex++
					state.ContentBlockStarted = false
				}
				// Gemini streaming tool calls usually come in one chunk
				result.WriteString(c.GenerateAnthropicToolUseBlockStart(*contentIndex, generateMessageID(), part.FunctionCall.Name))
				argsJson, _ := json.Marshal(part.FunctionCall.Args)
				result.WriteString(c.GenerateAnthropicToolUseDelta(*contentIndex, string(argsJson)))
				result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
				*contentIndex++
			}
		}

		if candidate.FinishReason != "" {
			if state.ContentBlockStarted {
				result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
				state.ContentBlockStarted = false
			}
			if state.ThinkingStarted {
				result.WriteString(c.GenerateAnthropicContentBlockStop(*contentIndex))
				state.ThinkingStarted = false
			}

			stopReason := convertGeminiFinishReasonToAnthropic(candidate.FinishReason)
			outputTokens := 0
			if chunk.UsageMetadata != nil {
				outputTokens = chunk.UsageMetadata.CandidatesTokenCount
			}
			result.WriteString(c.GenerateAnthropicMessageDelta(stopReason, outputTokens))
			result.WriteString(c.GenerateAnthropicMessageStop())
			state.MessageFinished = true
		}
	}

	return result.String()
}

func convertGeminiFinishReasonToAnthropic(reason string) string {
	switch reason {
	case "STOP":
		return models.AnthropicStopEndTurn
	case "MAX_TOKENS":
		return models.AnthropicStopMaxTokens
	case "SAFETY", "RECITATION":
		return models.AnthropicStopSequence
	default:
		return models.AnthropicStopEndTurn
	}
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

// ConvertGeminiStreamChunkToOpenAI converts a Gemini stream chunk to OpenAI format
func (c *ProtocolConverter) ConvertGeminiStreamChunkToOpenAI(chunk *models.GeminiGenerateContentResponse, messageID string, modelName string, state *StreamConversionState) string {
	var result strings.Builder

	if len(chunk.Candidates) > 0 {
		candidate := chunk.Candidates[0]

		for _, part := range candidate.Content.Parts {
			delta := map[string]interface{}{}

			// Handle Thinking
			if part.Thought {
				if !state.ThinkingStarted {
					state.ThinkingStarted = true
				}
				delta["reasoning_content"] = part.Text
				state.AccumulatedContent += part.Text
			} else if part.Text != "" {
				// Transition from thinking to content
				if state.ThinkingStarted {
					state.ThinkingStarted = false
				}
				delta["content"] = part.Text
				state.AccumulatedContent += part.Text
			}

			if part.FunctionCall != nil {
				argsJson, _ := json.Marshal(part.FunctionCall.Args)
				toolCalls := []map[string]interface{}{
					{
						"index": 0,
						"id":    generateMessageID(),
						"type":  "function",
						"function": map[string]interface{}{
							"name":      part.FunctionCall.Name,
							"arguments": string(argsJson),
						},
					},
				}
				delta["tool_calls"] = toolCalls
			}

			if len(delta) > 0 {
				chunkObj := map[string]interface{}{
					"id":      messageID,
					"object":  "chat.completion.chunk",
					"created": time.Now().Unix(),
					"model":   modelName,
					"choices": []map[string]interface{}{
						{
							"index": 0,
							"delta": delta,
						},
					},
				}
				result.WriteString(formatOpenAISSE(chunkObj))
			}
		}

		if candidate.FinishReason != "" {
			finishReason := strings.ToLower(candidate.FinishReason)
			if finishReason == "stop" {
				finishReason = "stop"
			}

			chunkObj := map[string]interface{}{
				"id":      messageID,
				"object":  "chat.completion.chunk",
				"created": time.Now().Unix(),
				"model":   modelName,
				"choices": []map[string]interface{}{
					{
						"index":         0,
						"delta":         map[string]interface{}{},
						"finish_reason": finishReason,
					},
				},
			}
			result.WriteString(formatOpenAISSE(chunkObj))
		}
	}

	// Handle usage metadata if present in the last chunk
	if chunk.UsageMetadata != nil {
		usageObj := map[string]interface{}{
			"id":      messageID,
			"object":  "chat.completion.chunk",
			"created": time.Now().Unix(),
			"model":   modelName,
			"choices": []map[string]interface{}{},
			"usage": map[string]interface{}{
				"prompt_tokens":     chunk.UsageMetadata.PromptTokenCount,
				"completion_tokens": chunk.UsageMetadata.CandidatesTokenCount,
				"total_tokens":      chunk.UsageMetadata.TotalTokenCount,
			},
		}
		result.WriteString(formatOpenAISSE(usageObj))
	}

	return result.String()
}

func formatOpenAISSE(data interface{}) string {
	jsonData, _ := json.Marshal(data)
	return fmt.Sprintf("data: %s\n\n", string(jsonData))
}

func formatSSE(eventType string, data interface{}) string {
	jsonData, _ := json.Marshal(data)
	return fmt.Sprintf("event: %s\ndata: %s\n\n", eventType, string(jsonData))
}

// cleanSchemaForGemini removes JSON Schema fields that Gemini doesn't support
// Gemini's function declaration parameters schema doesn't support:
// - $schema (JSON Schema version)
// - additionalProperties
// - propertyNames
// - exclusiveMinimum / exclusiveMaximum
// - const
// - examples
// - default (sometimes)
// - $id, $ref, definitions, $defs
func cleanSchemaForGemini(schema map[string]interface{}) map[string]interface{} {
	if schema == nil {
		return nil
	}

	// Fields to remove (Gemini doesn't support these)
	unsupportedFields := []string{
		"$schema", "$id", "$ref", "$defs", "definitions",
		"additionalProperties", "propertyNames",
		"exclusiveMinimum", "exclusiveMaximum",
		"const", "examples", "default",
	}

	result := make(map[string]interface{})
	for k, v := range schema {
		// Skip unsupported fields
		skip := false
		for _, uf := range unsupportedFields {
			if k == uf {
				skip = true
				break
			}
		}
		if skip {
			continue
		}

		// Recursively clean nested objects
		switch val := v.(type) {
		case map[string]interface{}:
			result[k] = cleanSchemaForGemini(val)
		case []interface{}:
			cleanedArray := make([]interface{}, len(val))
			for i, item := range val {
				if itemMap, ok := item.(map[string]interface{}); ok {
					cleanedArray[i] = cleanSchemaForGemini(itemMap)
				} else {
					cleanedArray[i] = item
				}
			}
			result[k] = cleanedArray
		default:
			result[k] = v
		}
	}

	return result
}
