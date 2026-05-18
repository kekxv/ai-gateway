package service

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/kekxv/ai-gateway/internal/models"
)

// ============================================================
// Tests: ResponseRequest -> ChatRequest (convertResponseRequestToChatRequest)
// ============================================================

func TestConvertResponseRequestToChatRequest_SimpleStringInput(t *testing.T) {
	req := &models.ResponseRequest{
		Model:   "deepseek-chat",
		Input:   models.ResponseInput{StringInput: "Hello world"},
		Stream:  true,
		Reasoning: &models.ReasoningConfig{Effort: "medium"},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if chatReq.Model != "deepseek-chat" {
		t.Errorf("expected model deepseek-chat, got %s", chatReq.Model)
	}
	if !chatReq.Stream {
		t.Error("expected stream to be true")
	}
	if chatReq.ReasoningEffort != "medium" {
		t.Errorf("expected reasoning_effort medium, got %s", chatReq.ReasoningEffort)
	}
	if len(chatReq.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(chatReq.Messages))
	}
	if chatReq.Messages[0].Role != "user" {
		t.Errorf("expected role user, got %s", chatReq.Messages[0].Role)
	}
	if chatReq.Messages[0].Content.StringContent != "Hello world" {
		t.Errorf("expected content 'Hello world', got %q", chatReq.Messages[0].Content.StringContent)
	}
}

func TestConvertResponseRequestToChatRequest_Instructions(t *testing.T) {
	req := &models.ResponseRequest{
		Model:        "deepseek-chat",
		Input:        models.ResponseInput{StringInput: "Help me"},
		Instructions: "You are a helpful assistant.",
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if len(chatReq.Messages) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(chatReq.Messages))
	}
	// Instructions become system message in Go implementation
	if chatReq.Messages[0].Role != "system" {
		t.Errorf("expected first message role system, got %s", chatReq.Messages[0].Role)
	}
	if chatReq.Messages[0].Content.StringContent != "You are a helpful assistant." {
		t.Errorf("unexpected system content: %q", chatReq.Messages[0].Content.StringContent)
	}
	if chatReq.Messages[1].Role != "user" {
		t.Errorf("expected second message role user, got %s", chatReq.Messages[1].Role)
	}
}

func TestConvertResponseRequestToChatRequest_ArrayInput_Messages(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "message", Role: "user", Content: models.ResponseContent{StringContent: "What is 2+2?"}},
				{Type: "message", Role: "assistant", Content: models.ResponseContent{StringContent: "It is 4."}},
				{Type: "message", Role: "user", Content: models.ResponseContent{StringContent: "What about 3+3?"}},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if len(chatReq.Messages) != 3 {
		t.Fatalf("expected 3 messages, got %d", len(chatReq.Messages))
	}
	if chatReq.Messages[0].Role != "user" {
		t.Errorf("expected message 0 role user, got %s", chatReq.Messages[0].Role)
	}
	if chatReq.Messages[1].Role != "assistant" {
		t.Errorf("expected message 1 role assistant, got %s", chatReq.Messages[1].Role)
	}
	if chatReq.Messages[2].Role != "user" {
		t.Errorf("expected message 2 role user, got %s", chatReq.Messages[2].Role)
	}
}

func TestConvertResponseRequestToChatRequest_DeveloperRoleMapped(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "message", Role: "developer", Content: models.ResponseContent{StringContent: "Dev instruction"}},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	// Go maps developer to system
	if chatReq.Messages[0].Role != "system" {
		t.Errorf("expected developer->system, got %s", chatReq.Messages[0].Role)
	}
}

func TestConvertResponseRequestToChatRequest_FunctionCallItems(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "function_call", CallID: "call_abc", Name: "search", Arguments: `{"query":"test"}`, Status: "completed"},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if len(chatReq.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(chatReq.Messages))
	}
	msg := chatReq.Messages[0]
	if msg.Role != "assistant" {
		t.Errorf("expected role assistant, got %s", msg.Role)
	}
	if len(msg.ToolCalls) != 1 {
		t.Fatalf("expected 1 tool call, got %d", len(msg.ToolCalls))
	}
	if msg.ToolCalls[0].ID != "call_abc" {
		t.Errorf("expected tool call id call_abc, got %s", msg.ToolCalls[0].ID)
	}
	if msg.ToolCalls[0].Function.Name != "search" {
		t.Errorf("expected tool name search, got %s", msg.ToolCalls[0].Function.Name)
	}
	if msg.ToolCalls[0].Function.Arguments != `{"query":"test"}` {
		t.Errorf("unexpected arguments: %s", msg.ToolCalls[0].Function.Arguments)
	}
}

