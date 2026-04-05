package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/service"
)

// ChatHandler handles chat conversation operations
type ChatHandler struct {
	conversationRepo *repository.ConversationRepository
	messageRepo      *repository.MessageRepository
	userRepo         *repository.UserRepository
	gatewayService   *service.GatewayService
	billingService   *service.BillingService
}

// NewChatHandler creates a new chat handler
func NewChatHandler(
	conversationRepo *repository.ConversationRepository,
	messageRepo *repository.MessageRepository,
	userRepo *repository.UserRepository,
	gatewayService *service.GatewayService,
	billingService *service.BillingService,
) *ChatHandler {
	return &ChatHandler{
		conversationRepo: conversationRepo,
		messageRepo:      messageRepo,
		userRepo:         userRepo,
		gatewayService:   gatewayService,
		billingService:   billingService,
	}
}

// ListConversations lists all conversations for the current user
func (h *ChatHandler) ListConversations(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	conversations, err := h.conversationRepo.GetByUserID(c.Request.Context(), user.ID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": conversations})
}

// CreateConversation creates a new conversation
func (h *ChatHandler) CreateConversation(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	var req models.CreateConversationRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Default title if not provided
	title := req.Title
	if title == "" {
		title = "New Chat"
	}

	// Default model if not provided
	model := req.Model
	if model == "" {
		model = "gpt-3.5-turbo"
	}

	// Serialize settings
	settingsJSON, _ := json.Marshal(req.Settings)

	conversation := &models.Conversation{
		UserID:       user.ID,
		Title:        title,
		Model:        model,
		SystemPrompt: req.SystemPrompt,
		Settings:     string(settingsJSON),
	}

	if err := h.conversationRepo.Create(c.Request.Context(), conversation); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": conversation})
}

// GetConversation gets a conversation by ID
func (h *ChatHandler) GetConversation(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	id := c.Param("id")
	var conversationID uint
	if err := parseUint(id, &conversationID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid ID"})
		return
	}

	conversation, err := h.conversationRepo.GetByID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Conversation not found"})
		return
	}

	// Check ownership
	if conversation.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": conversation})
}

// UpdateConversation updates a conversation
func (h *ChatHandler) UpdateConversation(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	id := c.Param("id")
	var conversationID uint
	if err := parseUint(id, &conversationID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid ID"})
		return
	}

	conversation, err := h.conversationRepo.GetByID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Conversation not found"})
		return
	}

	// Check ownership
	if conversation.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied"})
		return
	}

	var req models.UpdateConversationRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Update fields
	if req.Title != "" {
		conversation.Title = req.Title
	}
	if req.Model != "" {
		conversation.Model = req.Model
	}
	conversation.SystemPrompt = req.SystemPrompt
	settingsJSON, _ := json.Marshal(req.Settings)
	conversation.Settings = string(settingsJSON)
	conversation.UpdatedAt = time.Now()

	if err := h.conversationRepo.Update(c.Request.Context(), conversation); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": conversation})
}

// DeleteConversation deletes a conversation
func (h *ChatHandler) DeleteConversation(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	id := c.Param("id")
	var conversationID uint
	if err := parseUint(id, &conversationID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid ID"})
		return
	}

	conversation, err := h.conversationRepo.GetByID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Conversation not found"})
		return
	}

	// Check ownership
	if conversation.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied"})
		return
	}

	// Delete messages first
	if err := h.messageRepo.DeleteByConversationID(c.Request.Context(), conversationID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Delete conversation
	if err := h.conversationRepo.Delete(c.Request.Context(), conversationID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Deleted successfully"})
}

// GetMessages gets all messages for a conversation
func (h *ChatHandler) GetMessages(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	id := c.Param("id")
	var conversationID uint
	if err := parseUint(id, &conversationID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid ID"})
		return
	}

	conversation, err := h.conversationRepo.GetByID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Conversation not found"})
		return
	}

	// Check ownership
	if conversation.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied"})
		return
	}

	messages, err := h.messageRepo.GetByConversationID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": messages})
}

