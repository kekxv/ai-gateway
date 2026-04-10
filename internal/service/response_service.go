package service

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/utils"
)

var (
	ErrResponseNotFound = errors.New("response not found")
)

// ResponseService handles Responses API requests
type ResponseService struct {
	modelRepo      *repository.ModelRepository
	modelRouteRepo *repository.ModelRouteRepository
	providerRepo   *repository.ProviderRepository
	apiKeyRepo     *repository.APIKeyRepository
	channelRepo    *repository.ChannelRepository
	userRepo       *repository.UserRepository
	logRepo        *repository.LogRepository
	logDetailRepo  *repository.LogDetailRepository
	billingService *BillingService
	httpClient     *http.Client
	proxyConfig    *ProxyConfig
	cache          *ResponseCache
}

// NewResponseService creates a new ResponseService
func NewResponseService(
	modelRepo *repository.ModelRepository,
	modelRouteRepo *repository.ModelRouteRepository,
	providerRepo *repository.ProviderRepository,
	apiKeyRepo *repository.APIKeyRepository,
	channelRepo *repository.ChannelRepository,
	userRepo *repository.UserRepository,
	logRepo *repository.LogRepository,
	logDetailRepo *repository.LogDetailRepository,
	billingService *BillingService,
	proxyConfig *ProxyConfig,
) *ResponseService {
	// Create custom transport with proxy bypass support
	transport := &http.Transport{
		Proxy: func(req *http.Request) (*url.URL, error) {
			if utils.ShouldBypassProxy(req.URL.String(), proxyConfig.NoProxy) {
				return nil, nil // Bypass proxy for matched URLs
			}
			return http.ProxyFromEnvironment(req)
		},
	}

	return &ResponseService{
		modelRepo:      modelRepo,
		modelRouteRepo: modelRouteRepo,
		providerRepo:   providerRepo,
		apiKeyRepo:     apiKeyRepo,
		channelRepo:    channelRepo,
		userRepo:       userRepo,
		logRepo:        logRepo,
		logDetailRepo:  logDetailRepo,
		billingService: billingService,
		httpClient:     &http.Client{Timeout: 240 * time.Second, Transport: transport},
		proxyConfig:    proxyConfig,
		cache:          NewResponseCache(24 * time.Hour), // 1 day TTL
	}
}