func TestConvertResponseRequestToChatRequest_FunctionCallOutput(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "function_call_output", CallID: "call_abc", Output: "result data"},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if len(chatReq.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(chatReq.Messages))
	}
	msg := chatReq.Messages[0]
	if msg.Role != "tool" {
		t.Errorf("expected role tool, got %s", msg.Role)
	}
	if msg.ToolCallID != "call_abc" {
		t.Errorf("expected tool_call_id call_abc, got %s", msg.ToolCallID)
	}
	if msg.Content.StringContent != "result data" {
		t.Errorf("expected content 'result data', got %q", msg.Content.StringContent)
	}
}

func TestConvertResponseRequestToChatRequest_ToolCallRoundTrip(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "message", Role: "user", Content: models.ResponseContent{StringContent: "Search for Go"}},
				{Type: "function_call", CallID: "call_1", Name: "search", Arguments: `{"q":"Go"}`},
				{Type: "function_call_output", CallID: "call_1", Output: "Go is a programming language"},
				{Type: "message", Role: "user", Content: models.ResponseContent{StringContent: "Summarize"}},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	// Should have: user, assistant(tool_calls), tool, user = 4 messages
	if len(chatReq.Messages) != 4 {
		t.Fatalf("expected 4 messages, got %d: %+v", len(chatReq.Messages), chatReq.Messages)
	}
	if chatReq.Messages[0].Role != "user" {
		t.Errorf("msg[0] expected user, got %s", chatReq.Messages[0].Role)
	}
	if chatReq.Messages[1].Role != "assistant" || len(chatReq.Messages[1].ToolCalls) != 1 {
		t.Error("msg[1] expected assistant with tool_calls")
	}
	if chatReq.Messages[2].Role != "tool" {
		t.Errorf("msg[2] expected tool, got %s", chatReq.Messages[2].Role)
	}
	if chatReq.Messages[3].Role != "user" {
		t.Errorf("msg[3] expected user, got %s", chatReq.Messages[3].Role)
	}
}

func TestConvertResponseRequestToChatRequest_Tools(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{StringInput: "search something"},
		Tools: []models.ResponseTool{
			{Type: "function", Function: &models.FunctionDef{
				Name:        "search",
				Description: "Search the web",
				Parameters:  map[string]interface{}{"type": "object"},
			}},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if len(chatReq.Tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(chatReq.Tools))
	}
	if chatReq.Tools[0].Function.Name != "search" {
		t.Errorf("expected tool name search, got %s", chatReq.Tools[0].Function.Name)
	}
	if chatReq.Tools[0].Function.Description != "Search the web" {
		t.Errorf("expected description 'Search the web', got %s", chatReq.Tools[0].Function.Description)
	}
}

func TestConvertResponseRequestToChatRequest_MaxTokens(t *testing.T) {
	tokens := 4096
	req := &models.ResponseRequest{
		Model:             "deepseek-chat",
		Input:             models.ResponseInput{StringInput: "hi"},
		MaxOutputTokens:   tokens,
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if chatReq.MaxTokens != tokens {
		t.Errorf("expected max_tokens %d, got %d", tokens, chatReq.MaxTokens)
	}
}

func TestConvertResponseRequestToChatRequest_MultimodalContent(t *testing.T) {
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{
					Type: "message",
					Role: "user",
					Content: models.ResponseContent{
						Parts: []models.ContentPart{
							{Type: "input_text", Text: "What is this?"},
							{Type: "input_image", ImageURL: "https://example.com/img.png"},
						},
					},
				},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	if len(chatReq.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(chatReq.Messages))
	}
	parts := chatReq.Messages[0].Content.Parts
	if len(parts) != 2 {
		t.Fatalf("expected 2 content parts, got %d", len(parts))
	}
	if parts[0].Type != "text" {
		t.Errorf("expected part 0 type text, got %s", parts[0].Type)
	}
	if parts[1].Type != "image_url" {
		t.Errorf("expected part 1 type image_url, got %s", parts[1].Type)
	}
}

