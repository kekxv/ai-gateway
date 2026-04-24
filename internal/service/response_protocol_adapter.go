package service

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/kekxv/ai-gateway/internal/models"
)

func convertResponseRequestToChatRequest(req *models.ResponseRequest) *ChatRequest {
	chatReq := &ChatRequest{
		Model:           req.Model,
		Stream:          req.Stream,
		MaxTokens:       req.MaxOutputTokens,
		ReasoningEffort: "",
	}

	if req.Temperature != nil {
		chatReq.Temperature = *req.Temperature
	}

	if req.Reasoning != nil {
		chatReq.ReasoningEffort = req.Reasoning.Effort
	}

	if req.Instructions != "" {
		chatReq.Messages = append(chatReq.Messages, ChatMessage{
			Role: "system",
			Content: ChatMessageContent{
				StringContent: req.Instructions,
			},
		})
	}

	if len(req.Tools) > 0 {
		chatReq.Tools = make([]ToolDefinition, 0, len(req.Tools))
		for _, tool := range req.Tools {
			if tool.Type == "function" && tool.Function != nil {
				chatReq.Tools = append(chatReq.Tools, ToolDefinition{
					Type: tool.Type,
					Function: ToolFunctionSpec{
						Name:        tool.Function.Name,
						Description: tool.Function.Description,
						Parameters:  tool.Function.Parameters,
					},
				})
			} else {
				// For non-function tools, we might need to handle them specially or pass as extra
				// For now, let's at least capture the type so we don't drop them completely
				if chatReq.Extra == nil {
					chatReq.Extra = make(map[string]interface{})
				}
				extraTools, _ := chatReq.Extra["tools"].([]interface{})
				extraTools = append(extraTools, tool)
				chatReq.Extra["tools"] = extraTools
			}
		}
	}

	if req.Input.StringInput != "" {
		chatReq.Messages = append(chatReq.Messages, ChatMessage{
			Role: "user",
			Content: ChatMessageContent{
				StringContent: req.Input.StringInput,
			},
		})
	}

	for _, item := range req.Input.Items {
		switch item.Type {
		case "message", "":
			role := item.Role
			if role == "developer" {
				role = "system"
			}
			chatReq.Messages = append(chatReq.Messages, ChatMessage{
				Role:    role,
				Content: convertResponseContentToChatMessageContent(item.Content),
			})
		case "function_call":
			chatReq.Messages = append(chatReq.Messages, ChatMessage{
				Role: "assistant",
				Content: ChatMessageContent{
					StringContent: "",
				},
				ToolCalls: []ToolCall{
					{
						ID:   firstNonEmpty(item.CallID, item.ID, "call_"+shortUUID()),
						Type: "function",
						Function: FunctionCall{
							Name:      item.Name,
							Arguments: defaultJSONString(item.Arguments),
						},
					},
				},
			})
		case "function_call_output":
			chatReq.Messages = append(chatReq.Messages, ChatMessage{
				Role: "tool",
				Content: ChatMessageContent{
					StringContent: item.Output,
				},
				ToolCallID: item.CallID,
			})
		}
	}

	return chatReq
}

func convertResponseContentToChatMessageContent(content models.ResponseContent) ChatMessageContent {
	if content.StringContent != "" {
		return ChatMessageContent{StringContent: content.StringContent}
	}

	parts := make([]ChatContentPart, 0, len(content.Parts))
	for _, part := range content.Parts {
		switch part.Type {
		case "input_text":
			parts = append(parts, ChatContentPart{
				Type: "text",
				Text: part.Text,
			})
		case "input_image":
			parts = append(parts, ChatContentPart{
				Type: "image_url",
				ImageURL: &ChatMediaURL{
					URL:    part.ImageURL,
					Detail: part.Detail,
				},
			})
		}
	}

	return ChatMessageContent{Parts: parts}
}