// CreateResponse handles POST /responses
// For streaming, returns (*ResponseStreamingResponse, error)
// For non-streaming, returns (*models.Response, error)
func (s *ResponseService) CreateResponse(ctx context.Context, apiKey *models.GatewayAPIKey, req *models.ResponseRequest, requestHeaders http.Header) (interface{}, error) {
	startTime := time.Now()

	// Extract headers for logging and forwarding
	forwardHeaders, headersJSON := extractForwardableHeaders(requestHeaders)

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

	// Create initial log entry at request start
	// Skip logging for virtual API keys (ID=0)
	logEntry := &models.Log{
		APIKeyID:       getAPIKeyIDPtr(apiKey.ID),
		ModelName:      model.Name,
		ProviderName:   route.Provider.Name,
		Status:         0, // pending
		RequestHeaders: headersJSON,
	}
	if apiKey.ID != 0 {
		if err := s.logRepo.Create(ctx, logEntry); err != nil {
			logEntry.ID = 0 // Continue without log if creation fails
		} else if apiKey.LogDetails {
			// Store request body immediately at request start
			reqBody, _ := json.Marshal(req)
			reqGz, _ := utils.GzipCompress(reqBody)
			detail := &models.LogDetail{
				LogID:       logEntry.ID,
				RequestBody: reqGz,
			}
			s.logDetailRepo.Create(ctx, detail)
		}
	} else {
		logEntry.ID = 0 // Virtual key, no logging
	}

	// 3. Check permission
	if err := s.checkPermission(ctx, apiKey, model.ID); err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 403, err.Error())
		return nil, err
	}

	// 4. Check balance
	if err := s.checkBalance(ctx, apiKey.UserID, model); err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 402, err.Error())
		return nil, err
	}

	// 5. Build upstream URL for Responses API
	// Use type-specific base URL if available, fallback to default
	baseURL := route.Provider.GetBaseURLForType("openai")
	targetURL := fmt.Sprintf("%s/responses", strings.TrimSuffix(baseURL, "/"))

	// 6. Send upstream request with forwarded headers
	resp, err := s.sendResponseUpstreamRequest(ctx, targetURL, route.Provider.APIKey, req, req.Stream, forwardHeaders)
	if err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 502, err.Error())
		return nil, ErrUpstreamFailed
	}

	// Handle error responses
	if resp.StatusCode >= 400 {
		latency := time.Since(startTime).Milliseconds()
		s.handleUpstreamError(ctx, resp, route)
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		s.updateLogError(ctx, logEntry.ID, int(latency), resp.StatusCode, string(body))
		return nil, fmt.Errorf("upstream error: %d", resp.StatusCode)
	}

	// Handle streaming response
	if req.Stream {
		streamResp := NewResponseStreamingResponse(resp)
		// Store context for later logging
		streamResp.ctx = ctx
		streamResp.logID = logEntry.ID
		streamResp.apiKey = apiKey
		streamResp.model = model
		streamResp.providerName = route.Provider.Name
		streamResp.request = req
		streamResp.startTime = startTime
		streamResp.logRepo = s.logRepo
		streamResp.logDetailRepo = s.logDetailRepo
		streamResp.billingService = s.billingService
		streamResp.cache = s.cache
		streamResp.provider = &route.Provider
		// Extract response headers
		streamResp.responseHeaders = extractResponseHeaders(resp.Header)
		return streamResp, nil
	}

	// Handle non-streaming response
	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
		return nil, err
	}

	var response models.Response
	if err := json.Unmarshal(body, &response); err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
		return nil, err
	}

	// Cache response ID -> provider mapping for later operations
	if response.ID != "" {
		s.cache.Set(response.ID, &route.Provider, baseURL)
	}

	// Update log with completion data
	latency := time.Since(startTime).Milliseconds()
	respHeaders := extractResponseHeaders(resp.Header)
	s.updateLogAndCalculateCost(ctx, apiKey, model, route.Provider.Name, logEntry.ID, req, &response, int(latency), respHeaders)

	return &response, nil
}

// getProviderForResponse gets the provider for a response ID from cache, or falls back to default
func (s *ResponseService) getProviderForResponse(ctx context.Context, responseID string) (*models.Provider, error) {
	// First check cache
	entry := s.cache.Get(responseID)
	if entry != nil {
		return &models.Provider{
			ID:      entry.ProviderID,
			BaseURL: entry.ProviderURL,
			APIKey:  entry.ProviderKey,
		}, nil
	}
	// Fall back to default provider
	return s.getDefaultProvider(ctx)
}

// GetResponse handles GET /responses/:id - forwards to upstream provider
func (s *ResponseService) GetResponse(ctx context.Context, apiKey *models.GatewayAPIKey, responseID string) (*models.Response, error) {
	provider, err := s.getProviderForResponse(ctx, responseID)
	if err != nil {
		return nil, err
	}

	targetURL := fmt.Sprintf("%s/responses/%s", strings.TrimSuffix(provider.BaseURL, "/"), responseID)

	httpReq, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Authorization", "Bearer "+provider.APIKey)

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, ErrUpstreamFailed
	}
	defer resp.Body.Close()

	if resp.StatusCode == 404 {
		return nil, ErrResponseNotFound
	}

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("upstream error: %d - %s", resp.StatusCode, string(body))
	}

	var response models.Response
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, err
	}

	return &response, nil
}

// DeleteResponse handles DELETE /responses/:id - forwards to upstream provider
func (s *ResponseService) DeleteResponse(ctx context.Context, apiKey *models.GatewayAPIKey, responseID string) (*models.DeleteResponse, error) {
	provider, err := s.getProviderForResponse(ctx, responseID)
	if err != nil {
		return nil, err
	}

	targetURL := fmt.Sprintf("%s/responses/%s", strings.TrimSuffix(provider.BaseURL, "/"), responseID)

	httpReq, err := http.NewRequestWithContext(ctx, "DELETE", targetURL, nil)
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Authorization", "Bearer "+provider.APIKey)

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, ErrUpstreamFailed
	}
	defer resp.Body.Close()

	if resp.StatusCode == 404 {
		return nil, ErrResponseNotFound
	}

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("upstream error: %d - %s", resp.StatusCode, string(body))
	}

	// Remove from cache on successful delete
	s.cache.Delete(responseID)

	var response models.DeleteResponse
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, err
	}

	return &response, nil
}

