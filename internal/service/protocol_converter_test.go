package service

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/kekxv/ai-gateway/internal/models"
)

func TestGetProviderProtocol(t *testing.T) {
	tests := []struct {
		input    string
		expected ProtocolType
	}{
		{"openai", ProtocolOpenAI},
		{"OpenAI", ProtocolOpenAI},
		{"anthropic", ProtocolAnthropic},
		{"Anthropic", ProtocolAnthropic},
		{"claude", ProtocolAnthropic},
		{"Claude", ProtocolAnthropic},
		{"gemini", ProtocolGemini},
		{"Gemini", ProtocolGemini},
		{"custom", ProtocolOpenAI},
		{"", ProtocolOpenAI},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := GetProviderProtocol(tt.input)
			if result != tt.expected {
				t.Errorf("GetProviderProtocol(%s) = %s, want %s", tt.input, result, tt.expected)
			}
		})
	}
}

func TestConvertRequest_OpenAIToAnthropic_Basic(t *testing.T) {
	converter := NewProtocolConverter()

	openAIReq := &ChatRequest{
		Model: "gpt-4",
		Messages: []ChatMessage{
			{Role: "user", Content: ChatMessageContent{StringContent: "Hello"}},
			{Role: "assistant", Content: ChatMessageContent{StringContent: "Hi there!"}},
		},
		MaxTokens:   100,
		Stream:      false,
		Temperature: 0.7,
	}

	result, err := converter.ConvertRequest(openAIReq, ProtocolOpenAI, ProtocolAnthropic)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	anthropicReq, ok := result.(*models.AnthropicMessagesRequest)
	if !ok {
		t.Fatalf("Expected *AnthropicMessagesRequest, got %T", result)
	}

	if anthropicReq.Model != "gpt-4" {
		t.Errorf("Model = %s, want gpt-4", anthropicReq.Model)
	}
	if anthropicReq.MaxTokens != 100 {
		t.Errorf("MaxTokens = %d, want 100", anthropicReq.MaxTokens)
	}
	if anthropicReq.Temperature != 0.7 {
		t.Errorf("Temperature = %f, want 0.7", anthropicReq.Temperature)
	}
	if len(anthropicReq.Messages) != 2 {
		t.Errorf("Messages count = %d, want 2", len(anthropicReq.Messages))
	}
}

