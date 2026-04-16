package models

import "encoding/json"

// ================================== Gemini API Types ==================================

// GeminiGenerateContentRequest represents a Gemini generateContent request
type GeminiGenerateContentRequest struct {
	Contents          []GeminiContent          `json:"contents"`
	SystemInstruction *GeminiContent           `json:"systemInstruction,omitempty"`
	Tools             []GeminiTool             `json:"tools,omitempty"`
	ToolConfig        *GeminiToolConfig        `json:"toolConfig,omitempty"`
	GenerationConfig  *GeminiGenerationConfig  `json:"generationConfig,omitempty"`
	SafetySettings    []GeminiSafetySetting    `json:"safetySettings,omitempty"`
}

// GeminiContent represents a Gemini content object
type GeminiContent struct {
	Role  string       `json:"role,omitempty"` // "user" or "model"
	Parts []GeminiPart `json:"parts"`
}

// GeminiPart represents a Gemini part object
type GeminiPart struct {
	Text             string                  `json:"text,omitempty"`
	Thought          bool                    `json:"thought,omitempty"` // For thinking models
	InlineData       *GeminiInlineData       `json:"inlineData,omitempty"`
	FileData         *GeminiFileData         `json:"fileData,omitempty"`
	FunctionCall     *GeminiFunctionCall     `json:"functionCall,omitempty"`
	FunctionResponse *GeminiFunctionResponse `json:"functionResponse,omitempty"`
}

// GeminiInlineData represents a Gemini inlineData object
type GeminiInlineData struct {
	MimeType string `json:"mimeType"`
	Data     string `json:"data"` // base64
}

// GeminiFileData represents a Gemini fileData object
type GeminiFileData struct {
	MimeType string `json:"mimeType"`
	FileUri  string `json:"fileUri"`
}

// GeminiFunctionCall represents a Gemini functionCall object
type GeminiFunctionCall struct {
	Name string                 `json:"name"`
	Args map[string]interface{} `json:"args"`
}

// GeminiFunctionResponse represents a Gemini functionResponse object
type GeminiFunctionResponse struct {
	Name     string                 `json:"name"`
	Response map[string]interface{} `json:"response"`
}

// GeminiTool represents a Gemini tool object
type GeminiTool struct {
	FunctionDeclarations []GeminiFunctionDeclaration `json:"functionDeclarations,omitempty"`
}

// GeminiFunctionDeclaration represents a Gemini functionDeclaration object
type GeminiFunctionDeclaration struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	Parameters  map[string]interface{} `json:"parameters,omitempty"`
}

// GeminiToolConfig represents a Gemini toolConfig object
type GeminiToolConfig struct {
	FunctionCallingConfig *GeminiFunctionCallingConfig `json:"functionCallingConfig,omitempty"`
}

// GeminiFunctionCallingConfig represents a Gemini functionCallingConfig object
type GeminiFunctionCallingConfig struct {
	Mode                 string   `json:"mode,omitempty"` // "AUTO", "ANY", "NONE"
	AllowedFunctionNames []string `json:"allowedFunctionNames,omitempty"`
}

// GeminiGenerationConfig represents a Gemini generationConfig object
type GeminiGenerationConfig struct {
	Temperature      *float64              `json:"temperature,omitempty"`
	TopP             *float64              `json:"topP,omitempty"`
	TopK             *int                  `json:"topK,omitempty"`
	CandidateCount   *int                  `json:"candidateCount,omitempty"`
	MaxOutputTokens  *int                  `json:"maxOutputTokens,omitempty"`
	StopSequences    []string              `json:"stopSequences,omitempty"`
	ResponseMimeType string                `json:"responseMimeType,omitempty"`
	ThinkingConfig   *GeminiThinkingConfig `json:"thinkingConfig,omitempty"`
}

// GeminiThinkingConfig represents a Gemini thinkingConfig object
type GeminiThinkingConfig struct {
	IncludeThoughts bool `json:"includeThoughts,omitempty"`
}

// GeminiSafetySetting represents a Gemini safetySetting object
type GeminiSafetySetting struct {
	Category  string `json:"category"`
	Threshold string `json:"threshold"`
}

// GeminiGenerateContentResponse represents a Gemini generateContent response
type GeminiGenerateContentResponse struct {
	Candidates     []GeminiCandidate    `json:"candidates"`
	UsageMetadata  *GeminiUsageMetadata `json:"usageMetadata,omitempty"`
	PromptFeedback *json.RawMessage     `json:"promptFeedback,omitempty"`
}

// GeminiCandidate represents a Gemini candidate object
type GeminiCandidate struct {
	Content       GeminiContent       `json:"content"`
	FinishReason  string              `json:"finishReason,omitempty"`
	Index         int                 `json:"index"`
	SafetyRatings []GeminiSafetyRating `json:"safetyRatings,omitempty"`
	TokenCount    int                 `json:"tokenCount,omitempty"`
}

// GeminiSafetyRating represents a Gemini safetyRating object
type GeminiSafetyRating struct {
	Category    string `json:"category"`
	Probability string `json:"probability"`
	Blocked     bool   `json:"blocked,omitempty"`
}

// GeminiUsageMetadata represents a Gemini usageMetadata object
type GeminiUsageMetadata struct {
	PromptTokenCount     int `json:"promptTokenCount"`
	CandidatesTokenCount int `json:"candidatesTokenCount"`
	TotalTokenCount      int `json:"totalTokenCount"`
}
