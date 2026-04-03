package service

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"strings"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/utils"
)

var (
	ErrModelNotFound      = errors.New("model not found")
	ErrNoRouteAvailable   = errors.New("no available route for this model")
	ErrPermissionDenied   = errors.New("permission denied for this model")
	ErrInsufficientBalance = errors.New("insufficient balance")
	ErrUpstreamFailed     = errors.New("upstream request failed")
)

type ChatRequest struct {
	Model       string                 `json:"model"`
	Messages    []ChatMessage          `json:"messages"`
	Stream      bool                   `json:"stream,omitempty"`
	Temperature float64                `json:"temperature,omitempty"`
	MaxTokens   int                    `json:"max_tokens,omitempty"`
	Extra       map[string]interface{} `json:"-"` // Additional fields
}

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatResponse struct {
	ID      string   `json:"id"`
	Object  string   `json:"object"`
	Created int64    `json:"created"`
	Model   string   `json:"model"`
	Choices []Choice `json:"choices"`
	Usage   *Usage   `json:"usage,omitempty"`
}

type Choice struct {
	Index        int          `json:"index"`
	Message      *ChatMessage `json:"message,omitempty"`
	Delta        *ChatMessage `json:"delta,omitempty"`
	FinishReason string       `json:"finish_reason"`
}

type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