func TestConvertRequest_OpenAIToAnthropic_WithSystem(t *testing.T) {
	converter := NewProtocolConverter()

	openAIReq := &ChatRequest{
		Model: "gpt-4",
		Messages: []ChatMessage{
			{Role: "system", Content: ChatMessageContent{StringContent: "You are helpful"}},
			{Role: "user", Content: ChatMessageContent{StringContent: "Hello"}},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(openAIReq, ProtocolOpenAI, ProtocolAnthropic)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	anthropicReq := result.(*models.AnthropicMessagesRequest)

	if anthropicReq.System.GetText() != "You are helpful" {
		t.Errorf("System = %s, want 'You are helpful'", anthropicReq.System.GetText())
	}
	if len(anthropicReq.Messages) != 1 {
		t.Errorf("Messages count = %d, want 1 (system should be separate)", len(anthropicReq.Messages))
	}
}

func TestConvertRequest_OpenAIToAnthropic_WithImage(t *testing.T) {
	converter := NewProtocolConverter()

	openAIReq := &ChatRequest{
		Model: "gpt-4-vision",
		Messages: []ChatMessage{
			{
				Role: "user",
				Content: ChatMessageContent{
					Parts: []ChatContentPart{
						{Type: "text", Text: "What's in this image?"},
						{Type: "image_url", ImageURL: &ChatImageURL{URL: "data:image/jpeg;base64,/9j/4AAQSkZJRg=="}},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(openAIReq, ProtocolOpenAI, ProtocolAnthropic)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	anthropicReq := result.(*models.AnthropicMessagesRequest)

	if len(anthropicReq.Messages) != 1 {
		t.Fatalf("Messages count = %d, want 1", len(anthropicReq.Messages))
	}

	if len(anthropicReq.Messages[0].Content.Blocks) != 2 {
		t.Errorf("Content blocks = %d, want 2 (text + image)", len(anthropicReq.Messages[0].Content.Blocks))
	}

	// Check text block
	if anthropicReq.Messages[0].Content.Blocks[0].Type != "text" {
		t.Errorf("First block type = %s, want text", anthropicReq.Messages[0].Content.Blocks[0].Type)
	}
	if anthropicReq.Messages[0].Content.Blocks[0].Text != "What's in this image?" {
		t.Errorf("First block text = %s, want 'What's in this image?'", anthropicReq.Messages[0].Content.Blocks[0].Text)
	}

	// Check image block
	if anthropicReq.Messages[0].Content.Blocks[1].Type != "image" {
		t.Errorf("Second block type = %s, want image", anthropicReq.Messages[0].Content.Blocks[1].Type)
	}
	if anthropicReq.Messages[0].Content.Blocks[1].Source == nil {
		t.Error("Image block should have source")
	} else {
		if anthropicReq.Messages[0].Content.Blocks[1].Source.Type != "base64" {
			t.Errorf("Image source type = %s, want base64", anthropicReq.Messages[0].Content.Blocks[1].Source.Type)
		}
		if anthropicReq.Messages[0].Content.Blocks[1].Source.MediaType != "image/jpeg" {
			t.Errorf("Image media type = %s, want image/jpeg", anthropicReq.Messages[0].Content.Blocks[1].Source.MediaType)
		}
	}
}

func TestConvertRequest_AnthropicToOpenAI_Basic(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
		},
		MaxTokens: 100,
		Stream:    false,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq, ok := result.(*ChatRequest)
	if !ok {
		t.Fatalf("Expected *ChatRequest, got %T", result)
	}

	if openAIReq.Model != "claude-3-5-sonnet" {
		t.Errorf("Model = %s, want claude-3-5-sonnet", openAIReq.Model)
	}
	if openAIReq.MaxTokens != 100 {
		t.Errorf("MaxTokens = %d, want 100", openAIReq.MaxTokens)
	}
	if len(openAIReq.Messages) != 1 {
		t.Errorf("Messages count = %d, want 1", len(openAIReq.Messages))
	}
}

func TestConvertRequest_AnthropicToOpenAI_WithSystem(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
		},
		System:    models.AnthropicSystem{StringContent: "You are helpful"},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Messages) != 2 {
		t.Errorf("Messages count = %d, want 2 (system + user)", len(openAIReq.Messages))
	}
	if openAIReq.Messages[0].Role != "system" {
		t.Errorf("First message role = %s, want system", openAIReq.Messages[0].Role)
	}
	if openAIReq.Messages[0].Content.GetText() != "You are helpful" {
		t.Errorf("System content = %s, want 'You are helpful'", openAIReq.Messages[0].Content.GetText())
	}
}

func TestConvertRequest_AnthropicToOpenAI_WithSystemArray(t *testing.T) {
	converter := NewProtocolConverter()

	// Test with system as array (new format)
	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
		},
		System: models.AnthropicSystem{
			Blocks: []models.AnthropicContentBlock{
				{Type: "text", Text: "You are helpful. "},
				{Type: "text", Text: "Be concise."},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Messages) != 2 {
		t.Errorf("Messages count = %d, want 2 (system + user)", len(openAIReq.Messages))
	}
	if openAIReq.Messages[0].Role != "system" {
		t.Errorf("First message role = %s, want system", openAIReq.Messages[0].Role)
	}
	expectedSystem := "You are helpful. Be concise."
	if openAIReq.Messages[0].Content.GetText() != expectedSystem {
		t.Errorf("System content = %s, want '%s'", openAIReq.Messages[0].Content.GetText(), expectedSystem)
	}
}

func TestAnthropicSystemJSONParsing(t *testing.T) {
	// Test system as string
	jsonStr := `{"model":"claude-3","max_tokens":100,"messages":[],"system":"You are helpful"}`
	var req1 models.AnthropicMessagesRequest
	if err := json.Unmarshal([]byte(jsonStr), &req1); err != nil {
		t.Fatalf("Failed to parse system as string: %v", err)
	}
	if req1.System.StringContent != "You are helpful" {
		t.Errorf("System.StringContent = %s, want 'You are helpful'", req1.System.StringContent)
	}
	if req1.System.GetText() != "You are helpful" {
		t.Errorf("System.GetText() = %s, want 'You are helpful'", req1.System.GetText())
	}

	// Test system as array
	jsonArr := `{"model":"claude-3","max_tokens":100,"messages":[],"system":[{"type":"text","text":"You are helpful. "},{"type":"text","text":"Be concise."}]}`
	var req2 models.AnthropicMessagesRequest
	if err := json.Unmarshal([]byte(jsonArr), &req2); err != nil {
		t.Fatalf("Failed to parse system as array: %v", err)
	}
	if len(req2.System.Blocks) != 2 {
		t.Errorf("System.Blocks length = %d, want 2", len(req2.System.Blocks))
	}
	expectedText := "You are helpful. Be concise."
	if req2.System.GetText() != expectedText {
		t.Errorf("System.GetText() = %s, want '%s'", req2.System.GetText(), expectedText)
	}

	// Test marshaling back to JSON
	// String format should remain as string
	data1, err := json.Marshal(req1.System)
	if err != nil {
		t.Fatalf("Failed to marshal string system: %v", err)
	}
	if string(data1) != `"You are helpful"` {
		t.Errorf("Marshaled string system = %s, want '\"You are helpful\"'", string(data1))
	}

	// Array format should remain as array
	data2, err := json.Marshal(req2.System)
	if err != nil {
		t.Fatalf("Failed to marshal array system: %v", err)
	}
	if !strings.Contains(string(data2), `"type":"text"`) {
		t.Errorf("Marshaled array system should contain type:text, got %s", string(data2))
	}
}

func TestConvertRequest_AnthropicToOpenAI_WithImage(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{
				Role: "user",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{Type: "text", Text: "What's in this image?"},
						{
							Type: "image",
							Source: &models.AnthropicImageSource{
								Type:      "base64",
								MediaType: "image/jpeg",
								Data:      "/9j/4AAQSkZJRg==",
							},
						},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Messages) != 1 {
		t.Fatalf("Messages count = %d, want 1", len(openAIReq.Messages))
	}

	if len(openAIReq.Messages[0].Content.Parts) != 2 {
		t.Errorf("Content parts = %d, want 2 (text + image)", len(openAIReq.Messages[0].Content.Parts))
	}

	// Check text part
	if openAIReq.Messages[0].Content.Parts[0].Type != "text" {
		t.Errorf("First part type = %s, want text", openAIReq.Messages[0].Content.Parts[0].Type)
	}
	if openAIReq.Messages[0].Content.Parts[0].Text != "What's in this image?" {
		t.Errorf("First part text = %s, want 'What's in this image?'", openAIReq.Messages[0].Content.Parts[0].Text)
	}

	// Check image part
	if openAIReq.Messages[0].Content.Parts[1].Type != "image_url" {
		t.Errorf("Second part type = %s, want image_url", openAIReq.Messages[0].Content.Parts[1].Type)
	}
	if openAIReq.Messages[0].Content.Parts[1].ImageURL == nil {
		t.Error("Image part should have image_url")
	} else {
		expectedURL := "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
		if openAIReq.Messages[0].Content.Parts[1].ImageURL.URL != expectedURL {
			t.Errorf("Image URL = %s, want %s", openAIReq.Messages[0].Content.Parts[1].ImageURL.URL, expectedURL)
		}
	}
}
func TestConvertRequest_AnthropicToOpenAI_WithTools(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "What's the weather?"}},
		},
		Tools: []models.AnthropicTool{
			{
				Name:        "get_weather",
				Description: "Get weather in a city",
				InputSchema: map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"city": map[string]interface{}{"type": "string"},
					},
				},
			},
		},
		ToolChoice: &models.AnthropicToolChoice{Type: "auto"},
		TopP:       0.9,
		MaxTokens:  100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Tools) != 1 {
		t.Errorf("Tools count = %d, want 1", len(openAIReq.Tools))
	}
	if openAIReq.Tools[0].Function.Name != "get_weather" {
		t.Errorf("Tool name = %s, want get_weather", openAIReq.Tools[0].Function.Name)
	}
	if openAIReq.Extra["top_p"] != 0.9 {
		t.Errorf("top_p = %v, want 0.9", openAIReq.Extra["top_p"])
	}
	if openAIReq.Extra["tool_choice"] != "auto" {
		t.Errorf("tool_choice = %v, want auto", openAIReq.Extra["tool_choice"])
	}

	// Verify JSON marshaling includes Extra fields
	data, _ := json.Marshal(openAIReq)
	var m map[string]interface{}
	json.Unmarshal(data, &m)
	if m["top_p"] != 0.9 {
		t.Errorf("JSON marshaled top_p = %v, want 0.9", m["top_p"])
	}
	if m["tool_choice"] != "auto" {
		t.Errorf("JSON marshaled tool_choice = %v, want auto", m["tool_choice"])
	}
}

