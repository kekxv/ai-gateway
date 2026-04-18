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

	// Read raw request body first (for direct forwarding)
	rawBody, err := c.GetRawData()
	if err != nil {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Failed to read request body: "+err.Error(),
		))
		return
	}

	// Parse Anthropic format request
	var req models.AnthropicMessagesRequest
	if err := json.Unmarshal(rawBody, &req); err != nil {
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
	// Default max_tokens to 4096 if not provided or invalid, instead of erroring
	// Anthropic API requires max_tokens, but some clients/proxies might omit it
	if req.MaxTokens <= 0 {
		req.MaxTokens = 4096
	}
	if len(req.Messages) == 0 {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Missing required field: messages",
		))
		return
	}

	// Process through gateway service - pass raw body for direct forwarding
	result, err := h.gatewayService.HandleAnthropicMessages(
		c.Request.Context(),
		apiKey,
		&req,
		rawBody, // Pass raw request body for direct forwarding
		req.Stream,
		c.Request.Header,
		c.Request.URL.RawQuery,
			c.Request.URL.Path,
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
			if n > 0 {
				w.Write(buf[:n])
				if f, ok := w.(http.Flusher); ok {
					f.Flush()
				}
			}
			return err == nil
		})
		return
	}

	// Upstream stream is OpenAI format, need to convert to Anthropic format
	// Generate message ID for this stream
	messageID := "msg_" + strings.ReplaceAll(uuid.New().String(), "-", "")[:24]
	contentIndex := 0

	// Track state for stream conversion
	state := &service.StreamConversionState{
		LastToolIndex: -1,
	}
	
	// Buffer for partial SSE lines
	var lineBuffer strings.Builder

	// Create a custom reader that converts OpenAI SSE to Anthropic SSE
	converter := service.NewProtocolConverter()

	c.Stream(func(w io.Writer) bool {
		buf := make([]byte, 1024)
		n, err := streamResp.Read(buf)
		if n > 0 {
			// Write to line buffer
			lineBuffer.Write(buf[:n])
			
			// Extract complete lines
			rawData := lineBuffer.String()
			lastNewline := strings.LastIndex(rawData, "\n")
			
			if lastNewline != -1 {
				completeData := rawData[:lastNewline+1]
				// Keep remaining partial line
				lineBuffer.Reset()
				lineBuffer.WriteString(rawData[lastNewline+1:])
				
				// Parse OpenAI SSE format and convert to Anthropic format
				converted := h.convertStreamData([]byte(completeData), messageID, &contentIndex, converter, state, modelName)
				if len(converted) > 0 {
					w.Write(converted)
					if f, ok := w.(http.Flusher); ok {
						f.Flush()
					}
				}
			}
		}
		
		if err != nil {
			// If we have remaining data in buffer, try to process it even if it doesn't end with newline
			remaining := lineBuffer.String()
			if remaining != "" {
				// Add a newline to ensure it's processed
				converted := h.convertStreamData([]byte(remaining+"\n"), messageID, &contentIndex, converter, state, modelName)
				if len(converted) > 0 {
					w.Write(converted)
					if f, ok := w.(http.Flusher); ok {
						f.Flush()
					}
				}
				lineBuffer.Reset()
			}

			// Final check for completion if not already finished
			if !state.MessageFinished {
				var finalResult strings.Builder
				if state.ContentBlockStarted || state.ThinkingStarted {
					finalResult.WriteString(converter.GenerateAnthropicContentBlockStop(contentIndex))
				}
				finalResult.WriteString(converter.GenerateAnthropicMessageDelta(models.AnthropicStopEndTurn, len(state.AccumulatedContent)/4))
				finalResult.WriteString(converter.GenerateAnthropicMessageStop())
				w.Write([]byte(finalResult.String()))
				if f, ok := w.(http.Flusher); ok {
					f.Flush()
				}
				state.MessageFinished = true
			}
			return false
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

			// Skip [DONE] marker - we handle completion via finish_reason or stream end
			if jsonData == "[DONE]" {
				if !state.MessageFinished {
					if state.ContentBlockStarted || state.ThinkingStarted {
						result.WriteString(converter.GenerateAnthropicContentBlockStop(*contentIndex))
					}
					result.WriteString(converter.GenerateAnthropicMessageDelta(models.AnthropicStopEndTurn, len(state.AccumulatedContent)/4))
					result.WriteString(converter.GenerateAnthropicMessageStop())
					state.MessageFinished = true
				}
				continue
			}

			// Parse the chunk
			var chunk service.StreamChunk
			if err := json.Unmarshal([]byte(jsonData), &chunk); err != nil {
				continue
			}

			// Convert to Anthropic format
			converted := converter.ConvertOpenAIStreamChunkToAnthropic(&chunk, messageID, modelName, contentIndex, state)
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

// CountTokens handles POST /v1/messages/count_tokens
func (h *AnthropicHandler) CountTokens(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, models.NewAnthropicError(
			models.AnthropicErrorAuthentication,
			"Missing API key",
		))
		return
	}

	// Read raw request body
	rawBody, err := c.GetRawData()
	if err != nil {
		c.JSON(http.StatusBadRequest, models.NewAnthropicError(
			models.AnthropicErrorInvalidRequest,
			"Failed to read request body: "+err.Error(),
		))
		return
	}

	// Process through gateway service
	result, err := h.gatewayService.HandleAnthropicCountTokens(
		c.Request.Context(),
		apiKey,
		rawBody,
		c.Request.Header,
	)

	if err != nil {
		h.handleErrorResponse(c, err)
		return
	}

	c.JSON(http.StatusOK, result)
}