func convertGeminiResponseToOpenAIResponse(resp *models.GeminiGenerateContentResponse, modelName string) *models.Response {
	now := time.Now().Unix()
	outputs := make([]models.ResponseOutput, 0)
	var outputText bytes.Buffer

	for _, candidate := range resp.Candidates {
		var contentParts []models.OutputContent
		for _, part := range candidate.Content.Parts {
			if part.Text != "" && !part.Thought {
				contentParts = append(contentParts, models.OutputContent{
					Type: "output_text",
					Text: part.Text,
				})
				outputText.WriteString(part.Text)
			}
			if part.FunctionCall != nil {
				argsJSON, _ := json.Marshal(part.FunctionCall.Args)
				callID := "call_" + shortUUID()
				outputs = append(outputs, models.ResponseOutput{
					Type:      "function_call",
					ID:        callID,
					CallID:    callID,
					Name:      part.FunctionCall.Name,
					Arguments: string(argsJSON),
					Status:    "completed",
				})
			}
		}

		if len(contentParts) > 0 {
			outputs = append(outputs, models.ResponseOutput{
				Type:    "message",
				ID:      "msg_" + shortUUID(),
				Role:    "assistant",
				Status:  "completed",
				Content: contentParts,
			})
		}
	}

	completedAt := now
	response := &models.Response{
		ID:          "resp_" + shortUUID(),
		Object:      "response",
		CreatedAt:   now,
		CompletedAt: &completedAt,
		Status:      "completed",
		Model:       modelName,
		Output:      outputs,
		OutputText:  outputText.String(),
	}

	if resp.UsageMetadata != nil {
		response.Usage = &models.ResponseUsage{
			InputTokens:  resp.UsageMetadata.PromptTokenCount,
			OutputTokens: resp.UsageMetadata.CandidatesTokenCount,
			TotalTokens:  resp.UsageMetadata.TotalTokenCount,
		}
	}

	return response
}

func convertGeminiChunkToResponseSSE(chunk *models.GeminiGenerateContentResponse, responseID, modelName string, state *responseStreamState) string {
	var result strings.Builder

	if !state.createdSent {
		state.createdSent = true
		result.WriteString(formatResponseSSE(models.EventResponseCreated, models.ResponseStreamEvent{
			Type: models.EventResponseCreated,
			Response: &models.Response{
				ID:        responseID,
				Object:    "response",
				CreatedAt: time.Now().Unix(),
				Status:    "in_progress",
				Model:     modelName,
			},
		}))
	}

	if len(chunk.Candidates) > 0 {
		candidate := chunk.Candidates[0]
		for _, part := range candidate.Content.Parts {
			if part.Text != "" && !part.Thought {
				result.WriteString(formatResponseSSE(models.EventResponseOutputTextDelta, models.ResponseStreamEvent{
					Type:  models.EventResponseOutputTextDelta,
					Delta: part.Text,
				}))
			}

			if part.FunctionCall != nil {
				argsJSON, _ := json.Marshal(part.FunctionCall.Args)
				callID := "call_" + shortUUID()
				result.WriteString(formatResponseSSE(models.EventResponseOutputItemDone, models.ResponseStreamEvent{
					Type: models.EventResponseOutputItemDone,
					Item: &models.ResponseOutput{
						Type:      "function_call",
						ID:        callID,
						CallID:    callID,
						Name:      part.FunctionCall.Name,
						Arguments: string(argsJSON),
						Status:    "completed",
					},
				}))
			}
		}
	}

	if chunk.UsageMetadata != nil {
		state.usage = &models.ResponseUsage{
			InputTokens:  chunk.UsageMetadata.PromptTokenCount,
			OutputTokens: chunk.UsageMetadata.CandidatesTokenCount,
			TotalTokens:  chunk.UsageMetadata.TotalTokenCount,
		}
	}

	return result.String()
}

func buildResponseCompletedSSE(responseID, modelName string, usage *models.ResponseUsage) string {
	completedAt := time.Now().Unix()
	return formatResponseSSE(models.EventResponseCompleted, models.ResponseStreamEvent{
		Type: models.EventResponseCompleted,
		Response: &models.Response{
			ID:          responseID,
			Object:      "response",
			CreatedAt:   completedAt,
			CompletedAt: &completedAt,
			Status:      "completed",
			Model:       modelName,
			Usage:       usage,
		},
	})
}

func formatResponseSSE(eventType string, data interface{}) string {
	payload, _ := json.Marshal(data)
	return fmt.Sprintf("event: %s\ndata: %s\n\n", eventType, payload)
}

func defaultJSONString(value string) string {
	if strings.TrimSpace(value) == "" {
		return "{}"
	}
	return value
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func shortUUID() string {
	return strings.ReplaceAll(uuid.New().String(), "-", "")
}

type responseStreamState struct {
	createdSent bool
	completed   bool
	usage       *models.ResponseUsage
}