func TestConvertRequest_AnthropicToOpenAI_NoConversion(t *testing.T) {
	converter := NewProtocolConverter()

	openAIReq := &ChatRequest{
		Model: "gpt-4",
		Messages: []ChatMessage{
			{Role: "user", Content: ChatMessageContent{StringContent: "Hello"}},
		},
	}

	// Same protocol - should return same request
	result, err := converter.ConvertRequest(openAIReq, ProtocolOpenAI, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	if result != openAIReq {
		t.Error("Expected same request object when protocols match")
	}
}

func TestConvertResponse_OpenAIToAnthropic_Basic(t *testing.T) {
	converter := NewProtocolConverter()

	openAIResp := &ChatResponse{
		ID:     "chatcmpl-123",
		Model:  "gpt-4",
		Object: "chat.completion",
		Choices: []Choice{
			{
				Index: 0,
				Message: &ChatMessage{
					Role:    "assistant",
					Content: ChatMessageContent{StringContent: "Hello! How can I help?"},
				},
				FinishReason: "stop",
			},
		},
		Usage: &Usage{
			PromptTokens:     10,
			CompletionTokens: 5,
		},
	}

	result, err := converter.ConvertResponse(openAIResp, ProtocolOpenAI, ProtocolAnthropic, "gpt-4")
	if err != nil {
		t.Fatalf("ConvertResponse failed: %v", err)
	}

	anthropicResp, ok := result.(*models.AnthropicMessagesResponse)
	if !ok {
		t.Fatalf("Expected *AnthropicMessagesResponse, got %T", result)
	}

	if anthropicResp.Type != "message" {
		t.Errorf("Type = %s, want message", anthropicResp.Type)
	}
	if anthropicResp.Role != "assistant" {
		t.Errorf("Role = %s, want assistant", anthropicResp.Role)
	}
	if len(anthropicResp.Content) != 1 {
		t.Errorf("Content count = %d, want 1", len(anthropicResp.Content))
	}
	if anthropicResp.Content[0].Text != "Hello! How can I help?" {
		t.Errorf("Content text = %s, want 'Hello! How can I help?'", anthropicResp.Content[0].Text)
	}
	if anthropicResp.StopReason != models.AnthropicStopEndTurn {
		t.Errorf("StopReason = %s, want end_turn", anthropicResp.StopReason)
	}
	if anthropicResp.Usage.InputTokens != 10 {
		t.Errorf("InputTokens = %d, want 10", anthropicResp.Usage.InputTokens)
	}
}

func TestConvertResponse_AnthropicToOpenAI_Basic(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicResp := &models.AnthropicMessagesResponse{
		ID:   "msg_123",
		Type: "message",
		Role: "assistant",
		Content: []models.AnthropicContentBlock{
			{Type: "text", Text: "Hello! How can I help?"},
		},
		Model:      "claude-3-5-sonnet",
		StopReason: models.AnthropicStopEndTurn,
		Usage: &models.AnthropicUsage{
			InputTokens:  10,
			OutputTokens: 5,
		},
	}

	result, err := converter.ConvertResponse(anthropicResp, ProtocolAnthropic, ProtocolOpenAI, "")
	if err != nil {
		t.Fatalf("ConvertResponse failed: %v", err)
	}

	openAIResp, ok := result.(*ChatResponse)
	if !ok {
		t.Fatalf("Expected *ChatResponse, got %T", result)
	}

	if openAIResp.Object != "chat.completion" {
		t.Errorf("Object = %s, want chat.completion", openAIResp.Object)
	}
	if len(openAIResp.Choices) != 1 {
		t.Errorf("Choices count = %d, want 1", len(openAIResp.Choices))
	}
	if openAIResp.Choices[0].Message.Content.GetText() != "Hello! How can I help?" {
		t.Errorf("Message content = %s, want 'Hello! How can I help?'", openAIResp.Choices[0].Message.Content.GetText())
	}
	if openAIResp.Choices[0].FinishReason != "stop" {
		t.Errorf("FinishReason = %s, want stop", openAIResp.Choices[0].FinishReason)
	}
	if openAIResp.Usage.PromptTokens != 10 {
		t.Errorf("PromptTokens = %d, want 10", openAIResp.Usage.PromptTokens)
	}
}
func TestChatRequest_MarshalJSON(t *testing.T) {
	req := &ChatRequest{
		Model: "gpt-4",
		Messages: []ChatMessage{
			{Role: "user", Content: ChatMessageContent{StringContent: "Hello"}},
		},
		Extra: map[string]interface{}{
			"top_p":       0.9,
			"tool_choice": "auto",
		},
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("Marshal failed: %v", err)
	}

	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}

	if m["model"] != "gpt-4" {
		t.Errorf("model = %v, want gpt-4", m["model"])
	}
	if m["top_p"] != 0.9 {
		t.Errorf("top_p = %v, want 0.9", m["top_p"])
	}
	if m["tool_choice"] != "auto" {
		t.Errorf("tool_choice = %v, want auto", m["tool_choice"])
	}
}

