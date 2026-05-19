package service

import "strings"

// headerMapping maps source header names (lowercase) to target header names per protocol.
// Supported protocols: "openai", "anthropic", "gemini".
var headerMapping = map[string]map[string]string{
	// Generic / OpenAI style
	"session-id": {
		"openai": "x-session-id", "anthropic": "anthropic-session-id", "gemini": "x-session-id",
	},
	"x-session-id": {
		"openai": "x-session-id", "anthropic": "anthropic-session-id", "gemini": "x-session-id",
	},
	"thread-id": {
		"openai": "x-thread-id", "anthropic": "anthropic-thread-id", "gemini": "x-thread-id",
	},
	"x-thread-id": {
		"openai": "x-thread-id", "anthropic": "anthropic-thread-id", "gemini": "x-thread-id",
	},
	"x-client-request-id": {
		"openai": "x-client-request-id", "anthropic": "anthropic-client-request-id", "gemini": "x-client-request-id",
	},
	// Anthropic style (reverse mapping)
	"anthropic-session-id": {
		"openai": "x-session-id", "anthropic": "anthropic-session-id", "gemini": "x-session-id",
	},
	"anthropic-thread-id": {
		"openai": "x-thread-id", "anthropic": "anthropic-thread-id", "gemini": "x-thread-id",
	},
	"anthropic-client-request-id": {
		"openai": "x-client-request-id", "anthropic": "anthropic-client-request-id", "gemini": "x-client-request-id",
	},
	// Codex series (passthrough with normalized format)
	"x-codex-window-id": {
		"openai": "x-codex-window-id", "anthropic": "x-codex-window-id", "gemini": "x-codex-window-id",
	},
	"x-codex-turn-metadata": {
		"openai": "x-codex-turn-metadata", "anthropic": "x-codex-turn-metadata", "gemini": "x-codex-turn-metadata",
	},
}

// MapHeaders transforms special request headers according to the target protocol.
// It modifies forwardHeaders in place, removing original keys and inserting mapped ones.
func MapHeaders(forwardHeaders map[string]string, protocol string) {
	for key := range forwardHeaders {
		keyLower := strings.ToLower(key)
		if mapping, ok := headerMapping[keyLower]; ok {
			targetKey := mapping[protocol]
			if targetKey == "" {
				targetKey = keyLower
			}
			value := forwardHeaders[key]
			if key != targetKey {
				delete(forwardHeaders, key)
				forwardHeaders[targetKey] = value
			}
		}
	}
}
