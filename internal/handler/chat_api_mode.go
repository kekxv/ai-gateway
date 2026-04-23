package handler

const (
	chatAPITypeResponses = "responses"
)

func detectChatAPIType(modelName string) string {
	return chatAPITypeResponses
}