func TestConvertFinishReason(t *testing.T) {
	tests := []struct {
		openAI    string
		anthropic string
	}{
		{"stop", models.AnthropicStopEndTurn},
		{"length", models.AnthropicStopMaxTokens},
		{"content_filter", models.AnthropicStopSequence},
		{"tool_calls", models.AnthropicStopToolUse},
		{"unknown", models.AnthropicStopEndTurn},
	}

	for _, tt := range tests {
		t.Run(tt.openAI, func(t *testing.T) {
			result := convertFinishReasonToAnthropic(tt.openAI)
			if result != tt.anthropic {
				t.Errorf("convertFinishReasonToAnthropic(%s) = %s, want %s", tt.openAI, result, tt.anthropic)
			}
		})
	}
}

func TestConvertStopReason(t *testing.T) {
	tests := []struct {
		anthropic string
		openAI    string
	}{
		{models.AnthropicStopEndTurn, "stop"},
		{models.AnthropicStopMaxTokens, "length"},
		{models.AnthropicStopSequence, "stop"},
		{models.AnthropicStopToolUse, "tool_calls"},
		{"unknown", "stop"},
	}

	for _, tt := range tests {
		t.Run(tt.anthropic, func(t *testing.T) {
			result := convertStopReasonToOpenAI(tt.anthropic)
			if result != tt.openAI {
				t.Errorf("convertStopReasonToOpenAI(%s) = %s, want %s", tt.anthropic, result, tt.openAI)
			}
		})
	}
}

func TestGenerateMessageID(t *testing.T) {
	id := generateMessageID()

	if !strings.HasPrefix(id, "msg_") {
		t.Errorf("Message ID should start with 'msg_', got %s", id)
	}
	if len(id) != 28 { // "msg_" + 24 chars
		t.Errorf("Message ID length = %d, want 28", len(id))
	}
}

func TestGenerateAnthropicStreamEvents(t *testing.T) {
	converter := NewProtocolConverter()

	// Test message_start
	start := converter.GenerateAnthropicStreamStart("msg_test123", "claude-3")
	if !strings.Contains(start, "event: message_start") {
		t.Error("message_start event should contain 'event: message_start'")
	}
	if !strings.Contains(start, `"id":"msg_test123"`) {
		t.Error("message_start event should contain the message ID")
	}
	if !strings.Contains(start, `"model":"claude-3"`) {
		t.Error("message_start event should contain the model name")
	}
	if !strings.HasSuffix(start, "\n\n") {
		t.Error("SSE event should end with double newline")
	}

	// Test content_block_start
	blockStart := converter.GenerateAnthropicContentBlockStart(0, "text")
	if !strings.Contains(blockStart, "event: content_block_start") {
		t.Error("content_block_start event should contain 'event: content_block_start'")
	}
	if !strings.Contains(blockStart, `"type":"text"`) {
		t.Error("content_block_start event should contain the block type")
	}

	// Test content_block_delta
	delta := converter.GenerateAnthropicContentDelta(0, "Hello")
	if !strings.Contains(delta, "event: content_block_delta") {
		t.Error("content_block_delta event should contain 'event: content_block_delta'")
	}
	if !strings.Contains(delta, "Hello") {
		t.Error("content_block_delta event should contain the text")
	}

	// Test thinking_delta
	thinkingDelta := converter.GenerateAnthropicThinkingDelta(0, "Hmm...")
	if !strings.Contains(thinkingDelta, "thinking_delta") {
		t.Error("thinking_delta event should contain 'thinking_delta'")
	}
	if !strings.Contains(thinkingDelta, "Hmm...") {
		t.Error("thinking_delta event should contain the thinking text")
	}

	// Test content_block_stop
	blockStop := converter.GenerateAnthropicContentBlockStop(0)
	if !strings.Contains(blockStop, "event: content_block_stop") {
		t.Error("content_block_stop event should contain 'event: content_block_stop'")
	}

	// Test message_delta
	msgDelta := converter.GenerateAnthropicMessageDelta(models.AnthropicStopEndTurn, 10)
	if !strings.Contains(msgDelta, "event: message_delta") {
		t.Error("message_delta event should contain 'event: message_delta'")
	}
	if !strings.Contains(msgDelta, "end_turn") {
		t.Error("message_delta event should contain the stop reason")
	}

	// Test message_stop
	msgStop := converter.GenerateAnthropicMessageStop()
	if !strings.Contains(msgStop, "event: message_stop") {
		t.Error("message_stop event should contain 'event: message_stop'")
	}
}

