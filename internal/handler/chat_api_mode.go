package handler

const (
	chatAPITypeResponses = "responses"
)

// detectChatAPIType determines which API mode to use based on model name.
// Returns "responses" for Codex models, empty string for regular Chat Completions.
func detectChatAPIType(modelName string) string {
	// Only use Responses API for explicit codex models
	// Most models should use Chat Completions API
	if modelName == "codex-mini" || modelName == "codex-1" {
		return chatAPITypeResponses
	}
	// Default to Chat Completions API
	return ""
}