func TestConvertResponseRequestToChatRequest_NoEmptyAssistantMessages(t *testing.T) {
	// Regression: function_call_output should NOT create a trailing empty assistant message
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "function_call", CallID: "c1", Name: "x", Arguments: "{}"},
				{Type: "function_call_output", CallID: "c1", Output: "ok"},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	// Should be: assistant(tool_calls), tool = 2 messages
	if len(chatReq.Messages) != 2 {
		t.Fatalf("expected 2 messages, got %d: %+v", len(chatReq.Messages), chatReq.Messages)
	}
	// No trailing empty assistant message
	if chatReq.Messages[1].Role == "assistant" && chatReq.Messages[1].Content.StringContent == "" && len(chatReq.Messages[1].ToolCalls) == 0 {
		t.Error("found trailing empty assistant message")
	}
}

// ============================================================
// Tests: ChatResponse -> Response (convertChatResponseToResponse)
// ============================================================

func TestConvertChatResponseToResponse_SimpleText(t *testing.T) {
	chatResp := &ChatResponse{
		ID:     "chatcmpl-123",
		Object: "chat.completion",
		Model:  "deepseek-chat",
		Choices: []Choice{
			{
				Index: 0,
				Message: &ChatMessage{
					Role:    "assistant",
					Content: ChatMessageContent{StringContent: "Hello, I am helpful."},
				},
				FinishReason: "stop",
			},
		},
		Usage: &Usage{PromptTokens: 10, CompletionTokens: 5, TotalTokens: 15},
	}

	resp := convertChatResponseToResponse(chatResp, "deepseek-chat", "", nil)

	if resp.Object != "response" {
		t.Errorf("expected object 'response', got %s", resp.Object)
	}
	if resp.Model != "deepseek-chat" {
		t.Errorf("expected model deepseek-chat, got %s", resp.Model)
	}
	if resp.Status != "completed" {
		t.Errorf("expected status completed, got %s", resp.Status)
	}
	if len(resp.Output) != 1 {
		t.Fatalf("expected 1 output item, got %d", len(resp.Output))
	}
	if resp.Output[0].Type != "message" {
		t.Errorf("expected output type message, got %s", resp.Output[0].Type)
	}
	if len(resp.Output[0].Content) != 1 {
		t.Fatalf("expected 1 content part, got %d", len(resp.Output[0].Content))
	}
	if resp.Output[0].Content[0].Text != "Hello, I am helpful." {
		t.Errorf("unexpected text: %s", resp.Output[0].Content[0].Text)
	}
	if resp.Usage == nil {
		t.Fatal("expected non-nil usage")
	}
	if resp.Usage.InputTokens != 10 {
		t.Errorf("expected input_tokens 10, got %d", resp.Usage.InputTokens)
	}
	if resp.Usage.OutputTokens != 5 {
		t.Errorf("expected output_tokens 5, got %d", resp.Usage.OutputTokens)
	}
}

func TestConvertChatResponseToResponse_ThinkTagsStripped(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Content: ChatMessageContent{StringContent: "<think> Let me think...</think>The answer is 42."},
				},
				FinishReason: "stop",
			},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if len(resp.Output) != 1 {
		t.Fatalf("expected 1 output, got %d", len(resp.Output))
	}
	text := resp.Output[0].Content[0].Text
	if strings.Contains(text, "<think>") {
		t.Errorf("think tags should be stripped, got: %s", text)
	}
	if text != "The answer is 42." {
		t.Errorf("expected 'The answer is 42.', got %q", text)
	}
}

func TestConvertChatResponseToResponse_ToolCalls(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Role:    "assistant",
					Content: ChatMessageContent{StringContent: ""},
					ToolCalls: []ToolCall{
						{ID: "call_abc", Type: "function", Function: FunctionCall{Name: "search", Arguments: `{"q":"test"}`}},
					},
				},
				FinishReason: "tool_calls",
			},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	// Tool calls become function_call output items (no text since content is empty)
	if len(resp.Output) != 1 {
		t.Fatalf("expected 1 output, got %d", len(resp.Output))
	}
	if resp.Output[0].Type != "function_call" {
		t.Errorf("expected type function_call, got %s", resp.Output[0].Type)
	}
	if resp.Output[0].CallID != "call_abc" {
		t.Errorf("expected call_id call_abc, got %s", resp.Output[0].CallID)
	}
	if resp.Output[0].Name != "search" {
		t.Errorf("expected name search, got %s", resp.Output[0].Name)
	}
}

