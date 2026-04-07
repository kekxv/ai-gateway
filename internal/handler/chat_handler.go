package handler

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
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

	// Delete messages after specified ID (for regenerate/edit) - must do BEFORE getting prevMessages
	if req.DeleteAfterID != nil {
		deleteID := *req.DeleteAfterID
		if err := h.messageRepo.DeleteAfterID(c.Request.Context(), conversationID, deleteID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
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

	// Add new user message (support multimodal)
	var userContent service.ChatMessageContent
	if len(req.Parts) > 0 {
		// Convert models.ChatContentPart to service.ChatContentPart
		parts := make([]service.ChatContentPart, len(req.Parts))
		for i, p := range req.Parts {
			parts[i] = service.ChatContentPart{
				Type: p.Type,
				Text: p.Text,
			}
			if p.ImageURL != nil {
				parts[i].ImageURL = &service.ChatMediaURL{
					URL:    p.ImageURL.URL,
					Detail: p.ImageURL.Detail,
				}
			}
		}
		userContent = service.ChatMessageContent{Parts: parts}
	} else {
		userContent = service.ChatMessageContent{StringContent: req.Content}
	}

	chatMessages = append(chatMessages, service.ChatMessage{
		Role:    "user",
		Content: userContent,
	})

	// Save user message (store text content for simplicity)
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
		Model:       conversation.Model,
		Messages:    chatMessages,
		Stream:      req.Stream,
		Temperature: settings.Temperature,
		MaxTokens:   settings.MaxTokens,
	}
	if settings.TopP != 0 {
		chatReq.Extra = map[string]interface{}{"top_p": settings.TopP}
	}

	// Convert tools from frontend request to service format
	if len(req.Tools) > 0 {
		chatReq.Tools = make([]service.ToolDefinition, len(req.Tools))
		for i, tool := range req.Tools {
			chatReq.Tools[i] = service.ToolDefinition{
				Type: tool.Type,
				Function: service.ToolFunctionSpec{
					Name:        tool.Function.Name,
					Description: tool.Function.Description,
					Parameters:  tool.Function.Parameters,
				},
			}
		}
	}

	// Create virtual API key for user (bind to all channels)
	userID := user.ID
	virtualAPIKey := &models.GatewayAPIKey{
		ID:               0, // Virtual key, no real ID
		UserID:           &userID,
		BindToAllChannels: true, // Allow access to all models
		IsChatKey:        true,  // Enable logging for chat requests
		LogDetails:       true,  // Enable detailed logging for chat
	}

	stream := req.Stream

	result, err := h.gatewayService.HandleChatCompletions(c.Request.Context(), virtualAPIKey, chatReq, stream, c.Request.Header)
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

		c.Stream(func(w io.Writer) bool {
			buf := make([]byte, 1024)
			n, err := streamResp.Read(buf)
			if err != nil {
				// Stream ended.
				// Logic for splicing and saving is now moved to frontend via AddMessage.
				// We only handle title update if it's the first message.
				if len(prevMessages) == 0 && conversation.Title == "New Chat" {
					title := req.Content
					if len(title) > 50 {
						title = title[:50] + "..."
					}
					h.conversationRepo.UpdateTitle(context.Background(), conversationID, title)
				}
				return false
			}

			// Write SSE format
			data := buf[:n]
			w.Write(data)

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
		"data":  chatResp.Choices[0].Message,
		"usage": chatResp.Usage,
	})
}

// AddMessage adds a new message to a conversation (typically from frontend)
func (h *ChatHandler) AddMessage(c *gin.Context) {
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

	var msg models.Message
	if err := c.ShouldBindJSON(&msg); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	msg.ConversationID = conversationID
	if err := h.messageRepo.Create(c.Request.Context(), &msg); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Update conversation timestamp
	conversation.UpdatedAt = time.Now()
	h.conversationRepo.Update(c.Request.Context(), conversation)

	c.JSON(http.StatusOK, gin.H{"data": msg})
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

// UploadFile handles file uploads for chat
// Supports all file types and returns base64 data URL
func (h *ChatHandler) UploadFile(c *gin.Context) {
	user := middleware.GetCurrentUser(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No file provided"})
		return
	}

	// Limit file size to 20MB
	if file.Size > 20*1024*1024 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "File too large (max 20MB)"})
		return
	}

	// Read file content
	content, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer content.Close()

	data, err := io.ReadAll(content)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Convert to base64
	base64Data := base64.StdEncoding.EncodeToString(data)

	// Determine MIME type
	mimeType := file.Header.Get("Content-Type")
	if mimeType == "" {
		mimeType = "application/octet-stream"
	}

	// Return base64 data URL format
	dataURL := fmt.Sprintf("data:%s;base64,%s", mimeType, base64Data)

	c.JSON(http.StatusOK, gin.H{
		"data":     dataURL,
		"filename": file.Filename,
		"size":     file.Size,
		"mimeType": mimeType,
	})
}

// readFileAsBase64 reads a multipart file and returns base64 data URL
func readFileAsBase64(file *multipart.FileHeader) (string, string, error) {
	content, err := file.Open()
	if err != nil {
		return "", "", err
	}
	defer content.Close()

	data, err := io.ReadAll(content)
	if err != nil {
		return "", "", err
	}

	mimeType := file.Header.Get("Content-Type")
	if mimeType == "" {
		mimeType = "application/octet-stream"
	}

	base64Data := base64.StdEncoding.EncodeToString(data)
	dataURL := fmt.Sprintf("data:%s;base64,%s", mimeType, base64Data)

	return dataURL, mimeType, nil
}