package service

import (
	"encoding/json"
	"testing"
)

func TestThinkingConfig_UnmarshalJSON(t *testing.T) {
	tests := []struct {
		name       string
		input      string
		wantType   string
		wantBudget int
		wantErr    bool
	}{
		{"boolean true", `true`, "enabled", 0, false},
		{"boolean false", `false`, "disabled", 0, false},
		{"string enabled", `"enabled"`, "enabled", 0, false},
		{"string disabled", `"disabled"`, "disabled", 0, false},
		{"object enabled with budget", `{"type":"enabled","budget_tokens":1024}`, "enabled", 1024, false},
		{"object enabled no budget", `{"type":"enabled"}`, "enabled", 0, false},
		{"object disabled", `{"type":"disabled"}`, "disabled", 0, false},
		{"null", `null`, "", 0, false},
		{"invalid number", `42`, "", 0, true},
		{"invalid array", `[true]`, "", 0, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var tc ThinkingConfig
			err := json.Unmarshal([]byte(tt.input), &tc)
			if (err != nil) != tt.wantErr {
				t.Errorf("UnmarshalJSON() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if tc.Type != tt.wantType {
					t.Errorf("Type = %q, want %q", tc.Type, tt.wantType)
				}
				if tc.BudgetTokens != tt.wantBudget {
					t.Errorf("BudgetTokens = %d, want %d", tc.BudgetTokens, tt.wantBudget)
				}
			}
		})
	}
}

func TestGenerationConfig_UnmarshalJSON(t *testing.T) {
	tests := []struct {
		name        string
		input       string
		wantLevel   string
		wantPresent bool
		wantErr     bool
	}{
		{
			"object with thinkingLevel",
			`{"thinkingConfig":{"thinkingLevel":"high"}}`,
			"high",
			true,
			false,
		},
		{
			"object empty",
			`{}`,
			"",
			false,
			false,
		},
		{"null", `null`, "", false, false},
		{"invalid bool", `true`, "", false, true},
		{"invalid string", `"high"`, "", false, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var gc GenerationConfig
			err := json.Unmarshal([]byte(tt.input), &gc)
			if (err != nil) != tt.wantErr {
				t.Errorf("UnmarshalJSON() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && tt.wantPresent {
				if gc.ThinkingConfig == nil {
					t.Error("ThinkingConfig should not be nil")
					return
				}
				if gc.ThinkingConfig.ThinkingLevel != tt.wantLevel {
					t.Errorf("ThinkingLevel = %q, want %q", gc.ThinkingConfig.ThinkingLevel, tt.wantLevel)
				}
			}
		})
	}
}

func TestStreamOptions_UnmarshalJSON(t *testing.T) {
	tests := []struct {
		name       string
		input      string
		wantUsage  bool
		wantPresent bool
		wantErr    bool
	}{
		{"object true", `{"include_usage":true}`, true, true, false},
		{"object false", `{"include_usage":false}`, false, true, false},
		{"null", `null`, false, false, false},
		{"invalid bool", `true`, false, false, true},
		{"invalid string", `"yes"`, false, false, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var so StreamOptions
			err := json.Unmarshal([]byte(tt.input), &so)
			if (err != nil) != tt.wantErr {
				t.Errorf("UnmarshalJSON() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && tt.wantPresent && so.IncludeUsage != tt.wantUsage {
				t.Errorf("IncludeUsage = %v, want %v", so.IncludeUsage, tt.wantUsage)
			}
		})
	}
}

func TestChatRequest_Unmarshal_ThinkingBool(t *testing.T) {
	// Simulates the exact payload that triggers the 400 error
	body := []byte(`{"model":"gpt-4","messages":[{"role":"user","content":"hi"}],"thinking":true}`)
	var req ChatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if req.Thinking == nil {
		t.Fatal("Thinking should not be nil")
	}
	if req.Thinking.Type != "enabled" {
		t.Errorf("Thinking.Type = %q, want 'enabled'", req.Thinking.Type)
	}
}

func TestChatRequest_Unmarshal_ThinkingFalse(t *testing.T) {
	body := []byte(`{"model":"gpt-4","messages":[{"role":"user","content":"hi"}],"thinking":false}`)
	var req ChatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if req.Thinking == nil || req.Thinking.Type != "disabled" {
		t.Errorf("Thinking should be disabled, got %v", req.Thinking)
	}
}

func TestChatRequest_Unmarshal_ThinkingObject(t *testing.T) {
	body := []byte(`{"model":"gpt-4","messages":[{"role":"user","content":"hi"}],"thinking":{"type":"enabled","budget_tokens":2048}}`)
	var req ChatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if req.Thinking == nil {
		t.Fatal("Thinking should not be nil")
	}
	if req.Thinking.Type != "enabled" {
		t.Errorf("Type = %q, want 'enabled'", req.Thinking.Type)
	}
	if req.Thinking.BudgetTokens != 2048 {
		t.Errorf("BudgetTokens = %d, want 2048", req.Thinking.BudgetTokens)
	}
}

func TestChatRequest_Unmarshal_GenerationConfig(t *testing.T) {
	body := []byte(`{"model":"gemini","messages":[{"role":"user","content":"hi"}],"generationConfig":{"thinkingConfig":{"thinkingLevel":"high"}}}`)
	var req ChatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if req.GenerationConfig == nil {
		t.Fatal("GenerationConfig should not be nil")
	}
	if req.GenerationConfig.ThinkingConfig == nil {
		t.Fatal("ThinkingConfig should not be nil")
	}
	if req.GenerationConfig.ThinkingConfig.ThinkingLevel != "high" {
		t.Errorf("ThinkingLevel = %q, want 'high'", req.GenerationConfig.ThinkingConfig.ThinkingLevel)
	}
}

func TestChatRequest_Unmarshal_StreamOptions(t *testing.T) {
	body := []byte(`{"model":"gpt-4","messages":[{"role":"user","content":"hi"}],"stream":true,"stream_options":{"include_usage":true}}`)
	var req ChatRequest
	if err := json.Unmarshal(body, &req); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if req.StreamOptions == nil {
		t.Fatal("StreamOptions should not be nil")
	}
	if !req.StreamOptions.IncludeUsage {
		t.Error("IncludeUsage should be true")
	}
}