func TestConvertChatResponseToResponse_ToolCallsPlusText(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Role:    "assistant",
					Content: ChatMessageContent{StringContent: "Here is the result."},
					ToolCalls: []ToolCall{
						{ID: "call_abc", Type: "function", Function: FunctionCall{Name: "search", Arguments: `{"q":"test"}`}},
					},
				},
				FinishReason: "stop",
			},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if len(resp.Output) != 2 {
		t.Fatalf("expected 2 outputs (tool_call + message), got %d", len(resp.Output))
	}
	// Tool calls should come first
	if resp.Output[0].Type != "function_call" {
		t.Errorf("expected first output function_call, got %s", resp.Output[0].Type)
	}
	if resp.Output[1].Type != "message" {
		t.Errorf("expected second output message, got %s", resp.Output[1].Type)
	}
}

func TestConvertChatResponseToResponse_FinishReasonLength(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Content: ChatMessageContent{StringContent: "This is a very long"},
				},
				FinishReason: "length",
			},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if resp.Status != "incomplete" {
		t.Errorf("expected status incomplete for length, got %s", resp.Status)
	}
	if resp.IncompleteDetails == nil {
		t.Fatal("expected incomplete_details to be non-nil")
	}
	if resp.IncompleteDetails.Reason != "max_output_tokens" {
		t.Errorf("expected reason max_output_tokens, got %s", resp.IncompleteDetails.Reason)
	}
}

func TestConvertChatResponseToResponse_FinishReasonContentFilter(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Content: ChatMessageContent{StringContent: "filtered"},
				},
				FinishReason: "content_filter",
			},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if resp.Status != "incomplete" {
		t.Errorf("expected status incomplete for content_filter, got %s", resp.Status)
	}
	if resp.IncompleteDetails == nil {
		t.Fatal("expected incomplete_details")
	}
	if resp.IncompleteDetails.Reason != "content_filter" {
		t.Errorf("expected reason content_filter, got %s", resp.IncompleteDetails.Reason)
	}
}

func TestConvertChatResponseToResponse_EmptyChoices(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if resp.Object != "response" {
		t.Errorf("expected object response, got %s", resp.Object)
	}
	if len(resp.Output) != 0 {
		t.Errorf("expected empty output, got %d items", len(resp.Output))
	}
}

func TestConvertChatResponseToResponse_NilMessage(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{Message: nil, FinishReason: "stop"},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if len(resp.Output) != 0 {
		t.Errorf("expected empty output for nil message, got %d", len(resp.Output))
	}
}

func TestConvertChatResponseToResponse_PreviousResponseID(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{Message: &ChatMessage{Content: ChatMessageContent{StringContent: "hi"}}, FinishReason: "stop"},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "resp_prev123", nil)

	if resp.PreviousResponseID != "resp_prev123" {
		t.Errorf("expected previous_response_id resp_prev123, got %s", resp.PreviousResponseID)
	}
}

func TestConvertChatResponseToResponse_Metadata(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{Message: &ChatMessage{Content: ChatMessageContent{StringContent: "hi"}}, FinishReason: "stop"},
		},
	}

	meta := map[string]interface{}{"conversation_id": "conv_1"}
	resp := convertChatResponseToResponse(chatResp, "model", "", meta)

	if resp.Metadata == nil {
		t.Fatal("expected metadata to be set")
	}
	if resp.Metadata["conversation_id"] != "conv_1" {
		t.Errorf("expected conversation_id conv_1, got %v", resp.Metadata["conversation_id"])
	}
}

func TestConvertChatResponseToResponse_UsageTranslation(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{Message: &ChatMessage{Content: ChatMessageContent{StringContent: "hi"}}, FinishReason: "stop"},
		},
		Usage: &Usage{PromptTokens: 100, CompletionTokens: 50, TotalTokens: 150},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if resp.Usage == nil {
		t.Fatal("expected non-nil usage")
	}
	if resp.Usage.InputTokens != 100 {
		t.Errorf("expected input_tokens 100, got %d", resp.Usage.InputTokens)
	}
	if resp.Usage.OutputTokens != 50 {
		t.Errorf("expected output_tokens 50, got %d", resp.Usage.OutputTokens)
	}
	if resp.Usage.TotalTokens != 150 {
		t.Errorf("expected total_tokens 150, got %d", resp.Usage.TotalTokens)
	}
}

func TestConvertChatResponseToResponse_ResponseIDFormat(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{Message: &ChatMessage{Content: ChatMessageContent{StringContent: "hi"}}, FinishReason: "stop"},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	if !strings.HasPrefix(resp.ID, "resp_") {
		t.Errorf("expected ID to start with resp_, got %s", resp.ID)
	}
}

