package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/service"
)

// AnthropicHandler handles Anthropic Messages API requests
type AnthropicHandler struct {
	gatewayService *service.GatewayService
	converter      *service.ProtocolConverter
}

// NewAnthropicHandler creates a new Anthropic handler
func NewAnthropicHandler(gatewayService *service.GatewayService) *AnthropicHandler {
	return &AnthropicHandler{
		gatewayService: gatewayService,
		converter:      service.NewProtocolConverter(),
	}
}

// CreateMessages handles POST /v1/messages
func (h *AnthropicHandler) CreateMessages(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, models.NewAnthropicError(
			models.AnthropicErrorAuthentication,
			"Missing API key",
		))
		return
	}

	// Parse Anthropic format request
	var req models.AnthropicMessagesRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Invalid request body: "+err.Error(),
		))
		return
	}

	// Validate required fields
	if req.Model == "" {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Missing required field: model",
		))
		return
	}
	if req.MaxTokens <= 0 {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Missing or invalid required field: max_tokens",
		))
		return
	}
	if len(req.Messages) == 0 {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Missing required field: messages",
		))
		return
	}

	// Process through gateway service - keep Anthropic format, let gateway decide whether to convert
	result, err := h.gatewayService.HandleAnthropicMessages(
		c.Request.Context(),
		apiKey,
		&req, // Keep Anthropic format
		req.Stream,
		c.Request.Header,
	)

	if err != nil {
		h.handleErrorResponse(c, err)
		return
	}

	// Handle response based on streaming
	if req.Stream {
		h.handleStreamResponse(c, result, req.Model)
	} else {
		h.handleNonStreamResponse(c, result, req.Model)
	}
}

// handleNonStreamResponse handles non-streaming response
func (h *AnthropicHandler) handleNonStreamResponse(c *gin.Context, result interface{}, modelName string) {
	// Check if response is already Anthropic format (direct forwarding)
	if anthropicResp, ok := result.(*models.AnthropicMessagesResponse); ok {
		c.JSON(http.StatusOK, anthropicResp)
		return
	}

	// Response is OpenAI format, need to convert back to Anthropic
	openAIResp, ok := result.(*service.ChatResponse)
	if !ok {
		c.JSON(http.StatusInternalServerError, models.NewAnthropicError(
			models.AnthropicErrorAPI,
			"Unexpected response type",
		))
		return
	}

	// Convert OpenAI response to Anthropic format
	anthropicResp, err := h.converter.ConvertResponse(openAIResp, service.ProtocolOpenAI, service.ProtocolAnthropic, modelName)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.NewAnthropicError(
			models.AnthropicErrorAPI,
			"Failed to convert response: "+err.Error(),
		))
		return
	}

	c.JSON(http.StatusOK, anthropicResp)
}

// handleStreamResponse handles streaming response
func (h *AnthropicHandler) handleStreamResponse(c *gin.Context, result interface{}, modelName string) {
	streamResp, ok := result.(*service.StreamingResponse)
	if !ok {
		c.JSON(http.StatusInternalServerError, models.NewAnthropicError(
			models.AnthropicErrorAPI,
			"Unexpected stream response type",
		))
		return
	}
	defer streamResp.Close()

	// Set SSE headers
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")

	// Check if upstream stream is already Anthropic format (direct forwarding)
	if streamResp.IsAnthropicStream() {
		// Direct forwarding - just pass through the stream data
		c.Stream(func(w io.Writer) bool {
			buf := make([]byte, 1024)
			n, err := streamResp.Read(buf)
			if err != nil {
				return false
			}
			w.Write(buf[:n])
			return true
		})
		return
	}

	// Upstream stream is OpenAI format, need to convert to Anthropic format
	// Generate message ID for this stream
	messageID := "msg_" + strings.ReplaceAll(uuid.New().String(), "-", "")[:24]
	contentIndex := 0

	// Track state for stream conversion
	state := &service.StreamConversionState{}

	// Create a custom reader that converts OpenAI SSE to Anthropic SSE
	converter := service.NewProtocolConverter()

	c.Stream(func(w io.Writer) bool {
		buf := make([]byte, 1024)
		n, err := streamResp.Read(buf)
		if err != nil {
			return false
		}

		// Parse OpenAI SSE format and convert to Anthropic format
		converted := h.convertStreamData(buf[:n], messageID, &contentIndex, converter, state, modelName)
		if len(converted) > 0 {
			w.Write(converted)
		}
		return true
	})
}

// convertStreamData converts OpenAI streaming data to Anthropic format
func (h *AnthropicHandler) convertStreamData(data []byte, messageID string, contentIndex *int, converter *service.ProtocolConverter, state *service.StreamConversionState, modelName string) []byte {
	// Parse the OpenAI SSE data
	lines := strings.Split(string(data), "\n")
	var result strings.Builder

	for _, line := range lines {
		if strings.HasPrefix(line, "data: ") {
			jsonData := strings.TrimPrefix(line, "data: ")

			// Skip [DONE] marker
			if jsonData == "[DONE]" {
				// Send final events
				if state.ContentBlockStarted {
					result.WriteString(converter.GenerateAnthropicContentBlockStop(*contentIndex))
					result.WriteString("\n")
				}
				result.WriteString(converter.GenerateAnthropicMessageDelta(models.AnthropicStopEndTurn, 0))
				result.WriteString("\n")
				result.WriteString(converter.GenerateAnthropicMessageStop())
				result.WriteString("\n")
				continue
			}

			// Parse the chunk
			var chunk service.StreamChunk
			if err := json.Unmarshal([]byte(jsonData), &chunk); err != nil {
				continue
			}

			// Convert to Anthropic format
			converted := converter.ConvertOpenAIStreamChunkToAnthropic(&chunk, messageID, *contentIndex, state)
			result.WriteString(converted)
		}
	}

	return []byte(result.String())
}

// handleErrorResponse maps errors to Anthropic error format
func (h *AnthropicHandler) handleErrorResponse(c *gin.Context, err error) {
	errMsg := err.Error()

	switch {
	case strings.Contains(errMsg, "not found"):
		c.JSON(http.StatusNotFound, models.NewAnthropicError(
			models.AnthropicErrorNotFound,
			errMsg,
		))
	case strings.Contains(errMsg, "permission") || strings.Contains(errMsg, "denied"):
		c.JSON(http.StatusForbidden, models.NewAnthropicError(
			models.AnthropicErrorPermission,
			errMsg,
		))
	case strings.Contains(errMsg, "balance") || strings.Contains(errMsg, "insufficient"):
		c.JSON(http.StatusForbidden, models.NewAnthropicError(
			models.AnthropicErrorPermission,
			"Insufficient balance",
		))
	default:
		c.JSON(http.StatusInternalServerError, models.NewAnthropicError(
			models.AnthropicErrorAPI,
			errMsg,
		))
	}
}