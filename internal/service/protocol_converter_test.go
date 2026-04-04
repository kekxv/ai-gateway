package service

import (
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

	if anthropicReq.System != "You are helpful" {
		t.Errorf("System = %s, want 'You are helpful'", anthropicReq.System)
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
		System:    "You are helpful",
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

func TestConvertRequest_NoConversion(t *testing.T) {
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

	// Test content_block_start
	blockStart := converter.GenerateAnthropicContentBlockStart(0)
	if !strings.Contains(blockStart, "event: content_block_start") {
		t.Error("content_block_start event should contain 'event: content_block_start'")
	}

	// Test content_block_delta
	delta := converter.GenerateAnthropicContentDelta(0, "Hello")
	if !strings.Contains(delta, "event: content_block_delta") {
		t.Error("content_block_delta event should contain 'event: content_block_delta'")
	}
	if !strings.Contains(delta, "Hello") {
		t.Error("content_block_delta event should contain the text")
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

	// First chunk with content
	chunk1 := &StreamChunk{
		ID: "chatcmpl-123",
	}
	chunk1.Choices = []struct {
		Index        int `json:"index"`
		Delta        struct {
			Role    string `json:"role,omitempty"`
			Content string `json:"content,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{
			Index: 0,
		},
	}
	chunk1.Choices[0].Delta.Role = "assistant"
	chunk1.Choices[0].Delta.Content = "Hello"

	result := converter.ConvertOpenAIStreamChunkToAnthropic(chunk1, "msg_test", 0, state)

	// Should contain message_start, content_block_start, and content_block_delta
	if !strings.Contains(result, "message_start") {
		t.Error("First chunk should contain message_start event")
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
		Index        int `json:"index"`
		Delta        struct {
			Role    string `json:"role,omitempty"`
			Content string `json:"content,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	}{
		{
			Index:        0,
			FinishReason: &finishReason,
		},
	}

	result2 := converter.ConvertOpenAIStreamChunkToAnthropic(chunk2, "msg_test", 0, state)

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
}