func TestConvertChatResponseToResponse_OutputTextConvenience(t *testing.T) {
	chatResp := &ChatResponse{
		Choices: []Choice{
			{Message: &ChatMessage{Content: ChatMessageContent{StringContent: "Hello world"}}, FinishReason: "stop"},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "model", "", nil)

	// Verify we can extract text via output
	if len(resp.Output) == 0 {
		t.Fatal("expected non-empty output")
	}
	// The output_text should be the message content
	found := false
	for _, item := range resp.Output {
		if item.Type == "message" {
			for _, c := range item.Content {
				if c.Type == "output_text" && c.Text == "Hello world" {
					found = true
				}
			}
		}
	}
	if !found {
		t.Errorf("expected to find output_text 'Hello world' in output items")
	}
}

// ============================================================
// Tests: Streaming SSE conversion (readChatCompletionsStream)
// ============================================================

func TestConvertChatChunkToResponseSSE_TextStream(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls: make(map[int]*streamingToolCall),
		},
	}

	// First chunk: text delta
	chunk := &StreamChunk{
		Choices: []struct {
			Index int `json:"index"`
			Delta struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"delta"`
			FinishReason *string `json:"finish_reason"`
		}{
			{
				Delta: struct {
					Role             string     `json:"role,omitempty"`
					Content          string     `json:"content,omitempty"`
					Reasoning        string     `json:"reasoning,omitempty"`
					ReasoningContent string     `json:"reasoning_content,omitempty"`
					ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
				}{
					Content: "Hello",
				},
			},
		},
	}

	events := s.convertChatChunkToResponseSSE(chunk)

	// Should include response.created, response.in_progress, output_item.added, content_part.added, output_text.delta
	if !strings.Contains(events, "response.created") {
		t.Error("expected response.created event")
	}
	if !strings.Contains(events, "response.in_progress") {
		t.Error("expected response.in_progress event")
	}
	if !strings.Contains(events, "response.output_item.added") {
		t.Error("expected response.output_item.added event")
	}
	if !strings.Contains(events, "response.output_text.delta") {
		t.Error("expected response.output_text.delta event")
	}
	if !strings.Contains(events, "Hello") {
		t.Error("expected delta text 'Hello' in events")
	}
}

func TestConvertChatChunkToResponseSSE_ReasoningCapturedNotEmitted(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls:  make(map[int]*streamingToolCall),
			createdSent: true,
		},
	}

	chunk := &StreamChunk{
		Choices: []struct {
			Index int `json:"index"`
			Delta struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"delta"`
			FinishReason *string `json:"finish_reason"`
		}{
			{
				Delta: struct {
					Role             string     `json:"role,omitempty"`
					Content          string     `json:"content,omitempty"`
					Reasoning        string     `json:"reasoning,omitempty"`
					ReasoningContent string     `json:"reasoning_content,omitempty"`
					ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
				}{
					Reasoning: "Let me think about this...",
				},
			},
		},
	}

	events := s.convertChatChunkToResponseSSE(chunk)

	// Reasoning should be captured in state but NOT emitted as SSE events
	if s.chatStreamState.reasoningBuf.String() != "Let me think about this..." {
		t.Errorf("expected reasoning captured, got %q", s.chatStreamState.reasoningBuf.String())
	}
	if strings.Contains(events, "Let me think") {
		t.Error("reasoning should NOT be emitted in SSE events")
	}
}

