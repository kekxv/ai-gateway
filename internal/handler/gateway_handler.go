package handler

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/service"
)

type GatewayHandler struct {
	gatewayService  *service.GatewayService
	responseService *service.ResponseService
}

func NewGatewayHandler(gatewayService *service.GatewayService, responseService *service.ResponseService) *GatewayHandler {
	return &GatewayHandler{
		gatewayService:  gatewayService,
		responseService: responseService,
	}
}

// ChatCompletions handles chat completions requests
func (h *GatewayHandler) ChatCompletions(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Read raw body for transparent forwarding
	rawBody, err := c.GetRawData()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read request body"})
		return
	}

	var req service.ChatRequest
	if err := json.Unmarshal(rawBody, &req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	stream := req.Stream

	// Pass rawBody to HandleChatCompletions
	result, err := h.gatewayService.HandleChatCompletions(c.Request.Context(), apiKey, &req, rawBody, stream, c.Request.Header, c.Request.URL.Path)
	if err != nil {
		log.Printf("[ChatCompletions] Error: %v, Model: %s, Stream: %v", err, req.Model, stream)
		switch err {
		case service.ErrModelNotFound:
			c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		case service.ErrNoRouteAvailable:
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "No available route for this model"})
		case service.ErrPermissionDenied:
			c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied for this model"})
		case service.ErrInsufficientBalance:
			c.JSON(http.StatusForbidden, gin.H{"error": "Insufficient balance"})
		case service.ErrUpstreamFailed:
			c.JSON(http.StatusBadGateway, gin.H{"error": "Upstream request failed"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	// Handle streaming response
	if stream {
		streamResp, ok := result.(*service.StreamingResponse)
		if !ok {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Invalid streaming response"})
			return
		}
		defer streamResp.Close()

		c.Header("Content-Type", streamResp.ResponseBody.Header.Get("Content-Type"))
		c.Header("Cache-Control", "no-cache")
		c.Header("Connection", "keep-alive")

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

	// Handle non-streaming response
	chatResp, ok := result.(*service.ChatResponse)
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Invalid response"})
		return
	}
	c.JSON(http.StatusOK, chatResp)
}

// ListGatewayModels lists models available through the gateway
func (h *GatewayHandler) ListGatewayModels(c *gin.Context) {
	// Return OpenAI-compatible model list format
	c.JSON(http.StatusOK, gin.H{
		"object": "list",
		"data": []gin.H{
			// TODO: Get actual models from database
		},
	})
}

// Embeddings handles embeddings requests
func (h *GatewayHandler) Embeddings(c *gin.Context) {
	// TODO: Implement embeddings
	c.JSON(http.StatusOK, gin.H{"message": "embeddings"})
}

// AudioTranscriptions handles audio transcription requests
func (h *GatewayHandler) AudioTranscriptions(c *gin.Context) {
	// TODO: Implement audio transcriptions
	c.JSON(http.StatusOK, gin.H{"message": "audio transcriptions"})
}

// AudioTranslations handles audio translation requests
func (h *GatewayHandler) AudioTranslations(c *gin.Context) {
	// TODO: Implement audio translations
	c.JSON(http.StatusOK, gin.H{"message": "audio translations"})
}

// ImageGenerations handles image generation requests
func (h *GatewayHandler) ImageGenerations(c *gin.Context) {
	// TODO: Implement image generations
	c.JSON(http.StatusOK, gin.H{"message": "image generations"})
}

// ImageEdits handles image edit requests
func (h *GatewayHandler) ImageEdits(c *gin.Context) {
	// TODO: Implement image edits
	c.JSON(http.StatusOK, gin.H{"message": "image edits"})
}

// ImageVariations handles image variation requests
func (h *GatewayHandler) ImageVariations(c *gin.Context) {
	// TODO: Implement image variations
	c.JSON(http.StatusOK, gin.H{"message": "image variations"})
}

// BillingSubscription returns subscription info
func (h *GatewayHandler) BillingSubscription(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"userId":           apiKey.UserID,
		"plan":             "default",
		"status":           "active",
		"currentPeriodEnd": nil,
	})
}

