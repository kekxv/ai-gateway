package service

import (
	"regexp"
	"strings"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
)

var thinkTagRegex = regexp.MustCompile(`<think>[\s\S]*?</think>\s*`)

// convertChatResponseToResponse converts a Chat Completions response to Responses API format
func convertChatResponseToResponse(chatResp *ChatResponse, modelName string, previousResponseID string, metadata map[string]interface{}) *models.Response {
	now := time.Now().Unix()
	output := make([]models.ResponseOutput, 0)

	if len(chatResp.Choices) == 0 || chatResp.Choices[0].Message == nil {
		return &models.Response{
			ID:        "resp_" + shortUUID(),
			Object:    "response",
			CreatedAt: now,
			Status:    "completed",
			Model:     modelName,
			Output:    output,
			Usage:     translateUsage(chatResp.Usage),
		}
	}

	msg := chatResp.Choices[0]

	// Convert tool calls to function_call output items
	if len(msg.Message.ToolCalls) > 0 {
		for _, tc := range msg.Message.ToolCalls {
			output = append(output, models.ResponseOutput{
				Type:      "function_call",
				ID:        "fc_" + shortUUID()[:16],
				CallID:    tc.ID,
				Name:      tc.Function.Name,
				Arguments: tc.Function.Arguments,
				Status:    "completed",
			})
		}
	}

	// Convert text content to message output item
	text := msg.Message.Content.GetText()
	text = thinkTagRegex.ReplaceAllString(text, "")
	text = strings.TrimSpace(text)

	if text != "" {
		output = append(output, models.ResponseOutput{
			Type:   "message",
			ID:     "msg_" + shortUUID()[:16],
			Status: "completed",
			Role:   "assistant",
			Content: []models.OutputContent{
				{Type: "output_text", Text: text},
			},
		})
	}

	// Map finish reason
	status := "completed"
	var incompleteDetails *models.IncompleteDetails
	switch msg.FinishReason {
	case "length":
		status = "incomplete"
		incompleteDetails = &models.IncompleteDetails{Reason: "max_output_tokens"}
	case "content_filter":
		status = "incomplete"
		incompleteDetails = &models.IncompleteDetails{Reason: "content_filter"}
	}

	responseID := "resp_" + shortUUID()[:16]
	response := &models.Response{
		ID:                 responseID,
		Object:             "response",
		CreatedAt:          now,
		Status:             status,
		Model:              modelName,
		Output:             output,
		Usage:              translateUsage(chatResp.Usage),
		IncompleteDetails:  incompleteDetails,
		PreviousResponseID: previousResponseID,
	}

	if metadata != nil {
		response.Metadata = metadata
	}

	return response
}

func translateUsage(usage *Usage) *models.ResponseUsage {
	if usage == nil {
		return nil
	}
	return &models.ResponseUsage{
		InputTokens:  usage.PromptTokens,
		OutputTokens: usage.CompletionTokens,
		TotalTokens:  usage.TotalTokens,
	}
}