// SendMessage sends a message and gets AI response (with streaming support)
func (h *ChatHandler) SendMessage(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	id := c.Param("id")
	var conversationID uint
	if err := parseUint(id, &conversationID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid ID"})
		return
	}

	conversation, err := h.conversationRepo.GetByID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Conversation not found"})
		return
	}

	// Check ownership
	if conversation.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied"})
		return
	}

	var req models.ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get previous messages
	prevMessages, err := h.messageRepo.GetByConversationID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Build chat messages
	chatMessages := []service.ChatMessage{}

	// Add system prompt if set
	if conversation.SystemPrompt != "" {
		chatMessages = append(chatMessages, service.ChatMessage{
			Role: "system",
			Content: service.ChatMessageContent{StringContent: conversation.SystemPrompt},
		})
	}

	// Add previous messages
	for _, msg := range prevMessages {
		chatMessages = append(chatMessages, service.ChatMessage{
			Role: msg.Role,
			Content: service.ChatMessageContent{StringContent: msg.Content},
		})
	}

	// Add new user message
	chatMessages = append(chatMessages, service.ChatMessage{
		Role: "user",
		Content: service.ChatMessageContent{StringContent: req.Content},
	})

	// Save user message
	userMsg := &models.Message{
		ConversationID: conversationID,
		Role:           "user",
		Content:        req.Content,
	}
	if err := h.messageRepo.Create(c.Request.Context(), userMsg); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Parse conversation settings
	var settings models.ConversationSettings
	if conversation.Settings != "" {
		json.Unmarshal([]byte(conversation.Settings), &settings)
	}

	// Use request settings if provided (override)
	if req.Settings.Temperature != 0 {
		settings.Temperature = req.Settings.Temperature
	}
	if req.Settings.MaxTokens != 0 {
		settings.MaxTokens = req.Settings.MaxTokens
	}
	if req.Settings.TopP != 0 {
		settings.TopP = req.Settings.TopP
	}

	// Build chat request
	chatReq := &service.ChatRequest{
		Model:    conversation.Model,
		Messages: chatMessages,
		Stream:   req.Stream,
		Temperature: settings.Temperature,
		MaxTokens:   settings.MaxTokens,
	}
	if settings.TopP != 0 {
		chatReq.Extra = map[string]interface{}{"top_p": settings.TopP}
	}

	// Create virtual API key for user (bind to all channels)
	userID := user.ID
	virtualAPIKey := &models.GatewayAPIKey{
		ID:               0, // Virtual key, no real ID
		UserID:           &userID,
		BindToAllChannels: true, // Allow access to all models
	}

	stream := req.Stream

	result, err := h.gatewayService.HandleChatCompletions(c.Request.Context(), virtualAPIKey, chatReq, stream)
	if err != nil {
		// Save error as assistant message
		errorMsg := &models.Message{
			ConversationID: conversationID,
			Role:           "assistant",
			Content:        fmt.Sprintf("Error: %s", err.Error()),
		}
		h.messageRepo.Create(c.Request.Context(), errorMsg)

		switch err {
		case service.ErrModelNotFound:
			c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		case service.ErrNoRouteAvailable:
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "No available route for this model"})
		case service.ErrPermissionDenied:
			c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied for this model"})
		case service.ErrInsufficientBalance:
			c.JSON(http.StatusForbidden, gin.H{"error": "Insufficient balance"})
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

		c.Header("Content-Type", "text/event-stream")
		c.Header("Cache-Control", "no-cache")
		c.Header("Connection", "keep-alive")

		// Stream and capture content
		var contentBuilder strings.Builder
		flusher, _ := c.Writer.(http.Flusher)

		c.Stream(func(w io.Writer) bool {
			buf := make([]byte, 1024)
			n, err := streamResp.Read(buf)
			if err != nil {
				// Stream ended, save assistant message
				content := contentBuilder.String()
				if content != "" {
					assistantMsg := &models.Message{
						ConversationID: conversationID,
						Role:           "assistant",
						Content:        content,
					}
					h.messageRepo.Create(context.Background(), assistantMsg)

					// Update conversation title if first message
					if len(prevMessages) == 0 && conversation.Title == "New Chat" {
						// Use first 50 chars of user message as title
						title := req.Content
						if len(title) > 50 {
							title = title[:50] + "..."
						}
						h.conversationRepo.UpdateTitle(context.Background(), conversationID, title)
					}
				}
				return false
			}

			// Write SSE format
			data := buf[:n]
			w.Write(data)
			flusher.Flush()

			// Parse and capture content
			lines := strings.Split(string(data), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "data: ") {
					jsonData := strings.TrimPrefix(line, "data: ")
					if jsonData != "[DONE]" {
						var chunk service.StreamChunk
						if json.Unmarshal([]byte(jsonData), &chunk) == nil {
							for _, choice := range chunk.Choices {
								if choice.Delta.Content != "" {
									contentBuilder.WriteString(choice.Delta.Content)
								}
							}
						}
					}
				}
			}

			return true
		})
		return
	}

	// Handle non-streaming response
	chatResp, ok := result.(*service.ChatResponse)
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Invalid response"})
		return
	}

	// Extract assistant content
	var assistantContent string
	if len(chatResp.Choices) > 0 && chatResp.Choices[0].Message != nil {
		assistantContent = chatResp.Choices[0].Message.Content.GetText()
	}

	// Save assistant message
	assistantMsg := &models.Message{
		ConversationID: conversationID,
		Role:           "assistant",
		Content:        assistantContent,
		Tokens:         chatResp.Usage.CompletionTokens,
	}
	h.messageRepo.Create(c.Request.Context(), assistantMsg)

	// Update user message tokens
	userMsg.Tokens = chatResp.Usage.PromptTokens
	// Note: we can't easily update, so we'll leave it

	// Update conversation title if first message
	if len(prevMessages) == 0 && conversation.Title == "New Chat" {
		title := req.Content
		if len(title) > 50 {
			title = title[:50] + "..."
		}
		h.conversationRepo.UpdateTitle(c.Request.Context(), conversationID, title)
	}

	// Update conversation timestamp
	conversation.UpdatedAt = time.Now()
	h.conversationRepo.Update(c.Request.Context(), conversation)

	c.JSON(http.StatusOK, gin.H{
		"data": assistantMsg,
		"usage": chatResp.Usage,
	})
}

// Helper function to parse uint
func parseUint(s string, v *uint) error {
	var i int
	if err := parseInt(s, &i); err != nil {
		return err
	}
	if i < 0 {
		return errors.New("negative value")
	}
	*v = uint(i)
	return nil
}

func parseInt(s string, v *int) error {
	_, err := fmt.Sscanf(s, "%d", v)
	return err
}