// BillingUsage returns usage info
func (h *GatewayHandler) BillingUsage(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// TODO: Implement actual usage calculation
	c.JSON(http.StatusOK, gin.H{
		"totalUsage": gin.H{
			"promptTokens":     0,
			"completionTokens": 0,
			"totalTokens":      0,
			"totalCost":        0,
		},
		"dailyUsage":  gin.H{},
		"usageByModel": []gin.H{},
	})
}

// Ensure models import is used
var _ = models.GatewayAPIKey{}

// ================================== Responses API Handlers ==================================

// CreateResponse handles POST /responses
func (h *GatewayHandler) CreateResponse(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	var req models.ResponseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	stream := req.Stream

	result, err := h.responseService.CreateResponse(c.Request.Context(), apiKey, &req, c.Request.Header)
	if err != nil {
		switch err {
		case service.ErrModelNotFound:
			c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		case service.ErrNoRouteAvailable:
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "No available route for this model"})
		case service.ErrPermissionDenied:
			c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied for this model"})
		case service.ErrInsufficientBalance:
			c.JSON(http.StatusForbidden, gin.H{"error": "Insufficient balance"})
		case service.ErrUpstreamFailed:
			c.JSON(http.StatusBadGateway, gin.H{"error": "Upstream request failed"})
		case service.ErrResponseNotFound:
			c.JSON(http.StatusNotFound, gin.H{"error": "Response not found"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	// Handle streaming response
	if stream {
		streamResp, ok := result.(*service.ResponseStreamingResponse)
		if !ok {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Invalid streaming response"})
			return
		}
		defer streamResp.Close()

		c.Header("Content-Type", streamResp.ResponseBody.Header.Get("Content-Type"))
		c.Header("Cache-Control", "no-cache")
		c.Header("Connection", "keep-alive")

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

	// Handle non-streaming response
	response, ok := result.(*models.Response)
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Invalid response"})
		return
	}
	c.JSON(http.StatusOK, response)
}

// GetResponse handles GET /response/:id
func (h *GatewayHandler) GetResponse(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	responseID := c.Param("id")

	response, err := h.responseService.GetResponse(c.Request.Context(), apiKey, responseID)
	if err != nil {
		if errors.Is(err, service.ErrResponseNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "Response not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

// DeleteResponse handles DELETE /response/:id
func (h *GatewayHandler) DeleteResponse(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	responseID := c.Param("id")

	response, err := h.responseService.DeleteResponse(c.Request.Context(), apiKey, responseID)
	if err != nil {
		if errors.Is(err, service.ErrResponseNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "Response not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

// CancelResponse handles POST /response/:id/cancel
func (h *GatewayHandler) CancelResponse(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	responseID := c.Param("id")

	response, err := h.responseService.CancelResponse(c.Request.Context(), apiKey, responseID)
	if err != nil {
		if errors.Is(err, service.ErrResponseNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "Response not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

// CompactConversation handles POST /response/compact
func (h *GatewayHandler) CompactConversation(c *gin.Context) {
	apiKey := middleware.GetAPIKey(c)
	if apiKey == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	var req models.CompactRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response, err := h.responseService.CompactConversation(c.Request.Context(), apiKey, &req, c.Request.Header)
	if err != nil {
		switch err {
		case service.ErrModelNotFound:
			c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		case service.ErrNoRouteAvailable:
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "No available route for this model"})
		case service.ErrPermissionDenied:
			c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied for this model"})
		case service.ErrInsufficientBalance:
			c.JSON(http.StatusForbidden, gin.H{"error": "Insufficient balance"})
		case service.ErrUpstreamFailed:
			c.JSON(http.StatusBadGateway, gin.H{"error": "Upstream request failed"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, response)
}