// StreamChunk represents a streaming response chunk
type StreamChunk struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Index        int `json:"index"`
		Delta        struct {
			Role    string `json:"role,omitempty"`
			Content string `json:"content,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	} `json:"choices"`
	Usage *Usage `json:"usage,omitempty"`
}

// StreamingResponse wraps an HTTP response for streaming with logging support
type StreamingResponse struct {
	ResponseBody   *http.Response
	capturedBuffer *bytes.Buffer
	reader         *bufio.Reader

	// For logging after streaming is complete
	apiKey         *models.GatewayAPIKey
	model          *models.Model
	providerName   string
	request        *ChatRequest
	startTime      time.Time
	logRepo        *repository.LogRepository
	logDetailRepo  *repository.LogDetailRepository
	billingService *BillingService
}

// NewStreamingResponse creates a new streaming response wrapper
func NewStreamingResponse(resp *http.Response) *StreamingResponse {
	return &StreamingResponse{
		ResponseBody:   resp,
		capturedBuffer: &bytes.Buffer{},
		reader:         bufio.NewReader(resp.Body),
	}
}

// Read implements io.Reader for streaming
func (s *StreamingResponse) Read(p []byte) (n int, err error) {
	n, err = s.reader.Read(p)
	if n > 0 {
		s.capturedBuffer.Write(p[:n])
	}
	return
}

// GetCapturedData returns the captured streaming data and parses it
func (s *StreamingResponse) GetCapturedData() (content string, usage *Usage, rawData string) {
	rawData = s.capturedBuffer.String()

	// Parse SSE format
	scanner := bufio.NewScanner(strings.NewReader(rawData))
	var contentBuilder strings.Builder
	usage = &Usage{}

	for scanner.Scan() {
		line := scanner.Text()

		// Skip empty lines
		if line == "" {
			continue
		}

		// Look for "data: " prefix
		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		data := strings.TrimPrefix(line, "data: ")

		// Skip [DONE] marker
		if data == "[DONE]" {
			continue
		}

		var chunk StreamChunk
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			continue
		}

		// Extract content from choices
		for _, choice := range chunk.Choices {
			if choice.Delta.Content != "" {
				contentBuilder.WriteString(choice.Delta.Content)
			}
		}

		// Extract usage if present (some providers send it at the end)
		if chunk.Usage != nil {
			usage = chunk.Usage
		}
	}

	content = contentBuilder.String()
	return
}

// LogAfterComplete logs the streaming request after it's complete
func (s *StreamingResponse) LogAfterComplete(ctx context.Context) {
	if s.logRepo == nil {
		return
	}

	content, usage, _ := s.GetCapturedData()
	latency := time.Since(s.startTime).Milliseconds()

	// Estimate completion tokens if not provided
	completionTokens := usage.CompletionTokens
	if completionTokens == 0 && content != "" {
		// Rough estimate: ~4 characters per token
		completionTokens = len(content) / 4
	}

	// Calculate cost
	var cost int64
	if s.model != nil {
		cost = s.billingService.CalculateCost(
			usage.PromptTokens,
			completionTokens,
			s.model.InputTokenPrice,
			s.model.OutputTokenPrice,
		)
	}

	// Create log entry
	logEntry := &models.Log{
		Latency:          int(latency),
		PromptTokens:     usage.PromptTokens,
		CompletionTokens: completionTokens,
		TotalTokens:      usage.PromptTokens + completionTokens,
		Cost:             cost,
		APIKeyID:         s.apiKey.ID,
		ModelName:        s.model.Name,
		ProviderName:     s.providerName,
		Status:           200,
	}

	if err := s.logRepo.Create(ctx, logEntry); err == nil && s.apiKey.LogDetails {
		// Store detailed log
		reqBody, _ := json.Marshal(s.request)

		// Build response object for logging
		respObj := map[string]interface{}{
			"id":      "",
			"object":  "chat.completion",
			"created": time.Now().Unix(),
			"model":   s.model.Name,
			"choices": []map[string]interface{}{
				{
					"index": 0,
					"message": map[string]interface{}{
						"role":    "assistant",
						"content": content,
					},
					"finish_reason": "stop",
				},
			},
			"usage": map[string]int{
				"prompt_tokens":     usage.PromptTokens,
				"completion_tokens": completionTokens,
				"total_tokens":      usage.PromptTokens + completionTokens,
			},
		}
		respBody, _ := json.Marshal(respObj)

		reqGz, _ := utils.GzipCompress(reqBody)
		respGz, _ := utils.GzipCompress(respBody)

		detail := &models.LogDetail{
			LogID:        logEntry.ID,
			RequestBody:  reqGz,
			ResponseBody: respGz,
		}
		s.logDetailRepo.Create(ctx, detail)
	}
}

// Close closes the underlying response body and logs the request
func (s *StreamingResponse) Close() error {
	s.LogAfterComplete(context.Background())
	return s.ResponseBody.Body.Close()
}

type GatewayService struct {
	modelRepo      *repository.ModelRepository
	modelRouteRepo *repository.ModelRouteRepository
	apiKeyRepo     *repository.APIKeyRepository
	channelRepo    *repository.ChannelRepository
	userRepo       *repository.UserRepository
	logRepo        *repository.LogRepository
	logDetailRepo  *repository.LogDetailRepository
	billingService *BillingService
	httpClient     *http.Client
	proxyConfig    *ProxyConfig
}

type ProxyConfig struct {
	HTTPProxy  string
	HTTPSProxy string
	NoProxy    []string
}

func NewGatewayService(
	modelRepo *repository.ModelRepository,
	modelRouteRepo *repository.ModelRouteRepository,
	apiKeyRepo *repository.APIKeyRepository,
	channelRepo *repository.ChannelRepository,
	userRepo *repository.UserRepository,
	logRepo *repository.LogRepository,
	logDetailRepo *repository.LogDetailRepository,
	billingService *BillingService,
	proxyConfig *ProxyConfig,
) *GatewayService {
	return &GatewayService{
		modelRepo:      modelRepo,
		modelRouteRepo: modelRouteRepo,
		apiKeyRepo:     apiKeyRepo,
		channelRepo:    channelRepo,
		userRepo:       userRepo,
		logRepo:        logRepo,
		logDetailRepo:  logDetailRepo,
		billingService: billingService,
		httpClient:     &http.Client{Timeout: 240 * time.Second},
		proxyConfig:    proxyConfig,
	}
}

// HandleChatCompletions handles chat completions requests
// For streaming, returns (*StreamingResponse, error)
// For non-streaming, returns (*ChatResponse, error)
func (s *GatewayService) HandleChatCompletions(ctx context.Context, apiKey *models.GatewayAPIKey, req *ChatRequest, stream bool) (interface{}, error) {
	startTime := time.Now()

	// 1. Find model (supports alias and :latest)
	model, err := s.findModel(ctx, req.Model)
	if err != nil {
		return nil, ErrModelNotFound
	}

	// 2. Select route (weighted random)
	route, err := s.selectRoute(ctx, model.ID)
	if err != nil {
		return nil, ErrNoRouteAvailable
	}

	// 3. Check permission
	if err := s.checkPermission(ctx, apiKey, model.ID); err != nil {
		return nil, err
	}

	// 4. Check balance
	if err := s.checkBalance(ctx, apiKey.UserID, model); err != nil {
		return nil, err
	}

	// 5. Build upstream request
	targetURL := fmt.Sprintf("%s/chat/completions", strings.TrimSuffix(route.Provider.BaseURL, "/"))

	// 6. Send upstream request
	resp, err := s.sendUpstreamRequest(ctx, targetURL, route.Provider.APIKey, req, stream)
	if err != nil {
		latency := time.Since(startTime).Milliseconds()
		s.logError(ctx, apiKey, model, route.Provider.Name, int(latency), 502, err.Error(), req)
		return nil, ErrUpstreamFailed
	}

	// Handle error responses
	if resp.StatusCode >= 400 {
		latency := time.Since(startTime).Milliseconds()
		s.handleUpstreamError(ctx, resp, route)
		s.logError(ctx, apiKey, model, route.Provider.Name, int(latency), resp.StatusCode, "Upstream error", req)
		return nil, fmt.Errorf("upstream error: %d", resp.StatusCode)
	}

	// Handle streaming response
	if stream {
		streamResp := NewStreamingResponse(resp)
		// Store context for later logging
		streamResp.apiKey = apiKey
		streamResp.model = model
		streamResp.providerName = route.Provider.Name
		streamResp.request = req
		streamResp.startTime = startTime
		streamResp.logRepo = s.logRepo
		streamResp.logDetailRepo = s.logDetailRepo
		streamResp.billingService = s.billingService
		return streamResp, nil
	}

	// Handle non-streaming response
	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		return nil, err
	}

	var chatResp ChatResponse
	if err := json.Unmarshal(body, &chatResp); err != nil {
		return nil, err
	}

	// Log and calculate cost
	latency := time.Since(startTime).Milliseconds()
	s.logAndCalculateCost(ctx, apiKey, model, route.Provider.Name, req, &chatResp, int(latency))

	return &chatResp, nil
}

// findModel finds a model by name or alias
func (s *GatewayService) findModel(ctx context.Context, name string) (*models.Model, error) {
	// If name contains ':', search directly
	if strings.Contains(name, ":") {
		return s.modelRepo.FindByNameOrAlias(ctx, name)
	}

	// Try name:latest first
	model, err := s.modelRepo.FindByNameOrAlias(ctx, name+":latest")
	if err == nil {
		return model, nil
	}

	// Fallback to name without tag
	return s.modelRepo.FindByNameOrAlias(ctx, name)
}

// selectRoute selects an upstream route using weighted random selection
func (s *GatewayService) selectRoute(ctx context.Context, modelID uint) (*models.ModelRoute, error) {
	routes, err := s.modelRouteRepo.FindEligibleRoutes(ctx, modelID)
	if err != nil || len(routes) == 0 {
		return nil, ErrNoRouteAvailable
	}

	// Weighted random selection
	weights := make([]int, len(routes))
	for i, r := range routes {
		weights[i] = r.Weight
	}

	selectedIdx := weightedRandomSelect(weights)
	return &routes[selectedIdx], nil
}

// checkPermission checks if the API key has permission to use the model
func (s *GatewayService) checkPermission(ctx context.Context, apiKey *models.GatewayAPIKey, modelID uint) error {
	if apiKey.BindToAllChannels {
		return nil
	}

	channels, err := s.apiKeyRepo.GetChannels(ctx, apiKey.ID)
	if err != nil || len(channels) == 0 {
		return ErrPermissionDenied
	}

	channelIDs := make([]uint, len(channels))
	for i, c := range channels {
		channelIDs[i] = c.ChannelID
	}

	// Check if model is allowed in any of the channels
	for _, channelID := range channelIDs {
		allowedModels, err := s.channelRepo.GetAllowedModels(ctx, channelID)
		if err != nil {
			continue
		}
		for _, am := range allowedModels {
			if am.ModelID == modelID {
				return nil
			}
		}
	}

	return ErrPermissionDenied
}

// checkBalance checks if the user has sufficient balance
func (s *GatewayService) checkBalance(ctx context.Context, userID *uint, model *models.Model) error {
	if model.InputTokenPrice <= 0 && model.OutputTokenPrice <= 0 {
		return nil
	}

	if userID == nil {
		return nil
	}

	user, err := s.userRepo.FindByID(ctx, *userID)
	if err != nil {
		return err
	}

	if user.Balance <= 0 {
		return ErrInsufficientBalance
	}

	return nil
}

// sendUpstreamRequest sends a request to the upstream provider
func (s *GatewayService) sendUpstreamRequest(ctx context.Context, url, apiKey string, req *ChatRequest, stream bool) (*http.Response, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+apiKey)

	// TODO: Add proxy support

	return s.httpClient.Do(httpReq)
}

// handleUpstreamError handles upstream errors, including auto-disabling routes for 429
func (s *GatewayService) handleUpstreamError(ctx context.Context, resp *http.Response, route *models.ModelRoute) {
	if resp.StatusCode == 429 {
		// Check if we should disable the route
		count, err := s.modelRouteRepo.CountEligible(ctx, route.ModelID)
		if err == nil && count > 1 {
			// Disable for 10 minutes
			until := time.Now().Add(10 * time.Minute)
			s.modelRouteRepo.DisableUntil(ctx, route.ID, until)
		}
	}
}

// logAndCalculateCost logs the request and calculates cost
func (s *GatewayService) logAndCalculateCost(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, req *ChatRequest, resp *ChatResponse, latency int) {
	var promptTokens, completionTokens, totalTokens int
	if resp.Usage != nil {
		promptTokens = resp.Usage.PromptTokens
		completionTokens = resp.Usage.CompletionTokens
		totalTokens = resp.Usage.TotalTokens
	}

	cost := s.billingService.CalculateCost(promptTokens, completionTokens, model.InputTokenPrice, model.OutputTokenPrice)

	// Determine owner channel (for shared channels)
	ownerChannelID, ownerChannelUserID := s.determineChannelOwner(ctx, apiKey, model.ID)

	// Deduct cost
	if cost > 0 && apiKey.UserID != nil {
		s.billingService.DeductAndDistribute(ctx, apiKey.UserID, ownerChannelUserID, cost)
	}

	// Create log entry
	logEntry := &models.Log{
		Latency:          latency,
		PromptTokens:     promptTokens,
		CompletionTokens: completionTokens,
		TotalTokens:      totalTokens,
		Cost:             cost,
		APIKeyID:         apiKey.ID,
		ModelName:        model.Name,
		ProviderName:     providerName,
		OwnerChannelID:   ownerChannelID,
		OwnerChannelUserID: ownerChannelUserID,
		Status:           200,
	}

	if err := s.logRepo.Create(ctx, logEntry); err == nil && apiKey.LogDetails {
		// Store detailed log
		reqBody, _ := json.Marshal(req)
		respBody, _ := json.Marshal(resp)
		reqGz, _ := utils.GzipCompress(reqBody)
		respGz, _ := utils.GzipCompress(respBody)

		detail := &models.LogDetail{
			LogID:        logEntry.ID,
			RequestBody:  reqGz,
			ResponseBody: respGz,
		}
		s.logDetailRepo.Create(ctx, detail)
	}
}

// logError logs an error request
func (s *GatewayService) logError(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, latency, status int, errMsg string, req *ChatRequest) {
	logEntry := &models.Log{
		Latency:      latency,
		APIKeyID:     apiKey.ID,
		ModelName:    model.Name,
		ProviderName: providerName,
		Status:       status,
		ErrorMessage: errMsg,
	}

	if err := s.logRepo.Create(ctx, logEntry); err == nil && apiKey.LogDetails {
		reqBody, _ := json.Marshal(req)
		reqGz, _ := utils.GzipCompress(reqBody)

		detail := &models.LogDetail{
			LogID:       logEntry.ID,
			RequestBody: reqGz,
		}
		s.logDetailRepo.Create(ctx, detail)
	}
}

// determineChannelOwner determines the channel owner for billing
func (s *GatewayService) determineChannelOwner(ctx context.Context, apiKey *models.GatewayAPIKey, modelID uint) (*uint, *uint) {
	// TODO: Implement channel owner determination logic
	return nil, nil
}

// weightedRandomSelect selects an index based on weights
func weightedRandomSelect(weights []int) int {
	total := 0
	for _, w := range weights {
		total += w
	}

	// Handle edge case where all weights are 0
	if total <= 0 {
		return len(weights) - 1
	}

	r := rand.Intn(total)
	for i, w := range weights {
		r -= w
		if r < 0 {
			return i
		}
	}

	return len(weights) - 1
}