func TestConvertChatChunkToResponseSSE_ToolCallStream(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls:   make(map[int]*streamingToolCall),
			createdSent: true,
		},
	}

	// Tool call delta
	reason := "tool_calls"
	chunk := &StreamChunk{
		Choices: []struct {
			Index int `json:"index"`
			Delta struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"delta"`
			FinishReason *string `json:"finish_reason"`
		}{
			{
				Delta: struct {
					Role             string     `json:"role,omitempty"`
					Content          string     `json:"content,omitempty"`
					Reasoning        string     `json:"reasoning,omitempty"`
					ReasoningContent string     `json:"reasoning_content,omitempty"`
					ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
				}{
					ToolCalls: []ToolCall{
						{Index: 0, ID: "call_xyz", Type: "function", Function: FunctionCall{Name: "search", Arguments: `{"q":`}},
					},
				},
				FinishReason: &reason,
			},
		},
	}

	events := s.convertChatChunkToResponseSSE(chunk)

	if !strings.Contains(events, "response.output_item.added") {
		t.Error("expected response.output_item.added for tool call")
	}
	if !strings.Contains(events, "response.function_call_arguments.delta") {
		t.Error("expected function_call_arguments.delta event")
	}
	if !strings.Contains(events, "search") {
		t.Error("expected tool name 'search' in events")
	}
}

func TestConvertChatChunkToResponseSSE_MultiChunkTextStream(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls: make(map[int]*streamingToolCall),
		},
	}

	// Chunk 1: first text
	chunk1 := &StreamChunk{
		Choices: []struct {
			Index int `json:"index"`
			Delta struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"delta"`
			FinishReason *string `json:"finish_reason"`
		}{
			{Delta: struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			}{Content: "Hel"}},
		},
	}
	s.convertChatChunkToResponseSSE(chunk1)

	// Chunk 2: more text
	chunk2 := &StreamChunk{
		Choices: []struct {
			Index int `json:"index"`
			Delta struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"delta"`
			FinishReason *string `json:"finish_reason"`
		}{
			{Delta: struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			}{Content: "lo"}},
		},
	}
	s.convertChatChunkToResponseSSE(chunk2)

	if !s.chatStreamState.createdSent {
		t.Error("expected createdSent to be true after first chunk")
	}
	if !s.chatStreamState.textStarted {
		t.Error("expected textStarted to be true")
	}
	if s.chatStreamState.fullText.String() != "Hello" {
		t.Errorf("expected accumulated text 'Hello', got %q", s.chatStreamState.fullText.String())
	}
}

func TestConvertChatChunkToResponseSSE_FinishReasonEmitsCompletion(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls:   make(map[int]*streamingToolCall),
			createdSent: true,
			textStarted: true,
			textOutputID: "msg_test",
			fullText:    strings.Builder{},
		},
	}
	s.chatStreamState.fullText.WriteString("Hello")

	reason := "stop"
	chunk := &StreamChunk{
		Choices: []struct {
			Index int `json:"index"`
			Delta struct {
				Role             string     `json:"role,omitempty"`
				Content          string     `json:"content,omitempty"`
				Reasoning        string     `json:"reasoning,omitempty"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"delta"`
			FinishReason *string `json:"finish_reason"`
		}{
			{
				Delta: struct {
					Role             string     `json:"role,omitempty"`
					Content          string     `json:"content,omitempty"`
					Reasoning        string     `json:"reasoning,omitempty"`
					ReasoningContent string     `json:"reasoning_content,omitempty"`
					ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
				}{},
				FinishReason: &reason,
			},
		},
	}

	events := s.convertChatChunkToResponseSSE(chunk)

	// finish_reason chunk should set state but NOT emit done events
	// Done events are emitted by buildChatCompletionsCompletedSSE on [DONE]/EOF
	if !s.chatStreamState.completed {
		t.Error("expected completed to be true after finish_reason")
	}
	if events != "" {
		t.Errorf("expected no events from finish_reason chunk, got: %s", events)
	}

	// buildChatCompletionsCompletedSSE should emit done events + response.completed
	completed := s.buildChatCompletionsCompletedSSE()
	if !strings.Contains(completed, "response.completed") {
		t.Error("expected response.completed in buildChatCompletionsCompletedSSE output")
	}
	if !strings.Contains(completed, "response.output_text.done") {
		t.Error("expected response.output_text.done in completed output")
	}
	if !strings.Contains(completed, "response.output_item.done") {
		t.Error("expected response.output_item.done in completed output")
	}
	if !strings.Contains(completed, "Hello") {
		t.Error("expected text content in completed output")
	}
}

func TestBuildChatCompletionsCompletedSSE_TextOnly(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls:   make(map[int]*streamingToolCall),
			createdSent: true,
			textStarted: true,
			textOutputID: "msg_test",
			completed:   true,
		},
	}
	s.chatStreamState.fullText.WriteString("Final answer.")

	sse := s.buildChatCompletionsCompletedSSE()

	if !strings.Contains(sse, "response.completed") {
		t.Error("expected response.completed in SSE")
	}
	if !strings.Contains(sse, "Final answer.") {
		t.Error("expected final text in completed event")
	}
	if !strings.Contains(sse, `"status":"completed"`) {
		t.Error("expected status completed")
	}
}

func TestBuildChatCompletionsCompletedSSE_WithToolCalls(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls: map[int]*streamingToolCall{
				0: {
					callID:   "call_abc",
					outputID: "fc_123",
					name:     "search",
				},
			},
			createdSent: true,
			completed:   true,
		},
	}
	s.chatStreamState.toolCalls[0].arguments.WriteString(`{"q":"test"}`)

	sse := s.buildChatCompletionsCompletedSSE()

	if !strings.Contains(sse, `"type":"function_call"`) {
		t.Error("expected function_call type in completed event")
	}
	if !strings.Contains(sse, `"name":"search"`) {
		t.Error("expected tool name search in completed event")
	}
	if !strings.Contains(sse, "call_abc") {
		t.Error("expected call_id call_abc in completed event")
	}
}

func TestBuildChatCompletionsCompletedSSE_IncompleteForLength(t *testing.T) {
	state := &responseStreamState{}
	s := &ResponseStreamingResponse{
		responseID:  "resp_test123",
		model:       &models.Model{Name: "deepseek-chat"},
		streamState: state,
		chatStreamState: &chatToResponseStreamState{
			toolCalls:    make(map[int]*streamingToolCall),
			createdSent:  true,
			textStarted:  true,
			textOutputID: "msg_test",
			completed:    true,
			finishReason: "length",
		},
	}

	sse := s.buildChatCompletionsCompletedSSE()

	if !strings.Contains(sse, `"status":"incomplete"`) {
		t.Error("expected status incomplete for length finish_reason")
	}
}

func TestStreamChunkUnmarshal(t *testing.T) {
	// Verify StreamChunk can properly unmarshal Chat Completions SSE data
	data := `{
		"id": "chatcmpl-123",
		"object": "chat.completion.chunk",
		"created": 1700000000,
		"model": "deepseek-chat",
		"choices": [{
			"index": 0,
			"delta": {"role": "assistant", "content": "Hello"},
			"finish_reason": null
		}]
	}`

	var chunk StreamChunk
	if err := json.Unmarshal([]byte(data), &chunk); err != nil {
		t.Fatalf("failed to unmarshal stream chunk: %v", err)
	}
	if len(chunk.Choices) != 1 {
		t.Fatalf("expected 1 choice, got %d", len(chunk.Choices))
	}
	if chunk.Choices[0].Delta.Content != "Hello" {
		t.Errorf("expected content 'Hello', got %q", chunk.Choices[0].Delta.Content)
	}
}

func TestStreamChunkWithToolCallsUnmarshal(t *testing.T) {
	data := `{
		"id": "chatcmpl-123",
		"object": "chat.completion.chunk",
		"created": 1700000000,
		"model": "deepseek-chat",
		"choices": [{
			"index": 0,
			"delta": {
				"tool_calls": [{
					"index": 0,
					"id": "call_abc",
					"type": "function",
					"function": {"name": "search", "arguments": "{\"q\":"}
				}]
			}
		}]
	}`

	var chunk StreamChunk
	if err := json.Unmarshal([]byte(data), &chunk); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}
	if len(chunk.Choices) != 1 {
		t.Fatalf("expected 1 choice, got %d", len(chunk.Choices))
	}
	if len(chunk.Choices[0].Delta.ToolCalls) != 1 {
		t.Fatalf("expected 1 tool call, got %d", len(chunk.Choices[0].Delta.ToolCalls))
	}
	if chunk.Choices[0].Delta.ToolCalls[0].Function.Name != "search" {
		t.Errorf("expected tool name search, got %s", chunk.Choices[0].Delta.ToolCalls[0].Function.Name)
	}
}

func TestTranslateUsage(t *testing.T) {
	usage := &Usage{PromptTokens: 100, CompletionTokens: 50, TotalTokens: 150}
	respUsage := translateUsage(usage)

	if respUsage.InputTokens != 100 {
		t.Errorf("expected input_tokens 100, got %d", respUsage.InputTokens)
	}
	if respUsage.OutputTokens != 50 {
		t.Errorf("expected output_tokens 50, got %d", respUsage.OutputTokens)
	}
	if respUsage.TotalTokens != 150 {
		t.Errorf("expected total_tokens 150, got %d", respUsage.TotalTokens)
	}
}

func TestTranslateUsageNil(t *testing.T) {
	respUsage := translateUsage(nil)
	if respUsage != nil {
		t.Error("expected nil usage for nil input")
	}
}

// ============================================================
// Tests: End-to-end conversion: ResponseRequest -> ChatRequest -> ChatResponse -> Response
// ============================================================

func TestEndToEnd_SimpleTextConversion(t *testing.T) {
	// Step 1: ResponseRequest -> ChatRequest
	req := &models.ResponseRequest{
		Model:   "deepseek-chat",
		Input:   models.ResponseInput{StringInput: "What is Go?"},
		Stream:  false,
	}

	chatReq := convertResponseRequestToChatRequest(req)

	// Verify request conversion
	if len(chatReq.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(chatReq.Messages))
	}

	// Step 2: Simulate upstream ChatResponse
	chatResp := &ChatResponse{
		ID:     "chatcmpl-simulated",
		Object: "chat.completion",
		Model:  "deepseek-chat",
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Role:    "assistant",
					Content: ChatMessageContent{StringContent: "Go is a programming language created at Google."},
				},
				FinishReason: "stop",
			},
		},
		Usage: &Usage{PromptTokens: 5, CompletionTokens: 12, TotalTokens: 17},
	}

	// Step 3: ChatResponse -> Response
	resp := convertChatResponseToResponse(chatResp, "deepseek-chat", "", nil)

	// Verify response conversion
	if resp.Object != "response" {
		t.Errorf("expected object 'response', got %s", resp.Object)
	}
	if len(resp.Output) != 1 {
		t.Fatalf("expected 1 output, got %d", len(resp.Output))
	}
	if resp.Output[0].Type != "message" {
		t.Errorf("expected message output, got %s", resp.Output[0].Type)
	}
	text := resp.Output[0].Content[0].Text
	if text != "Go is a programming language created at Google." {
		t.Errorf("unexpected text: %s", text)
	}
}

func TestEndToEnd_ToolCallRoundTrip(t *testing.T) {
	// Step 1: ResponseRequest with function_call items
	req := &models.ResponseRequest{
		Model: "deepseek-chat",
		Input: models.ResponseInput{
			Items: []models.ResponseInputItem{
				{Type: "message", Role: "user", Content: models.ResponseContent{StringContent: "Search for Golang"}},
				{Type: "function_call", CallID: "call_1", Name: "search", Arguments: `{"q":"Golang"}`},
				{Type: "function_call_output", CallID: "call_1", Output: "Golang is Go."},
			},
		},
	}

	chatReq := convertResponseRequestToChatRequest(req)

	// Should produce: user, assistant(tool_calls), tool
	if len(chatReq.Messages) != 3 {
		t.Fatalf("expected 3 messages (user, assistant, tool), got %d", len(chatReq.Messages))
	}
	if chatReq.Messages[0].Role != "user" {
		t.Errorf("expected first msg user, got %s", chatReq.Messages[0].Role)
	}
	assistantMsg := chatReq.Messages[1]
	if assistantMsg.Role != "assistant" {
		t.Errorf("expected second msg assistant, got %s", assistantMsg.Role)
	}
	if len(assistantMsg.ToolCalls) != 1 {
		t.Fatalf("expected 1 tool call, got %d", len(assistantMsg.ToolCalls))
	}

	toolMsg := chatReq.Messages[2]
	if toolMsg.Role != "tool" {
		t.Errorf("expected second msg tool, got %s", toolMsg.Role)
	}
	if toolMsg.ToolCallID != "call_1" {
		t.Errorf("expected tool_call_id call_1, got %s", toolMsg.ToolCallID)
	}

	// Simulate upstream response with another tool call
	chatResp := &ChatResponse{
		Choices: []Choice{
			{
				Message: &ChatMessage{
					Role:    "assistant",
					Content: ChatMessageContent{StringContent: ""},
					ToolCalls: []ToolCall{
						{ID: "call_2", Type: "function", Function: FunctionCall{Name: "summarize", Arguments: `{}`}},
					},
				},
				FinishReason: "tool_calls",
			},
		},
	}

	resp := convertChatResponseToResponse(chatResp, "deepseek-chat", "", nil)

	if len(resp.Output) != 1 {
		t.Fatalf("expected 1 function_call output, got %d", len(resp.Output))
	}
	if resp.Output[0].Type != "function_call" {
		t.Errorf("expected function_call, got %s", resp.Output[0].Type)
	}
	if resp.Output[0].Name != "summarize" {
		t.Errorf("expected name summarize, got %s", resp.Output[0].Name)
	}
}