// CancelResponse handles POST /responses/:id/cancel - forwards to upstream provider
func (s *ResponseService) CancelResponse(ctx context.Context, apiKey *models.GatewayAPIKey, responseID string) (*models.CancelResponse, error) {
	provider, err := s.getProviderForResponse(ctx, responseID)
	if err != nil {
		return nil, err
	}

	targetURL := fmt.Sprintf("%s/responses/%s/cancel", strings.TrimSuffix(provider.BaseURL, "/"), responseID)

	httpReq, err := http.NewRequestWithContext(ctx, "POST", targetURL, nil)
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+provider.APIKey)

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, ErrUpstreamFailed
	}
	defer resp.Body.Close()

	if resp.StatusCode == 404 {
		return nil, ErrResponseNotFound
	}

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("upstream error: %d - %s", resp.StatusCode, string(body))
	}

	var response models.CancelResponse
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, err
	}

	return &response, nil
}

// getDefaultProvider returns a default provider for forwarding requests
func (s *ResponseService) getDefaultProvider(ctx context.Context) (*models.Provider, error) {
	// Get first available (non-disabled) provider with ProviderTypes preloaded
	providers, err := s.providerRepo.ListWithTypes(ctx, nil)
	if err != nil || len(providers) == 0 {
		return nil, errors.New("no available provider")
	}
	// Return first non-disabled provider
	for _, p := range providers {
		if !p.Disabled {
			return &p, nil
		}
	}
	return nil, errors.New("no available provider")
}

// CompactConversation handles POST /responses/compact
func (s *ResponseService) CompactConversation(ctx context.Context, apiKey *models.GatewayAPIKey, req *models.CompactRequest, requestHeaders http.Header) (*models.Response, error) {
	startTime := time.Now()

	// Extract headers for logging and forwarding
	forwardHeaders, headersJSON := extractForwardableHeaders(requestHeaders)

	// Determine model (can be optional for compact)
	if req.Model == "" {
		req.Model = "gpt-4o" // Default model
	}

	// 1. Find model
	model, err := s.findModel(ctx, req.Model)
	if err != nil {
		return nil, ErrModelNotFound
	}

	// 2. Select route
	route, err := s.selectRoute(ctx, model.ID)
	if err != nil {
		return nil, ErrNoRouteAvailable
	}

	// Create initial log entry at request start
	// Skip logging for virtual API keys (ID=0)
	logEntry := &models.Log{
		APIKeyID:       getAPIKeyIDPtr(apiKey.ID),
		ModelName:      model.Name,
		ProviderName:   route.Provider.Name,
		Status:         0, // pending
		RequestHeaders: headersJSON,
	}
	if apiKey.ID != 0 {
		if err := s.logRepo.Create(ctx, logEntry); err != nil {
			logEntry.ID = 0 // Continue without log if creation fails
		} else if apiKey.LogDetails {
			// Store request body immediately at request start
			reqBody, _ := json.Marshal(req)
			reqGz, _ := utils.GzipCompress(reqBody)
			detail := &models.LogDetail{
				LogID:       logEntry.ID,
				RequestBody: reqGz,
			}
			s.logDetailRepo.Create(ctx, detail)
		}
	} else {
		logEntry.ID = 0 // Virtual key, no logging
	}

	// 3. Check permission
	if err := s.checkPermission(ctx, apiKey, model.ID); err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 403, err.Error())
		return nil, err
	}

	// 4. Check balance
	if err := s.checkBalance(ctx, apiKey.UserID, model); err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 402, err.Error())
		return nil, err
	}

	// 5. Build upstream URL
	// Use type-specific base URL if available, fallback to default
	baseURL := route.Provider.GetBaseURLForType("openai")
	targetURL := fmt.Sprintf("%s/responses/compact", strings.TrimSuffix(baseURL, "/"))

	// 6. Send upstream request with forwarded headers
	resp, err := s.sendCompactUpstreamRequest(ctx, targetURL, route.Provider.APIKey, req, forwardHeaders)
	if err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 502, err.Error())
		return nil, ErrUpstreamFailed
	}

	if resp.StatusCode >= 400 {
		latency := time.Since(startTime).Milliseconds()
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		s.updateLogError(ctx, logEntry.ID, int(latency), resp.StatusCode, string(body))
		return nil, fmt.Errorf("upstream error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
		return nil, err
	}

	var response models.Response
	if err := json.Unmarshal(body, &response); err != nil {
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
		return nil, err
	}

	latency := time.Since(startTime).Milliseconds()
	respHeaders := extractResponseHeaders(resp.Header)
	s.updateLogAndCalculateCost(ctx, apiKey, model, route.Provider.Name, logEntry.ID, req, &response, int(latency), respHeaders)

	return &response, nil
}

