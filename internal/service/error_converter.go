package service

import (
	"encoding/json"
)

// ConvertUpstreamErrorToOpenAI converts an upstream error body to OpenAI-compatible format.
// If the body is already in OpenAI format (has "error" key with "message"), returns it as-is.
// Otherwise wraps the raw body as an error message.
func ConvertUpstreamErrorToOpenAI(body []byte) []byte {
	if len(body) == 0 {
		return nil
	}
	// If it's already valid JSON, pass it through (upstream providers using OpenAI protocol)
	var obj map[string]any
	if err := json.Unmarshal(body, &obj); err != nil {
		// Not JSON, wrap as message
		return openAIErrorJSON("unknown", string(body), "")
	}
	// Already has OpenAI-style error structure
	if _, ok := obj["error"]; ok {
		return body
	}
	// Wrap arbitrary JSON as OpenAI error
	return openAIErrorJSON("unknown", string(body), "")
}

// ConvertUpstreamErrorToAnthropic converts an upstream error body to Anthropic-compatible format.
// If the body is already in Anthropic format (has "type":"error"), returns it as-is.
// If it's in OpenAI format, converts to Anthropic format.
// Otherwise wraps with a status-based error type.
func ConvertUpstreamErrorToAnthropic(statusCode int, body []byte) []byte {
	if len(body) == 0 {
		return anthropicErrorJSON(errorTypeFromStatus(statusCode), "upstream error: "+string(rune(statusCode)))
	}
	var obj map[string]any
	if err := json.Unmarshal(body, &obj); err != nil {
		return anthropicErrorJSON(errorTypeFromStatus(statusCode), string(body))
	}
	// Already Anthropic format: {"type":"error","error":{"type":...,"message":...}}
	if t, _ := obj["type"].(string); t == "error" {
		return body
	}
	// OpenAI format: {"error":{"message":...,"type":...}} -> convert to Anthropic
	if errObj, ok := obj["error"].(map[string]any); ok {
		msg, _ := errObj["message"].(string)
		if msg == "" {
			msg = string(body)
		}
		errType, _ := errObj["type"].(string)
		anthropicType := mapOpenAIErrorTypeToAnthropic(errType)
		return anthropicErrorJSON(anthropicType, msg)
	}
	// Arbitrary JSON, wrap it
	return anthropicErrorJSON(errorTypeFromStatus(statusCode), string(body))
}

// openAIErrorJSON creates an OpenAI-compatible error response
func openAIErrorJSON(errType, message, code string) []byte {
	result := map[string]any{
		"error": map[string]any{
			"message": message,
			"type":    errType,
		},
	}
	if code != "" {
		result["error"].(map[string]any)["code"] = code
	}
	b, _ := json.Marshal(result)
	return b
}

// anthropicErrorJSON creates an Anthropic-compatible error response
func anthropicErrorJSON(errType, message string) []byte {
	result := map[string]any{
		"type": "error",
		"error": map[string]any{
			"type":    errType,
			"message": message,
		},
	}
	b, _ := json.Marshal(result)
	return b
}

// errorTypeFromStatus maps HTTP status codes to Anthropic error type strings
func errorTypeFromStatus(code int) string {
	switch code {
	case 400:
		return "invalid_request_error"
	case 401:
		return "authentication_error"
	case 403:
		return "permission_error"
	case 404:
		return "not_found_error"
	case 429:
		return "rate_limit_error"
	case 500, 502, 503, 504:
		return "api_error"
	default:
		if code >= 500 {
			return "api_error"
		}
		return "invalid_request_error"
	}
}

// mapOpenAIErrorTypeToAnthropic maps OpenAI error type strings to Anthropic equivalents
func mapOpenAIErrorTypeToAnthropic(openAIType string) string {
	switch openAIType {
	case "invalid_request_error":
		return "invalid_request_error"
	case "authentication_error":
		return "authentication_error"
	case "insufficient_quota", "permission_error":
		return "permission_error"
	case "not_found_error", "model_not_found":
		return "not_found_error"
	case "rate_limit_error":
		return "rate_limit_error"
	case "api_error", "server_error":
		return "api_error"
	default:
		return "api_error"
	}
}