func TestConvertOpenAIStreamChunkToAnthropic(t *testing.T) {
	converter := NewProtocolConverter()
	state := &StreamConversionState{}
	contentIndex := 0

	// First chunk with content
	chunk1 := &StreamChunk{
		ID: "chatcmpl-123",
	}
	chunk1.Choices = []struct {
		Index int `json:"index"`
		Delta struct {
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning        string     `json:"reasoning,omitempty"`
			ReasoningContent string     `json:"reasoning_content,omitempty"`
			ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{
			Index: 0,
		},
	}
	chunk1.Choices[0].Delta.Role = "assistant"
	chunk1.Choices[0].Delta.Content = "Hello"

	result := converter.ConvertOpenAIStreamChunkToAnthropic(chunk1, "msg_test", "claude-3", &contentIndex, state)

	// Should contain message_start, content_block_start, and content_block_delta
	if !strings.Contains(result, "message_start") {
		t.Error("First chunk should contain message_start event")
	}
	if !strings.Contains(result, `"model":"claude-3"`) {
		t.Error("message_start should contain model name")
	}
	if !strings.Contains(result, "content_block_start") {
		t.Error("First chunk should contain content_block_start event")
	}
	if !strings.Contains(result, "content_block_delta") {
		t.Error("First chunk should contain content_block_delta event")
	}
	if !state.MessageStarted {
		t.Error("State should show MessageStarted = true")
	}
	if !state.ContentBlockStarted {
		t.Error("State should show ContentBlockStarted = true")
	}

	// Second chunk with finish reason
	finishReason := "stop"
	chunk2 := &StreamChunk{
		ID: "chatcmpl-123",
	}
	chunk2.Choices = []struct {
		Index int `json:"index"`
		Delta struct {
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning        string     `json:"reasoning,omitempty"`
			ReasoningContent string     `json:"reasoning_content,omitempty"`
			ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{
			Index:        0,
			FinishReason: &finishReason,
		},
	}

	result2 := converter.ConvertOpenAIStreamChunkToAnthropic(chunk2, "msg_test", "claude-3", &contentIndex, state)

	// Should contain content_block_stop, message_delta, and message_stop
	if !strings.Contains(result2, "content_block_stop") {
		t.Error("Final chunk should contain content_block_stop event")
	}
	if !strings.Contains(result2, "message_delta") {
		t.Error("Final chunk should contain message_delta event")
	}
	if !strings.Contains(result2, "message_stop") {
		t.Error("Final chunk should contain message_stop event")
	}
	if !state.MessageFinished {
		t.Error("State should show MessageFinished = true")
	}
}

func TestConvertOpenAIStreamChunkToAnthropic_Reasoning(t *testing.T) {
	converter := NewProtocolConverter()
	state := &StreamConversionState{}
	contentIndex := 0

	// First chunk with reasoning
	chunk1 := &StreamChunk{}
	chunk1.Choices = []struct {
		Index int `json:"index"`
		Delta struct {
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning        string     `json:"reasoning,omitempty"`
			ReasoningContent string     `json:"reasoning_content,omitempty"`
			ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{Index: 0},
	}
	chunk1.Choices[0].Delta.Reasoning = "Let me think..."

	result := converter.ConvertOpenAIStreamChunkToAnthropic(chunk1, "msg_test", "claude-3", &contentIndex, state)

	if !strings.Contains(result, "content_block_start") {
		t.Error("Should contain content_block_start for reasoning")
	}
	if !strings.Contains(result, "thinking_delta") {
		t.Error("Should contain thinking_delta")
	}
	if !state.ThinkingStarted {
		t.Error("State should show ThinkingStarted = true")
	}

	// Second chunk with content
	chunk2 := &StreamChunk{}
	chunk2.Choices = []struct {
		Index int `json:"index"`
		Delta struct {
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning        string     `json:"reasoning,omitempty"`
			ReasoningContent string     `json:"reasoning_content,omitempty"`
			ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{Index: 0},
	}
	chunk2.Choices[0].Delta.Content = "The answer is 42."

	result2 := converter.ConvertOpenAIStreamChunkToAnthropic(chunk2, "msg_test", "claude-3", &contentIndex, state)

	if !strings.Contains(result2, "content_block_stop") {
		t.Error("Should close thinking block")
	}
	if !strings.Contains(result2, "content_block_start") {
		t.Error("Should start new content block for text")
	}
	if !strings.Contains(result2, "text_delta") {
		t.Error("Should contain text_delta")
	}
	if contentIndex != 1 {
		t.Errorf("contentIndex = %d, want 1", contentIndex)
	}
}

func TestConvertOpenAIStreamChunkToAnthropic_ToolUse(t *testing.T) {
	converter := NewProtocolConverter()
	state := &StreamConversionState{
		LastToolIndex: -1,
	}
	contentIndex := 0

	// First chunk with tool use
	chunk1 := &StreamChunk{}
	chunk1.Choices = []struct {
		Index int `json:"index"`
		Delta struct {
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning        string     `json:"reasoning,omitempty"`
			ReasoningContent string     `json:"reasoning_content,omitempty"`
			ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{Index: 0},
	}
	chunk1.Choices[0].Delta.ToolCalls = []ToolCall{
		{
			Index: 0,
			ID:    "tool_123",
			Type:  "function",
			Function: FunctionCall{
				Name: "get_weather",
			},
		},
	}

	result := converter.ConvertOpenAIStreamChunkToAnthropic(chunk1, "msg_test", "claude-3", &contentIndex, state)

	if !strings.Contains(result, "content_block_start") {
		t.Error("Should contain content_block_start for tool_use")
	}
	if !strings.Contains(result, "tool_use") {
		t.Error("Should contain tool_use type")
	}
	if !strings.Contains(result, "get_weather") {
		t.Error("Should contain tool name")
	}
	if !state.ToolUseStarted {
		t.Error("State should show ToolUseStarted = true")
	}

	// Second chunk with arguments
	chunk2 := &StreamChunk{}
	chunk2.Choices = []struct {
		Index int `json:"index"`
		Delta struct {
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning        string     `json:"reasoning,omitempty"`
			ReasoningContent string     `json:"reasoning_content,omitempty"`
			ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{Index: 0},
	}
	chunk2.Choices[0].Delta.ToolCalls = []ToolCall{
		{
			Index: 0,
			Function: FunctionCall{
				Arguments: `{"city": "London"}`,
			},
		},
	}

	result2 := converter.ConvertOpenAIStreamChunkToAnthropic(chunk2, "msg_test", "claude-3", &contentIndex, state)

	if !strings.Contains(result2, "input_json_delta") {
		t.Error("Should contain input_json_delta")
	}
	if !strings.Contains(result2, `{\"city\": \"London\"}`) {
		t.Error("Should contain partial arguments")
	}
}

// Test multiple messages conversion
func TestConvertRequest_AnthropicToOpenAI_MultipleMessages(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "What is AI?"}},
			{Role: "assistant", Content: models.AnthropicContent{StringContent: "AI is artificial intelligence."}},
			{Role: "user", Content: models.AnthropicContent{StringContent: "Can you give examples?"}},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Messages) != 3 {
		t.Errorf("Messages count = %d, want 3", len(openAIReq.Messages))
	}

	if openAIReq.Messages[0].Role != "user" {
		t.Errorf("First message role = %s, want user", openAIReq.Messages[0].Role)
	}
	if openAIReq.Messages[0].Content.GetText() != "What is AI?" {
		t.Errorf("First message content = %s, want 'What is AI?'", openAIReq.Messages[0].Content.GetText())
	}
	if openAIReq.Messages[1].Role != "assistant" {
		t.Errorf("Second message role = %s, want assistant", openAIReq.Messages[1].Role)
	}
}

// Test long text conversion
func TestConvertRequest_AnthropicToOpenAI_LongText(t *testing.T) {
	converter := NewProtocolConverter()

	longText := "This is a very long text message that contains multiple sentences and paragraphs. It tests the converter's ability to handle large content without truncation or errors. The content should be preserved exactly as provided in the original message."

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: longText}},
		},
		MaxTokens: 1000,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if openAIReq.Messages[0].Content.GetText() != longText {
		t.Errorf("Long text content not preserved correctly")
	}
}