// sendResponseUpstreamRequest sends request to upstream Responses API
func (s *ResponseService) sendResponseUpstreamRequest(ctx context.Context, url, apiKey string, req *models.ResponseRequest, stream bool, forwardHeaders map[string]string) (*http.Response, error) {
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

	// Forward additional headers
	for key, value := range forwardHeaders {
		httpReq.Header.Set(key, value)
	}

	return s.httpClient.Do(httpReq)
}

// sendCompactUpstreamRequest sends compact request to upstream
func (s *ResponseService) sendCompactUpstreamRequest(ctx context.Context, url, apiKey string, req *models.CompactRequest, forwardHeaders map[string]string) (*http.Response, error) {
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

	// Forward additional headers
	for key, value := range forwardHeaders {
		httpReq.Header.Set(key, value)
	}

	return s.httpClient.Do(httpReq)
}

// ================================== Helper Methods (Reuse from GatewayService) ==================================

// findModel finds a model by name or alias
func (s *ResponseService) findModel(ctx context.Context, name string) (*models.Model, error) {
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
func (s *ResponseService) selectRoute(ctx context.Context, modelID uint) (*models.ModelRoute, error) {
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
func (s *ResponseService) checkPermission(ctx context.Context, apiKey *models.GatewayAPIKey, modelID uint) error {
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
func (s *ResponseService) checkBalance(ctx context.Context, userID *uint, model *models.Model) error {
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

// handleUpstreamError handles upstream errors, including auto-disabling routes for 429
func (s *ResponseService) handleUpstreamError(ctx context.Context, resp *http.Response, route *models.ModelRoute) {
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

// logResponseAndCalculateCost logs the request and calculates cost
func (s *ResponseService) logResponseAndCalculateCost(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, req interface{}, resp *models.Response, latency int) {
	var promptTokens, completionTokens, totalTokens int
	if resp.Usage != nil {
		promptTokens = resp.Usage.InputTokens
		completionTokens = resp.Usage.OutputTokens
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
	// Skip logging for virtual API keys (ID=0)
	if apiKey.ID != 0 {
		logEntry := &models.Log{
			Latency:            latency,
			PromptTokens:       promptTokens,
			CompletionTokens:   completionTokens,
			TotalTokens:        totalTokens,
			Cost:               cost,
			APIKeyID:           getAPIKeyIDPtr(apiKey.ID),
			ModelName:          model.Name,
			ProviderName:       providerName,
			OwnerChannelID:     ownerChannelID,
			OwnerChannelUserID: ownerChannelUserID,
			Status:             200,
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
}

// logError logs an error request
func (s *ResponseService) logError(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, latency, status int, errMsg string, req interface{}) {
	// Skip logging for virtual API keys (ID=0)
	if apiKey.ID == 0 {
		return
	}

	logEntry := &models.Log{
		Latency:      latency,
		APIKeyID:     getAPIKeyIDPtr(apiKey.ID),
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

// updateLogAndCalculateCost updates an existing log entry with completion data and calculates cost
func (s *ResponseService) updateLogAndCalculateCost(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, logID uint, req interface{}, resp *models.Response, latency int, respHeaders map[string]string) {
	if logID == 0 {
		return
	}

	var promptTokens, completionTokens, totalTokens int
	if resp.Usage != nil {
		promptTokens = resp.Usage.InputTokens
		completionTokens = resp.Usage.OutputTokens
		totalTokens = resp.Usage.TotalTokens
	}

	cost := s.billingService.CalculateCost(promptTokens, completionTokens, model.InputTokenPrice, model.OutputTokenPrice)

	// Determine owner channel (for shared channels)
	ownerChannelID, ownerChannelUserID := s.determineChannelOwner(ctx, apiKey, model.ID)

	// Deduct cost
	if cost > 0 && apiKey.UserID != nil {
		s.billingService.DeductAndDistribute(ctx, apiKey.UserID, ownerChannelUserID, cost)
	}

	// Update log entry
	updates := map[string]interface{}{
		"latency":            latency,
		"promptTokens":      promptTokens,
		"completionTokens":  completionTokens,
		"totalTokens":       totalTokens,
		"cost":               cost,
		"status":             200,
		"ownerChannelId":   ownerChannelID,
		"ownerChannelUserId": ownerChannelUserID,
	}

	// Add response headers if available
	if len(respHeaders) > 0 {
		respHeadersJSON, _ := json.Marshal(respHeaders)
		updates["responseHeaders"] = string(respHeadersJSON)
	}

	s.logRepo.UpdateByID(ctx, logID, updates)

	if apiKey.LogDetails {
		// Update existing LogDetail with response body
		respBody, _ := json.Marshal(resp)
		respGz, _ := utils.GzipCompress(respBody)
		s.logDetailRepo.UpdateResponseBody(ctx, logID, respGz)
	}
}

// updateLogError updates an existing log entry with error information
func (s *ResponseService) updateLogError(ctx context.Context, logID uint, latency, status int, errMsg string) {
	if logID == 0 {
		return
	}

	updates := map[string]interface{}{
		"latency":       latency,
		"status":        status,
		"errorMessage": errMsg,
	}

	s.logRepo.UpdateByID(ctx, logID, updates)
}

// determineChannelOwner determines the channel owner for billing
func (s *ResponseService) determineChannelOwner(ctx context.Context, apiKey *models.GatewayAPIKey, modelID uint) (*uint, *uint) {
	// TODO: Implement channel owner determination logic
	return nil, nil
}

// ================================== Streaming Response ==================================

// ResponseStreamingResponse wraps an HTTP response for Responses API streaming with logging support
type ResponseStreamingResponse struct {
	ResponseBody   *http.Response
	capturedBuffer *bytes.Buffer
	reader         *bufio.Reader

	// For logging after streaming is complete
	ctx            context.Context // Store context to detect client disconnect
	logID          uint            // ID of the initial log entry
	apiKey         *models.GatewayAPIKey
	model          *models.Model
	providerName   string
	provider       *models.Provider
	request        *models.ResponseRequest
	startTime      time.Time
	logRepo        *repository.LogRepository
	logDetailRepo  *repository.LogDetailRepository
	billingService *BillingService
	cache          *ResponseCache
	responseHeaders map[string]string // Response headers for logging
}

// NewResponseStreamingResponse creates a new streaming response wrapper for Responses API
func NewResponseStreamingResponse(resp *http.Response) *ResponseStreamingResponse {
	return &ResponseStreamingResponse{
		ResponseBody:   resp,
		capturedBuffer: &bytes.Buffer{},
		reader:         bufio.NewReader(resp.Body),
	}
}

// Read implements io.Reader for streaming
func (s *ResponseStreamingResponse) Read(p []byte) (n int, err error) {
	n, err = s.reader.Read(p)
	if n > 0 {
		s.capturedBuffer.Write(p[:n])
	}
	return
}

// GetCapturedData returns the captured streaming data and parses it for Responses API format
func (s *ResponseStreamingResponse) GetCapturedData() (responseID string, content string, usage *models.ResponseUsage, rawData string) {
	rawData = s.capturedBuffer.String()

	// Parse Responses API SSE format: "event: xxx\ndata: {...}"
	scanner := bufio.NewScanner(strings.NewReader(rawData))
	var contentBuilder strings.Builder
	usage = &models.ResponseUsage{}

	var eventType string

	for scanner.Scan() {
		line := scanner.Text()

		// Skip empty lines
		if line == "" {
			eventType = "" // Reset event type after empty line
			continue
		}

		// Parse "event:" line
		if strings.HasPrefix(line, "event: ") {
			eventType = strings.TrimPrefix(line, "event: ")
			continue
		}

		// Parse "data:" line
		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		data := strings.TrimPrefix(line, "data: ")
		if data == "" {
			continue
		}

		// Parse based on event type
		switch eventType {
		case models.EventResponseCreated, models.EventResponseInProgress:
			// These events contain the response object with ID
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil && event.Response != nil {
				if event.Response.ID != "" {
					responseID = event.Response.ID
				}
			}
		case models.EventResponseOutputTextDelta:
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil {
				contentBuilder.WriteString(event.Delta)
			}
		case models.EventResponseCompleted:
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil && event.Response != nil {
				if event.Response.ID != "" {
					responseID = event.Response.ID
				}
				if event.Response.Usage != nil {
					usage = event.Response.Usage
				}
			}
		case models.EventResponseOutputTextDone:
			// Final text content - can be used to verify accumulated content
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil && event.Part != nil {
				// Part.Text contains the complete text for this part
			}
		}
	}

	content = contentBuilder.String()
	return
}

// LogAfterComplete updates the log entry after streaming is complete
func (s *ResponseStreamingResponse) LogAfterComplete(ctx context.Context) {
	if s.logRepo == nil || s.logID == 0 {
		return
	}

	// Determine status based on context cancellation (client disconnect)
	status := 200
	errMsg := ""
	if s.ctx != nil {
		select {
		case <-s.ctx.Done():
			status = 499 // Client closed request (Nginx convention)
			errMsg = "client disconnected"
		default:
		}
	}

	responseID, content, usage, _ := s.GetCapturedData()
	latency := time.Since(s.startTime).Milliseconds()

	// Cache response ID -> provider mapping
	if responseID != "" && s.provider != nil && s.cache != nil {
		s.cache.Set(responseID, s.provider, s.provider.GetBaseURLForType("openai"))
	}

	// Estimate completion tokens if not provided
	completionTokens := usage.OutputTokens
	if completionTokens == 0 && content != "" {
		// Rough estimate: ~4 characters per token
		completionTokens = len(content) / 4
	}

	// Calculate cost
	var cost int64
	if s.model != nil {
		cost = s.billingService.CalculateCost(
			usage.InputTokens,
			completionTokens,
			s.model.InputTokenPrice,
			s.model.OutputTokenPrice,
		)
	}

	// Deduct cost only if request was successful
	if cost > 0 && status == 200 && s.apiKey.UserID != nil {
		s.billingService.DeductAndDistribute(ctx, s.apiKey.UserID, nil, cost)
	}

	// Update log entry
	updates := map[string]interface{}{
		"latency":           int(latency),
		"promptTokens":     usage.InputTokens,
		"completionTokens": completionTokens,
		"totalTokens":      usage.InputTokens + completionTokens,
		"cost":              cost,
		"status":            status,
	}
	if errMsg != "" {
		updates["errorMessage"] = errMsg
	}
	if len(s.responseHeaders) > 0 {
		respHeadersJSON, _ := json.Marshal(s.responseHeaders)
		updates["responseHeaders"] = string(respHeadersJSON)
	}

	s.logRepo.UpdateByID(ctx, s.logID, updates)

	if s.apiKey.LogDetails {
		// Build response object for logging
		respObj := map[string]interface{}{
			"id":      responseID,
			"object":  "response",
			"created": time.Now().Unix(),
			"model":   s.model.Name,
			"status":  "completed",
			"output": []map[string]interface{}{
				{
					"type":   "message",
					"id":     "",
					"status": "completed",
					"role":   "assistant",
					"content": []map[string]interface{}{
						{
							"type":        "output_text",
							"text":        content,
							"annotations": []interface{}{},
						},
					},
				},
			},
			"usage": map[string]int{
				"input_tokens":  usage.InputTokens,
				"output_tokens": completionTokens,
				"total_tokens":  usage.InputTokens + completionTokens,
			},
		}
		respBody, _ := json.Marshal(respObj)
		respGz, _ := utils.GzipCompress(respBody)

		// Update existing LogDetail with response body
		s.logDetailRepo.UpdateResponseBody(ctx, s.logID, respGz)
	}
}

// Close closes the underlying response body and logs the request
func (s *ResponseStreamingResponse) Close() error {
	ctx := s.ctx
	if ctx == nil {
		ctx = context.Background()
	}
	s.LogAfterComplete(ctx)
	return s.ResponseBody.Body.Close()
}