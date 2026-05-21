package service

import (
	"encoding/json"
	"testing"
)

// ==================== ConvertUpstreamErrorToOpenAI Tests ====================

func TestConvertUpstreamErrorToOpenAI_NilBody(t *testing.T) {
	result := ConvertUpstreamErrorToOpenAI(nil)
	if result != nil {
		t.Errorf("Expected nil for nil body, got %s", string(result))
	}
}

func TestConvertUpstreamErrorToOpenAI_EmptyBody(t *testing.T) {
	result := ConvertUpstreamErrorToOpenAI([]byte{})
	if result != nil {
		t.Errorf("Expected nil for empty body, got %s", string(result))
	}
}

func TestConvertUpstreamErrorToOpenAI_OpenAIFormat_PassThrough(t *testing.T) {
	body := []byte(`{"error":{"message":"deepseek-reasoner does not support this tool_choice","type":"invalid_request_error","param":null,"code":"invalid_request_error"}}`)
	result := ConvertUpstreamErrorToOpenAI(body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	errObj, ok := obj["error"].(map[string]any)
	if !ok {
		t.Fatal("Result does not have OpenAI error structure")
	}

	if errObj["message"] != "deepseek-reasoner does not support this tool_choice" {
		t.Errorf("Expected original message, got %v", errObj["message"])
	}
	if errObj["type"] != "invalid_request_error" {
		t.Errorf("Expected original type, got %v", errObj["type"])
	}
}

func TestConvertUpstreamErrorToOpenAI_NonJSON_Wrapped(t *testing.T) {
	body := []byte(`internal server error`)
	result := ConvertUpstreamErrorToOpenAI(body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	errObj, ok := obj["error"].(map[string]any)
	if !ok {
		t.Fatal("Result does not have OpenAI error structure")
	}

	if errObj["message"] != "internal server error" {
		t.Errorf("Expected wrapped message, got %v", errObj["message"])
	}
	if errObj["type"] != "unknown" {
		t.Errorf("Expected type 'unknown', got %v", errObj["type"])
	}
}

func TestConvertUpstreamErrorToOpenAI_ArbitraryJSON_Wrapped(t *testing.T) {
	body := []byte(`{"detail":"something went wrong","trace_id":"abc123"}`)
	result := ConvertUpstreamErrorToOpenAI(body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	errObj, ok := obj["error"].(map[string]any)
	if !ok {
		t.Fatal("Result does not have OpenAI error structure")
	}

	if errObj["message"] != `{"detail":"something went wrong","trace_id":"abc123"}` {
		t.Errorf("Expected wrapped JSON string, got %v", errObj["message"])
	}
}

// ==================== ConvertUpstreamErrorToAnthropic Tests ====================

func TestConvertUpstreamErrorToAnthropic_NilBody(t *testing.T) {
	result := ConvertUpstreamErrorToAnthropic(400, nil)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	if obj["type"] != "error" {
		t.Errorf("Expected type 'error', got %v", obj["type"])
	}
}

func TestConvertUpstreamErrorToAnthropic_EmptyBody(t *testing.T) {
	result := ConvertUpstreamErrorToAnthropic(400, []byte{})

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	if obj["type"] != "error" {
		t.Errorf("Expected type 'error', got %v", obj["type"])
	}
}

func TestConvertUpstreamErrorToAnthropic_AnthropicFormat_PassThrough(t *testing.T) {
	body := []byte(`{"type":"error","error":{"type":"invalid_request_error","message":"The model does not support tool calls"}}`)
	result := ConvertUpstreamErrorToAnthropic(400, body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	if obj["type"] != "error" {
		t.Fatal("Result does not have Anthropic error structure")
	}

	errObj, ok := obj["error"].(map[string]any)
	if !ok {
		t.Fatal("Result does not have error detail")
	}

	if errObj["type"] != "invalid_request_error" {
		t.Errorf("Expected original error type, got %v", errObj["type"])
	}
	if errObj["message"] != "The model does not support tool calls" {
		t.Errorf("Expected original message, got %v", errObj["message"])
	}
}

func TestConvertUpstreamErrorToAnthropic_OpenAIFormat_Converted(t *testing.T) {
	body := []byte(`{"error":{"message":"deepseek-reasoner does not support this tool_choice","type":"invalid_request_error","param":null,"code":"invalid_request_error"}}`)
	result := ConvertUpstreamErrorToAnthropic(400, body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	if obj["type"] != "error" {
		t.Fatal("Result is not Anthropic format")
	}

	errObj, ok := obj["error"].(map[string]any)
	if !ok {
		t.Fatal("Result does not have error detail")
	}

	if errObj["type"] != "invalid_request_error" {
		t.Errorf("Expected 'invalid_request_error', got %v", errObj["type"])
	}
	if errObj["message"] != "deepseek-reasoner does not support this tool_choice" {
		t.Errorf("Expected original message, got %v", errObj["message"])
	}
}

func TestConvertUpstreamErrorToAnthropic_OpenAIFormat_PermissionError(t *testing.T) {
	body := []byte(`{"error":{"message":"You exceeded your current quota","type":"insufficient_quota"}}`)
	result := ConvertUpstreamErrorToAnthropic(403, body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	errObj := obj["error"].(map[string]any)
	if errObj["type"] != "permission_error" {
		t.Errorf("Expected 'permission_error', got %v", errObj["type"])
	}
}

func TestConvertUpstreamErrorToAnthropic_ArbitraryJSON_Wrapped(t *testing.T) {
	body := []byte(`{"detail":"something went wrong"}`)
	result := ConvertUpstreamErrorToAnthropic(400, body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	errObj := obj["error"].(map[string]any)
	if errObj["type"] != "invalid_request_error" {
		t.Errorf("Expected 'invalid_request_error' for 400, got %v", errObj["type"])
	}
}

func TestConvertUpstreamErrorToAnthropic_NonJSON_Wrapped(t *testing.T) {
	body := []byte(`upstream error: connection refused`)
	result := ConvertUpstreamErrorToAnthropic(502, body)

	var obj map[string]any
	if err := json.Unmarshal(result, &obj); err != nil {
		t.Fatalf("Result is not valid JSON: %v", err)
	}

	errObj := obj["error"].(map[string]any)
	if errObj["type"] != "api_error" {
		t.Errorf("Expected 'api_error' for 502, got %v", errObj["type"])
	}
}

// ==================== errorTypeFromStatus Tests ====================

func TestErrorTypeFromStatus(t *testing.T) {
	tests := []struct {
		status   int
		expected string
	}{
		{400, "invalid_request_error"},
		{401, "authentication_error"},
		{403, "permission_error"},
		{404, "not_found_error"},
		{429, "rate_limit_error"},
		{500, "api_error"},
		{502, "api_error"},
		{503, "api_error"},
		{504, "api_error"},
		{418, "invalid_request_error"},
		{499, "invalid_request_error"},
	}

	for _, tt := range tests {
		t.Run(string(rune(tt.status)), func(t *testing.T) {
			result := errorTypeFromStatus(tt.status)
			if result != tt.expected {
				t.Errorf("errorTypeFromStatus(%d) = %s, want %s", tt.status, result, tt.expected)
			}
		})
	}
}

// ==================== mapOpenAIErrorTypeToAnthropic Tests ====================

func TestMapOpenAIErrorTypeToAnthropic(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"invalid_request_error", "invalid_request_error"},
		{"authentication_error", "authentication_error"},
		{"insufficient_quota", "permission_error"},
		{"permission_error", "permission_error"},
		{"not_found_error", "not_found_error"},
		{"model_not_found", "not_found_error"},
		{"rate_limit_error", "rate_limit_error"},
		{"api_error", "api_error"},
		{"server_error", "api_error"},
		{"unknown_type", "api_error"},
		{"", "api_error"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := mapOpenAIErrorTypeToAnthropic(tt.input)
			if result != tt.expected {
				t.Errorf("mapOpenAIErrorTypeToAnthropic(%q) = %s, want %s", tt.input, result, tt.expected)
			}
		})
	}
}

// ==================== UpstreamError Type Tests ====================

func TestUpstreamError_Error(t *testing.T) {
	err := &UpstreamError{StatusCode: 400, Body: []byte(`{"error":{"message":"bad request"}}`)}
	expected := "upstream error: 400"
	if err.Error() != expected {
		t.Errorf("Expected %q, got %q", expected, err.Error())
	}
}

func TestUpstreamError_CarriesBody(t *testing.T) {
	body := []byte(`{"error":{"message":"test error","type":"invalid_request_error"}}`)
	err := &UpstreamError{StatusCode: 400, Body: body}

	if string(err.Body) != string(body) {
		t.Errorf("Body not preserved correctly")
	}
	if err.StatusCode != 400 {
		t.Errorf("StatusCode not preserved correctly")
	}
}