// Test mixed content (text + image)
func TestConvertRequest_AnthropicToOpenAI_MixedContent(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{
				Role: "user",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{Type: "text", Text: "What's in this image?"},
						{
							Type: "image",
							Source: &models.AnthropicImageSource{
								Type:      "base64",
								MediaType: "image/jpeg",
								Data:      "/9j/4AAQSkZJRg==",
							},
						},
						{Type: "text", Text: "And can you also describe the text below?"},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Messages) != 1 {
		t.Fatalf("Messages count = %d, want 1", len(openAIReq.Messages))
	}

	// Text blocks are now preserved as separate parts
	if len(openAIReq.Messages[0].Content.Parts) != 3 {
		t.Errorf("Content parts = %d, want 3 (separate parts)", len(openAIReq.Messages[0].Content.Parts))
	}

	// Check first text part
	if openAIReq.Messages[0].Content.Parts[0].Type != "text" {
		t.Errorf("First part type = %s, want text", openAIReq.Messages[0].Content.Parts[0].Type)
	}
	if openAIReq.Messages[0].Content.Parts[0].Text != "What's in this image?" {
		t.Errorf("First part text = %s, want 'What's in this image?'", openAIReq.Messages[0].Content.Parts[0].Text)
	}

	// Check second image part
	if openAIReq.Messages[0].Content.Parts[1].Type != "image_url" {
		t.Errorf("Second part type = %s, want image_url", openAIReq.Messages[0].Content.Parts[1].Type)
	}

	// Check third text part
	if openAIReq.Messages[0].Content.Parts[2].Type != "text" {
		t.Errorf("Third part type = %s, want text", openAIReq.Messages[0].Content.Parts[2].Type)
	}
	if openAIReq.Messages[0].Content.Parts[2].Text != "And can you also describe the text below?" {
		t.Errorf("Third part text = %s, want 'And can you also describe the text below?'", openAIReq.Messages[0].Content.Parts[2].Text)
	}
	expectedURL := "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
	if openAIReq.Messages[0].Content.Parts[1].ImageURL.URL != expectedURL {
		t.Errorf("Image URL = %s, want %s", openAIReq.Messages[0].Content.Parts[1].ImageURL.URL, expectedURL)
	}
}

// Test conversation history with system message
func TestConvertRequest_AnthropicToOpenAI_ConversationHistory(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		System: models.AnthropicSystem{StringContent: "You are a helpful assistant that speaks concisely."},
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
			{Role: "assistant", Content: models.AnthropicContent{StringContent: "Hi! How can I help?"}},
			{Role: "user", Content: models.AnthropicContent{StringContent: "What is 2+2?"}},
			{Role: "assistant", Content: models.AnthropicContent{StringContent: "2+2 equals 4."}},
			{Role: "user", Content: models.AnthropicContent{StringContent: "Thanks"}},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	// Should have system + 5 messages = 6 total
	if len(openAIReq.Messages) != 6 {
		t.Errorf("Messages count = %d, want 6 (system + 5 messages)", len(openAIReq.Messages))
	}

	// Check system message is first
	if openAIReq.Messages[0].Role != "system" {
		t.Errorf("First message role = %s, want system", openAIReq.Messages[0].Role)
	}
	if openAIReq.Messages[0].Content.GetText() != "You are a helpful assistant that speaks concisely." {
		t.Errorf("System content = %s, want 'You are a helpful assistant that speaks concisely.'", openAIReq.Messages[0].Content.GetText())
	}
}

