package handler

import (
	"encoding/json"
	"strings"

	"github.com/kekxv/ai-gateway/internal/models"
)

func convertChatRequestToResponseRequest(req *models.ChatRequest) (*models.ResponseRequest, error) {
	responseReq := &models.ResponseRequest{
		Model:           req.Model,
		Stream:          req.Stream,
		Temperature:     floatPtr(req.Temperature),
		MaxOutputTokens: req.MaxTokens,
	}

	if req.ReasoningEffort != "" {
		responseReq.Reasoning = &models.ReasoningConfig{
			Effort: req.ReasoningEffort,
		}
	}

	if len(req.Tools) > 0 {
		responseReq.Tools = make([]models.ResponseTool, 0, len(req.Tools))
		for _, tool := range req.Tools {
			responseReq.Tools = append(responseReq.Tools, models.ResponseTool{
				Type: tool.Type,
				Function: &models.FunctionDef{
					Name:        tool.Function.Name,
					Description: tool.Function.Description,
					Parameters:  tool.Function.Parameters,
				},
			})
		}
	}

	instructions := make([]string, 0, len(req.Messages))
	inputItems := make([]models.ResponseInputItem, 0, len(req.Messages))

	for _, msg := range req.Messages {
		switch msg.Role {
		case "system", "developer":
			text, err := extractMessageText(msg.Content)
			if err != nil {
				return nil, err
			}
			if strings.TrimSpace(text) != "" {
				instructions = append(instructions, text)
			}
			continue
		case "tool":
			output, err := extractMessageText(msg.Content)
			if err != nil {
				return nil, err
			}
			inputItems = append(inputItems, models.ResponseInputItem{
				Type:   "function_call_output",
				CallID: msg.ToolCallID,
				Output: output,
			})
			continue
		}

		content, err := convertMessageContentToResponseContent(msg.Content)
		if err != nil {
			return nil, err
		}
		inputItems = append(inputItems, models.ResponseInputItem{
			Type:    "message",
			Role:    msg.Role,
			Content: content,
		})

		if len(msg.ToolCalls) == 0 {
			continue
		}

		var toolCalls []struct {
			ID       string `json:"id"`
			Type     string `json:"type"`
			Function struct {
				Name      string `json:"name"`
				Arguments string `json:"arguments"`
			} `json:"function"`
		}
		if err := json.Unmarshal(msg.ToolCalls, &toolCalls); err != nil {
			return nil, err
		}

		for _, tc := range toolCalls {
			inputItems = append(inputItems, models.ResponseInputItem{
				Type:      "function_call",
				CallID:    tc.ID,
				Name:      tc.Function.Name,
				Arguments: tc.Function.Arguments,
				Status:    "completed",
			})
		}
	}

	if len(instructions) > 0 {
		responseReq.Instructions = strings.Join(instructions, "\n\n")
	}
	responseReq.Input = models.ResponseInput{Items: inputItems}

	return responseReq, nil
}

func convertMessageContentToResponseContent(raw json.RawMessage) (models.ResponseContent, error) {
	var str string
	if err := json.Unmarshal(raw, &str); err == nil {
		return models.ResponseContent{StringContent: str}, nil
	}

	var parts []models.ChatContentPart
	if err := json.Unmarshal(raw, &parts); err != nil {
		return models.ResponseContent{}, err
	}

	responseParts := make([]models.ContentPart, 0, len(parts))
	for _, part := range parts {
		switch part.Type {
		case "text":
			responseParts = append(responseParts, models.ContentPart{
				Type: "input_text",
				Text: part.Text,
			})
		case "image_url":
			if part.ImageURL == nil {
				continue
			}
			responseParts = append(responseParts, models.ContentPart{
				Type:     "input_image",
				ImageURL: part.ImageURL.URL,
				Detail:   part.ImageURL.Detail,
			})
		}
	}

	return models.ResponseContent{Parts: responseParts}, nil
}

func extractMessageText(raw json.RawMessage) (string, error) {
	var str string
	if err := json.Unmarshal(raw, &str); err == nil {
		return str, nil
	}

	var parts []models.ChatContentPart
	if err := json.Unmarshal(raw, &parts); err != nil {
		return "", err
	}

	texts := make([]string, 0, len(parts))
	for _, part := range parts {
		if part.Type == "text" && strings.TrimSpace(part.Text) != "" {
			texts = append(texts, part.Text)
		}
	}

	return strings.Join(texts, "\n"), nil
}

func floatPtr(value float64) *float64 {
	return &value
}
