package handler

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"mime/multipart"
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

// UpdateTitle updates only the title of a conversation
func (h *ChatHandler) UpdateTitle(c *gin.Context) {
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

	var req struct {
		Title string `json:"title" binding:"required,max=100"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ctx := c.Request.Context()
	conversation, err := h.conversationRepo.GetByID(ctx, conversationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Conversation not found"})
		return
	}

	// Check ownership
	if conversation.UserID != user.ID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Permission denied"})
		return
	}

	if err := h.conversationRepo.UpdateTitle(ctx, conversationID, req.Title); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Title updated", "title": req.Title})
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
// Simplified: frontend provides full OpenAI-compatible request, backend only forwards
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

	// Convert frontend request to service format
	chatMessages := make([]service.ChatMessage, len(req.Messages))
	for i, msg := range req.Messages {
		// Parse content (supports string or array format)
		var content service.ChatMessageContent
		if err := json.Unmarshal(msg.Content, &content); err != nil {
			// Fallback to string
			content = service.ChatMessageContent{StringContent: string(msg.Content)}
		}

		// Parse tool_calls if present
		var toolCalls []service.ToolCall
		if len(msg.ToolCalls) > 0 {
			if err := json.Unmarshal(msg.ToolCalls, &toolCalls); err != nil {
				toolCalls = nil
			}
		}

		chatMessages[i] = service.ChatMessage{
			Role:       msg.Role,
			Content:    content,
			ToolCalls:  toolCalls,
			ToolCallID: msg.ToolCallID,
		}
	}

	// Build service request
	chatReq := &service.ChatRequest{
		Model:            req.Model,
		Messages:         chatMessages,
		Stream:           req.Stream,
		Temperature:      req.Temperature,
		MaxTokens:        req.MaxTokens,
		ReasoningEffort:  req.ReasoningEffort,
		Think:            req.Think,
	}

	// Parse advanced thinking configs if present
	if len(req.Thinking) > 0 {
		var thinking service.ThinkingConfig
		if err := json.Unmarshal(req.Thinking, &thinking); err == nil {
			chatReq.Thinking = &thinking
		}
	}
	if len(req.GenerationConfig) > 0 {
		var genConfig service.GenerationConfig
		if err := json.Unmarshal(req.GenerationConfig, &genConfig); err == nil {
			chatReq.GenerationConfig = &genConfig
		}
	}

	// Convert tools
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

	// Handle enable_thinking
	if req.EnableThinking {
		chatReq.Extra = map[string]interface{}{"enable_thinking": true}
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

	// Serialize chatReq for service consumption
	rawBody, _ := json.Marshal(chatReq)

	result, err := h.gatewayService.HandleChatCompletions(c.Request.Context(), virtualAPIKey, chatReq, rawBody, req.Stream, c.Request.Header, c.Request.URL.Path)
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
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	// Handle streaming response
	if req.Stream {
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

	// Update conversation timestamp
	conversation.UpdatedAt = time.Now()
	h.conversationRepo.Update(c.Request.Context(), conversation)

	c.JSON(http.StatusOK, chatResp)
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

// DeleteMessagesAfter deletes all messages after a specific message ID in a conversation
func (h *ChatHandler) DeleteMessagesAfter(c *gin.Context) {
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

	messageIDStr := c.Param("message_id")
	var messageID uint
	if err := parseUint(messageIDStr, &messageID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid message ID"})
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

	// Delete messages after the specified ID
	if err := h.messageRepo.DeleteAfterID(c.Request.Context(), conversationID, messageID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Messages deleted"})
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
		c.JSON(http.StatusBadRequest, gin.H{"error": "File too large (max 20MB)"	})
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

// GenerateTitle generates a title for the conversation based on the first user message
func (h *ChatHandler) GenerateTitle(c *gin.Context) {
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

	// Get the first user message
	messages, err := h.messageRepo.GetByConversationID(c.Request.Context(), conversationID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Find first user message
	var firstUserContent string
	for _, msg := range messages {
		if msg.Role == "user" {
			// Try to parse as multimodal content
			var parts []models.ChatContentPart
			if err := json.Unmarshal([]byte(msg.Content), &parts); err == nil && len(parts) > 0 {
				// Extract text from parts
				for _, p := range parts {
					if p.Type == "text" && p.Text != "" {
						firstUserContent = p.Text
						break
					}
				}
			} else {
				firstUserContent = msg.Content
			}
			break
		}
	}

	if firstUserContent == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No user message found"})
		return
	}

	// Build a request to generate title
	// Use the conversation's model to generate title
	// Note: Disable reasoning/thinking to get direct output
	chatReq := &service.ChatRequest{
		Model: conversation.Model,
		Messages: []service.ChatMessage{
			{
				Role:    "system",
				Content: service.ChatMessageContent{StringContent: "请根据用户的第一条消息，生成一个简短的对话标题（不超过20个汉字，不要使用引号）。直接返回标题，不要其他内容。"},
			},
			{
				Role:    "user",
				Content: service.ChatMessageContent{StringContent: firstUserContent},
			},
		},
		Stream:           false,
		MaxTokens:        50, // Title should be short
		Temperature:      0.7,
		ReasoningEffort:  "none", // Disable thinking/reasoning for direct output
	}

	// Create virtual API key for user
	userID := user.ID
	virtualAPIKey := &models.GatewayAPIKey{
		UserID:           &userID,
		BindToAllChannels: true,
		IsChatKey:        true,
		LogDetails:       false, // Don't log title generation
	}

	// Call gateway service to generate title
	titleRawBody, _ := json.Marshal(chatReq)
	result, err := h.gatewayService.HandleChatCompletions(c.Request.Context(), virtualAPIKey, chatReq, titleRawBody, false, c.Request.Header, c.Request.URL.Path)
	if err != nil {
		log.Printf("[GenerateTitle] HandleChatCompletions error: %v, model: %s", err, conversation.Model)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate title: " + err.Error()})
		return
	}

	chatResp, ok := result.(*service.ChatResponse)
	if !ok {
		log.Printf("[GenerateTitle] Invalid response type: %T", result)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Invalid response type"})
		return
	}

	// Extract title from response
	title := ""
	if len(chatResp.Choices) > 0 {
		choice := chatResp.Choices[0]
		if choice.Message != nil {
			// Use GetTextWithReasoning to support models that put content in reasoning field
			title = choice.Message.GetTextWithReasoning()
		}
		if choice.Delta != nil && title == "" {
			title = choice.Delta.GetTextWithReasoning()
		}
	}

	// Debug: if title is empty, return more info
	if title == "" {
		// Return original title with debug info
		debugPrompt := firstUserContent
		if len(debugPrompt) > 100 {
			debugPrompt = debugPrompt[:100]
		}
		c.JSON(http.StatusOK, gin.H{"data": gin.H{
			"title":      conversation.Title,
			"debug":      "AI returned empty content",
			"model":      conversation.Model,
			"prompt":     debugPrompt,
			"choices":    len(chatResp.Choices),
			"hasMessage": len(chatResp.Choices) > 0 && chatResp.Choices[0].Message != nil,
			"hasDelta":   len(chatResp.Choices) > 0 && chatResp.Choices[0].Delta != nil,
		}})
		return
	}

	// Clean up title - remove quotes and trim
	title = trimQuotes(title)
	if len(title) > 50 {
		title = title[:50]
	}

	// Update conversation title
	if err := h.conversationRepo.UpdateTitle(c.Request.Context(), conversationID, title); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"data": gin.H{"title": title}})
}

// trimQuotes removes surrounding quotes and thinking tags from a string
func trimQuotes(s string) string {
	// Remove thinking/reasoning tags first
	s = removeThinkingTags(s)
	s = trimChar(s, '"')
	s = trimChar(s, '\'')
	s = trimChar(s, '`')
	return s
}

// removeThinkingTags removes <think>, <thinking>, <reasoning>, <thought> tags and their content
func removeThinkingTags(s string) string {
	// Remove <think>...</think>
	for {
		start := strings.Index(s, "<think>")
		if start == -1 {
			break
		}
		end := strings.Index(s, "</think>")
		if end == -1 || end <= start {
			// No closing tag, remove from start to end of string
			s = s[:start]
			break
		}
		s = s[:start] + s[end+8:]
	}

	// Remove <thinking>...</thinking>
	for {
		start := strings.Index(s, "<thinking>")
		if start == -1 {
			break
		}
		end := strings.Index(s, "</thinking>")
		if end == -1 || end <= start {
			s = s[:start]
			break
		}
		s = s[:start] + s[end+11:]
	}

	// Remove <reasoning>...</reasoning>
	for {
		start := strings.Index(s, "<reasoning>")
		if start == -1 {
			break
		}
		end := strings.Index(s, "</reasoning>")
		if end == -1 || end <= start {
			s = s[:start]
			break
		}
		s = s[:start] + s[end+12:]
	}

	// Remove <thought>...</thought>
	for {
		start := strings.Index(s, "<thought>")
		if start == -1 {
			break
		}
		end := strings.Index(s, "</thought>")
		if end == -1 || end <= start {
			s = s[:start]
			break
		}
		s = s[:start] + s[end+10:]
	}

	// Remove incomplete tags at start/end
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "<think>") || strings.HasPrefix(s, "<thinking>") || strings.HasPrefix(s, "<reasoning>") || strings.HasPrefix(s, "<thought>") {
		// Find the end of the tag
		for i, c := range s {
			if c == '>' {
				s = s[i+1:]
				break
			}
		}
	}

	return strings.TrimSpace(s)
}

func trimChar(s string, c byte) string {
	for len(s) > 0 && s[0] == c {
		s = s[1:]
	}
	for len(s) > 0 && s[len(s)-1] == c {
		s = s[:len(s)-1]
	}
	return s
}