// Test URL-based image source
func TestConvertRequest_AnthropicToOpenAI_ImageURL(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{
				Role: "user",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{
							Type: "image",
							Source: &models.AnthropicMediaSource{
								Type: "url",
								URL:  "https://example.com/image.jpg",
							},
						},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if openAIReq.Messages[0].Content.Parts[0].Type != "image_url" {
		t.Errorf("Part type = %s, want image_url", openAIReq.Messages[0].Content.Parts[0].Type)
	}
	if openAIReq.Messages[0].Content.Parts[0].ImageURL.URL != "https://example.com/image.jpg" {
		t.Errorf("Image URL = %s, want https://example.com/image.jpg", openAIReq.Messages[0].Content.Parts[0].ImageURL.URL)
	}
}

// Test response conversion with usage
func TestConvertResponse_AnthropicToOpenAI_WithUsage(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicResp := &models.AnthropicMessagesResponse{
		ID:   "msg_123",
		Type: "message",
		Role: "assistant",
		Content: []models.AnthropicContentBlock{
			{Type: "text", Text: "Hello!"},
		},
		Model:      "claude-3-5-sonnet",
		StopReason: models.AnthropicStopEndTurn,
		Usage: &models.AnthropicUsage{
			InputTokens:  100,
			OutputTokens: 50,
		},
	}

	result, err := converter.ConvertResponse(anthropicResp, ProtocolAnthropic, ProtocolOpenAI, "")
	if err != nil {
		t.Fatalf("ConvertResponse failed: %v", err)
	}

	openAIResp := result.(*ChatResponse)

	if openAIResp.Usage.PromptTokens != 100 {
		t.Errorf("PromptTokens = %d, want 100", openAIResp.Usage.PromptTokens)
	}
	if openAIResp.Usage.CompletionTokens != 50 {
		t.Errorf("CompletionTokens = %d, want 50", openAIResp.Usage.CompletionTokens)
	}
}

func TestConvertRequest_AnthropicToOpenAI_WithToolUse(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{
				Role: "assistant",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{Type: "text", Text: "I'll check the weather."},
						{
							Type: "tool_use",
							ID:   "tool_123",
							Name: "get_weather",
							Input: map[string]interface{}{
								"city": "London",
							},
						},
					},
				},
			},
			{
				Role: "user",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{
							Type:      "tool_result",
							ToolUseID: "tool_123",
							Content:   "The weather is sunny.",
						},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	if len(openAIReq.Messages) != 2 {
		t.Fatalf("Messages count = %d, want 2", len(openAIReq.Messages))
	}

	// Check tool call message
	msg1 := openAIReq.Messages[0]
	if msg1.Role != "assistant" {
		t.Errorf("First message role = %s, want assistant", msg1.Role)
	}
	if len(msg1.ToolCalls) != 1 {
		t.Errorf("First message tool calls = %d, want 1", len(msg1.ToolCalls))
	}
	if msg1.ToolCalls[0].ID != "tool_123" {
		t.Errorf("Tool call ID = %s, want tool_123", msg1.ToolCalls[0].ID)
	}

	// Check tool result message
	msg2 := openAIReq.Messages[1]
	if msg2.Role != "tool" {
		t.Errorf("Second message role = %s, want tool", msg2.Role)
	}
	if msg2.ToolCallID != "tool_123" {
		t.Errorf("Tool call ID = %s, want tool_123", msg2.ToolCallID)
	}
	if msg2.Content.StringContent != "The weather is sunny." {
		t.Errorf("Tool result content = %s, want 'The weather is sunny.'", msg2.Content.StringContent)
	}
}

func TestConvertRequest_AnthropicToOpenAI_MultipleToolResults(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-5-sonnet",
		Messages: []models.AnthropicMessage{
			{
				Role: "assistant",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{
							Type:  "tool_use",
							ID:    "tool_1",
							Name:  "get_weather",
							Input: map[string]interface{}{"city": "London"},
						},
						{
							Type:  "tool_use",
							ID:    "tool_2",
							Name:  "get_time",
							Input: map[string]interface{}{"city": "London"},
						},
					},
				},
			},
			{
				Role: "user",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{Type: "text", Text: "Here are the results:"},
						{
							Type:      "tool_result",
							ToolUseID: "tool_1",
							Content:   "Sunny",
						},
						{
							Type:      "tool_result",
							ToolUseID: "tool_2",
							Content:   "12:00",
						},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	// Should have assistant (tool_use) + user (text) + tool (result 1) + tool (result 2)
	if len(openAIReq.Messages) != 4 {
		t.Fatalf("Messages count = %d, want 4", len(openAIReq.Messages))
	}

	if openAIReq.Messages[1].Role != "user" {
		t.Errorf("Message 1 role = %s, want user", openAIReq.Messages[1].Role)
	}
	if openAIReq.Messages[1].Content.StringContent != "Here are the results:" {
		t.Errorf("Message 1 content = %s, want 'Here are the results:'", openAIReq.Messages[1].Content.StringContent)
	}

	if openAIReq.Messages[2].Role != "tool" || openAIReq.Messages[2].ToolCallID != "tool_1" {
		t.Errorf("Message 2 should be tool result for tool_1")
	}
	if openAIReq.Messages[3].Role != "tool" || openAIReq.Messages[3].ToolCallID != "tool_2" {
		t.Errorf("Message 3 should be tool result for tool_2")
	}
}

func TestConvertRequest_AnthropicToOpenAI_ThinkingBlock(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "claude-3-7-sonnet",
		Messages: []models.AnthropicMessage{
			{
				Role: "user",
				Content: models.AnthropicContent{
					Blocks: []models.AnthropicContentBlock{
						{Type: "thinking", Thinking: "I should use a tool."},
						{Type: "text", Text: "What is the weather?"},
					},
				},
			},
		},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	openAIReq := result.(*ChatRequest)

	expectedContent := "<think>I should use a tool.</think>What is the weather?"
	if openAIReq.Messages[0].Content.GetText() != expectedContent {
		t.Errorf("Content = %s, want %s", openAIReq.Messages[0].Content.GetText(), expectedContent)
	}
}

func TestConvertResponse_OpenAIToAnthropic_WithReasoning(t *testing.T) {
	converter := NewProtocolConverter()

	openAIResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Role:      "assistant",
					Content:   ChatMessageContent{StringContent: "The answer is 42."},
					Reasoning: "Calculating...",
				},
			},
		},
	}

	result, err := converter.ConvertResponse(openAIResp, ProtocolOpenAI, ProtocolAnthropic, "claude-3")
	if err != nil {
		t.Fatalf("ConvertResponse failed: %v", err)
	}

	anthropicResp := result.(*models.AnthropicMessagesResponse)

	if len(anthropicResp.Content) != 2 {
		t.Fatalf("Content count = %d, want 2", len(anthropicResp.Content))
	}
	if anthropicResp.Content[0].Type != "thinking" || anthropicResp.Content[0].Thinking != "Calculating..." {
		t.Errorf("First block should be thinking")
	}
	if anthropicResp.Content[1].Type != "text" || anthropicResp.Content[1].Text != "The answer is 42." {
		t.Errorf("Second block should be text")
	}
}

func TestConvertRequest_AnthropicToGemini_Basic(t *testing.T) {
	converter := NewProtocolConverter()

	anthropicReq := &models.AnthropicMessagesRequest{
		Model: "gemini-1.5-flash",
		Messages: []models.AnthropicMessage{
			{Role: "user", Content: models.AnthropicContent{StringContent: "Hello"}},
		},
		System:    models.AnthropicSystem{StringContent: "You are a helpful assistant"},
		MaxTokens: 100,
	}

	result, err := converter.ConvertRequest(anthropicReq, ProtocolAnthropic, ProtocolGemini)
	if err != nil {
		t.Fatalf("ConvertRequest failed: %v", err)
	}

	geminiReq, ok := result.(*models.GeminiGenerateContentRequest)
	if !ok {
		t.Fatalf("Expected *models.GeminiGenerateContentRequest, got %T", result)
	}

	if geminiReq.SystemInstruction == nil || geminiReq.SystemInstruction.Parts[0].Text != "You are a helpful assistant" {
		t.Errorf("System instruction not converted correctly")
	}

	if len(geminiReq.Contents) != 1 || geminiReq.Contents[0].Role != "user" || geminiReq.Contents[0].Parts[0].Text != "Hello" {
		t.Errorf("Message content not converted correctly")
	}

	if *geminiReq.GenerationConfig.MaxOutputTokens != 100 {
		t.Errorf("MaxTokens not converted correctly")
	}
}

func TestConvertResponse_GeminiToAnthropic_Basic(t *testing.T) {
	converter := NewProtocolConverter()

	geminiResp := &models.GeminiGenerateContentResponse{
		Candidates: []models.GeminiCandidate{
			{
				Content: models.GeminiContent{
					Role: "model",
					Parts: []models.GeminiPart{
						{Text: "Hi there!"},
					},
				},
				FinishReason: "STOP",
			},
		},
		UsageMetadata: &models.GeminiUsageMetadata{
			PromptTokenCount:     10,
			CandidatesTokenCount: 5,
		},
	}

	result, err := converter.ConvertResponse(geminiResp, ProtocolGemini, ProtocolAnthropic, "gemini-1.5-flash")
	if err != nil {
		t.Fatalf("ConvertResponse failed: %v", err)
	}

	anthropicResp, ok := result.(*models.AnthropicMessagesResponse)
	if !ok {
		t.Fatalf("Expected *models.AnthropicMessagesResponse, got %T", result)
	}

	if len(anthropicResp.Content) != 1 || anthropicResp.Content[0].Text != "Hi there!" {
		t.Errorf("Response text not converted correctly")
	}

	if anthropicResp.Usage.InputTokens != 10 || anthropicResp.Usage.OutputTokens != 5 {
		t.Errorf("Usage metadata not converted correctly")
	}
}

func TestConvertGeminiStreamChunkToAnthropic(t *testing.T) {
	converter := NewProtocolConverter()
	state := &StreamConversionState{}
	contentIndex := 0

	chunk := &models.GeminiGenerateContentResponse{
		Candidates: []models.GeminiCandidate{
			{
				Content: models.GeminiContent{
					Parts: []models.GeminiPart{
						{Text: "Streamed content"},
					},
				},
			},
		},
	}

	result := converter.ConvertGeminiStreamChunkToAnthropic(chunk, "msg_test", "gemini-1.5-flash", &contentIndex, state)

	if !strings.Contains(result, "message_start") {
		t.Error("Should contain message_start")
	}
	if !strings.Contains(result, "content_block_start") {
		t.Error("Should contain content_block_start")
	}
	if !strings.Contains(result, "Streamed content") {
		t.Error("Should contain streamed text")
	}
}