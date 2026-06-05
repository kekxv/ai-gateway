package service

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
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
	if proxyConfig == nil {
		proxyConfig = &ProxyConfig{}
	}

	// Clone default transport to retain connection pooling, keep-alives and other optimizations
	var transport *http.Transport
	if defaultTrans, ok := http.DefaultTransport.(*http.Transport); ok {
		transport = defaultTrans.Clone()
	} else {
		transport = &http.Transport{}
	}

	// Set custom proxy bypass support
	transport.Proxy = func(req *http.Request) (*url.URL, error) {
		if utils.ShouldBypassProxy(req.URL.String(), proxyConfig.NoProxy) {
			return nil, nil // Bypass proxy for matched URLs
		}
		return http.ProxyFromEnvironment(req)
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
		httpClient:     &http.Client{Timeout: 0, Transport: transport}, // Disable hard request timeout for long LLM connections
		proxyConfig:    proxyConfig,
		cache:          NewResponseCache(24 * time.Hour), // 1 day TTL
	}
}

// CreateResponse handles POST /responses
// For streaming, returns (*ResponseStreamingResponse, error)
// For non-streaming, returns (*models.Response, error)
func (s *ResponseService) CreateResponse(ctx context.Context, apiKey *models.GatewayAPIKey, req *models.ResponseRequest, rawBody []byte, requestHeaders http.Header) (interface{}, error) {
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

	// Extract prompt for logging
	prompt := ""
	if req.Input.StringInput != "" {
		prompt = req.Input.StringInput
	} else if len(req.Input.Items) > 0 {
		// Find last user message or first message
		lastMsg := ""
		for i := len(req.Input.Items) - 1; i >= 0; i-- {
			item := req.Input.Items[i]
			if item.Type == "message" && item.Role == "user" {
				if item.Content.StringContent != "" {
					lastMsg = item.Content.StringContent
				} else if len(item.Content.Parts) > 0 {
					for _, p := range item.Content.Parts {
						if p.Type == "input_text" {
							lastMsg = p.Text
							break
						}
					}
				}
				if lastMsg != "" {
					break
				}
			}
		}
		if lastMsg == "" && len(req.Input.Items) > 0 {
			// Fallback to first item
			item := req.Input.Items[0]
			if item.Content.StringContent != "" {
				lastMsg = item.Content.StringContent
			}
		}
		prompt = lastMsg
	}

	// Create initial log entry at request start
	// Skip logging for virtual API keys (ID=0)
	logEntry := &models.Log{
		APIKeyID:       getAPIKeyIDPtr(apiKey.ID),
		ModelName:      model.Name,
		ProviderName:   route.Provider.Name,
		Status:         0, // pending
		RequestHeaders: headersJSON,
		Prompt:         prompt,
	}
	if apiKey.ID != 0 {
		if err := s.logRepo.Create(ctx, logEntry); err != nil {
			logEntry.ID = 0 // Continue without log if creation fails
		} else if apiKey.LogDetails {
			// Store original request body immediately at request start
			reqGz, _ := utils.GzipCompress(rawBody)
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

	providerType := "openai"
	if route.Provider.HasType("gemini") && !route.Provider.HasType("openai") {
		providerType = "gemini"
	} else if route.Provider.HasType("openai") && !route.Provider.HasType("responses") {
		providerType = "chat_completions"
	}

	// Map special headers based on protocol type
	headerProtocol := providerType
	if headerProtocol == "chat_completions" {
		headerProtocol = "openai"
	}
	MapHeaders(forwardHeaders, headerProtocol)

	var resp *http.Response
	var reqErr error
	baseURL := ""
	switch providerType {
	case "gemini":
		resp, reqErr = s.sendGeminiResponseRequest(ctx, &route.Provider, model.Name, req, forwardHeaders)
	case "chat_completions":
		baseURL = route.Provider.GetBaseURLForType("openai")
		resp, reqErr = s.sendChatCompletionsResponseRequest(ctx, &route.Provider, model.Name, req, forwardHeaders)
	default: // "openai" - native Responses API passthrough
		baseURL = route.Provider.GetBaseURLForType("openai")
		targetURL := fmt.Sprintf("%s/responses", strings.TrimSuffix(baseURL, "/"))

		upstreamModelName := route.Model.Name
		finalRawBody := rawBody
		if upstreamModelName != req.Model {
			finalRawBody, reqErr = replaceRawModel(rawBody, upstreamModelName)
			if reqErr != nil {
				log.Printf("[ResponseService] Replace raw model failed: %v", reqErr)
				return nil, reqErr
			}
		}

		resp, reqErr = s.sendResponseUpstreamRequest(ctx, targetURL, route.Provider.APIKey, finalRawBody, req.Stream, forwardHeaders)
	}
	if reqErr != nil {
		log.Printf("[ResponseService] Upstream request failed: providerType=%s, baseURL=%s, err=%v", providerType, baseURL, reqErr)
		s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 502, reqErr.Error())
		return nil, ErrUpstreamFailed
	}

	// Handle error responses
	if resp.StatusCode >= 400 {
		latency := time.Since(startTime).Milliseconds()
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		log.Printf("[ResponseService] Upstream HTTP error: providerType=%s, status=%d, body=%s", providerType, resp.StatusCode, string(body))
		s.handleUpstreamError(ctx, resp, route)
		s.updateLogError(ctx, logEntry.ID, int(latency), resp.StatusCode, string(body))
		return nil, &UpstreamError{StatusCode: resp.StatusCode, Body: body}
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
		streamResp.providerType = providerType
		streamResp.responseID = "resp_" + shortUUID()
		if providerType == "gemini" {
			streamResp.isGeminiStream = true
		} else if providerType == "chat_completions" {
			streamResp.isChatCompletionsStream = true
		}
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
	if providerType == "gemini" {
		var geminiResp models.GeminiGenerateContentResponse
		if err := json.Unmarshal(body, &geminiResp); err != nil {
			s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
			return nil, err
		}
		response = *convertGeminiResponseToOpenAIResponse(&geminiResp, model.Name)
	} else if providerType == "chat_completions" {
		var chatResp ChatResponse
		if err := json.Unmarshal(body, &chatResp); err != nil {
			s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
			return nil, err
		}
		response = *convertChatResponseToResponse(&chatResp, model.Name, req.PreviousResponseID, req.Metadata)
	} else {
		if err := json.Unmarshal(body, &response); err != nil {
			s.updateLogError(ctx, logEntry.ID, int(time.Since(startTime).Milliseconds()), 500, err.Error())
			return nil, err
		}
	}

	// Cache response ID -> provider mapping for later operations
	if providerType == "openai" && response.ID != "" {
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
		return nil, &UpstreamError{StatusCode: resp.StatusCode, Body: body}
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
		return nil, &UpstreamError{StatusCode: resp.StatusCode, Body: body}
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
		return nil, &UpstreamError{StatusCode: resp.StatusCode, Body: body}
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
func (s *ResponseService) CompactConversation(ctx context.Context, apiKey *models.GatewayAPIKey, req *models.CompactRequest, rawBody []byte, requestHeaders http.Header) (*models.Response, error) {
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
			// Store original request body immediately at request start
			reqGz, _ := utils.GzipCompress(rawBody)
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

	// Map special headers to OpenAI protocol format
	MapHeaders(forwardHeaders, "openai")

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
		return nil, &UpstreamError{StatusCode: resp.StatusCode, Body: body}
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
func (s *ResponseService) sendResponseUpstreamRequest(ctx context.Context, url, apiKey string, req interface{}, stream bool, forwardHeaders map[string]string) (*http.Response, error) {
	var body []byte
	var err error

	if b, ok := req.([]byte); ok {
		body = b
	} else {
		body, err = json.Marshal(req)
		if err != nil {
			return nil, err
		}
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

// sendChatCompletionsResponseRequest sends a Responses API request via Chat Completions translation
func (s *ResponseService) sendChatCompletionsResponseRequest(ctx context.Context, provider *models.Provider, modelName string, req *models.ResponseRequest, forwardHeaders map[string]string) (*http.Response, error) {
	chatReq := convertResponseRequestToChatRequest(req)

	// Replace alias with actual upstream model name
	chatReq.Model = modelName

	// Set default max_tokens
	if chatReq.MaxTokens == 0 {
		chatReq.MaxTokens = 16384
	}

	// For streaming, request usage info from upstream
	if req.Stream {
		chatReq.Extra["stream_options"] = map[string]interface{}{"include_usage": true}
	}

	baseURL := strings.TrimSuffix(provider.GetBaseURLForType("openai"), "/")
	targetURL := fmt.Sprintf("%s/chat/completions", baseURL)

	body, err := json.Marshal(chatReq)
	if err != nil {
		return nil, err
	}

	// Build tool summary for debugging
	toolSummary := make([]string, len(chatReq.Tools))
	for i, t := range chatReq.Tools {
		toolSummary[i] = fmt.Sprintf("%s(%s)", t.Function.Name, t.Type)
	}

	// Build truncated body summary for logging (avoid megabyte-sized log entries)
	bodyLog := string(body)
	if len(bodyLog) > 500 {
		// Replace message content with placeholders for logging
		truncated := fmt.Sprintf("body=%s, tools=[%s], model=%s, messages=%d", bodyLog[:100], strings.Join(toolSummary, ", "), chatReq.Model, len(chatReq.Messages))
		log.Printf("[ResponseService] chat_completions upstream: url=%s, %s", targetURL, truncated)
	} else {
		log.Printf("[ResponseService] chat_completions upstream: url=%s, model=%s, messages=%d, tools=[%s], tool_choice=%v, body=%s", targetURL, chatReq.Model, len(chatReq.Messages), strings.Join(toolSummary, ", "), chatReq.Extra["tool_choice"], string(body))
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", targetURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+provider.APIKey)
	for key, value := range forwardHeaders {
		httpReq.Header.Set(key, value)
	}

	return s.httpClient.Do(httpReq)
}

func (s *ResponseService) sendGeminiResponseRequest(ctx context.Context, provider *models.Provider, modelName string, req *models.ResponseRequest, forwardHeaders map[string]string) (*http.Response, error) {
	chatReq := convertResponseRequestToChatRequest(req)
	converter := NewProtocolConverter()
	geminiReqRaw, err := converter.ConvertRequest(chatReq, ProtocolOpenAI, ProtocolGemini)
	if err != nil {
		return nil, err
	}
	geminiReq := geminiReqRaw.(*models.GeminiGenerateContentRequest)

	baseURL := strings.TrimSuffix(provider.GetBaseURLForType("gemini"), "/")
	if !strings.HasSuffix(baseURL, "/v1") && !strings.HasSuffix(baseURL, "/v1beta") {
		baseURL += "/v1beta"
	}

	action := "generateContent"
	if req.Stream {
		action = "streamGenerateContent"
	}

	targetURL := fmt.Sprintf("%s/models/%s:%s", baseURL, modelName, action)
	if req.Stream {
		targetURL += "?alt=sse"
	}

	body, err := json.Marshal(geminiReq)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", targetURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-goog-api-key", provider.APIKey)
	for key, value := range forwardHeaders {
		httpReq.Header.Set(key, value)
	}

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, err
	}

	if shouldRetryGeminiWithoutThinking(req.Stream, resp, geminiReq) {
		respBody, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		httpReqRetryBody, err := json.Marshal(cloneGeminiRequestWithoutThinking(geminiReq))
		if err != nil {
			return nil, err
		}

		retryReq, err := http.NewRequestWithContext(ctx, "POST", targetURL, bytes.NewReader(httpReqRetryBody))
		if err != nil {
			return nil, err
		}

		retryReq.Header.Set("Content-Type", "application/json")
		retryReq.Header.Set("x-goog-api-key", provider.APIKey)
		for key, value := range forwardHeaders {
			retryReq.Header.Set(key, value)
		}

		_ = respBody
		return s.httpClient.Do(retryReq)
	}

	return resp, nil
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
		channel, err := s.channelRepo.FindByID(ctx, channelID)
		if err != nil {
			continue
		}

		// If channel supports all models, check if model has routes to channel's providers
		if channel.SupportsAllModels {
			// Get channel's providers
			providerBindings, err := s.channelRepo.GetProviders(ctx, channelID)
			if err != nil {
				continue
			}
			providerIDs := make([]uint, len(providerBindings))
			for i, pb := range providerBindings {
				providerIDs[i] = pb.ProviderID
			}

			// Check if model has routes to any of these providers
			if len(providerIDs) > 0 {
				routes, err := s.modelRouteRepo.FindByModelAndProviders(ctx, modelID, providerIDs)
				if err == nil && len(routes) > 0 {
					return nil
				}
			}
		} else {
			// Check ChannelAllowedModel table
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

	// Extract completion for logging
	completion := ""
	if len(resp.Output) > 0 {
		output := resp.Output[len(resp.Output)-1]
		if output.Type == "message" {
			for _, content := range output.Content {
				if content.Type == "output_text" {
					completion = content.Text
					break
				}
			}
		}
	}

	// Update log entry
	updates := map[string]interface{}{
		"latency":            latency,
		"promptTokens":       promptTokens,
		"completionTokens":   completionTokens,
		"totalTokens":        totalTokens,
		"cost":               cost,
		"status":             200,
		"ownerChannelId":     ownerChannelID,
		"ownerChannelUserId": ownerChannelUserID,
		"completion":         completion,
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
		"latency":      latency,
		"status":       status,
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
	pipeBuffer     *bytes.Buffer
	geminiScanner  *bufio.Scanner

	// For logging after streaming is complete
	ctx                     context.Context // Store context to detect client disconnect
	logID                   uint            // ID of the initial log entry
	apiKey                  *models.GatewayAPIKey
	model                   *models.Model
	providerName            string
	provider                *models.Provider
	request                 *models.ResponseRequest
	startTime               time.Time
	logRepo                 *repository.LogRepository
	logDetailRepo           *repository.LogDetailRepository
	billingService          *BillingService
	cache                   *ResponseCache
	responseHeaders         map[string]string // Response headers for logging
	providerType            string
	isGeminiStream          bool
	isChatCompletionsStream bool
	responseID              string
	streamState             *responseStreamState
	chatStreamState         *chatToResponseStreamState
}

// NewResponseStreamingResponse creates a new streaming response wrapper for Responses API
func NewResponseStreamingResponse(resp *http.Response) *ResponseStreamingResponse {
	return &ResponseStreamingResponse{
		ResponseBody:   resp,
		capturedBuffer: &bytes.Buffer{},
		reader:         bufio.NewReader(resp.Body),
		pipeBuffer:     &bytes.Buffer{},
		streamState:    &responseStreamState{},
	}
}

// Read implements io.Reader for streaming
func (s *ResponseStreamingResponse) Read(p []byte) (n int, err error) {
	// Check if context is cancelled (client disconnected)
	if s.ctx != nil {
		select {
		case <-s.ctx.Done():
			// Context cancelled, close response body and return error
			s.ResponseBody.Body.Close()
			return 0, s.ctx.Err()
		default:
		}
	}

	if s.isGeminiStream {
		if s.geminiScanner == nil {
			s.geminiScanner = bufio.NewScanner(s.ResponseBody.Body)
			s.geminiScanner.Split(GeminiStreamSplitter)
		}

		if s.pipeBuffer.Len() > 0 {
			return s.pipeBuffer.Read(p)
		}

		if s.geminiScanner.Scan() {
			data := s.geminiScanner.Bytes()
			if len(data) > 0 {
				var chunk models.GeminiGenerateContentResponse
				if err := json.Unmarshal(data, &chunk); err == nil {
					converted := convertGeminiChunkToResponseSSE(&chunk, s.responseID, s.model.Name, s.streamState)
					if converted != "" {
						s.pipeBuffer.WriteString(converted)
						s.capturedBuffer.WriteString(converted)
						return s.pipeBuffer.Read(p)
					}
				}
			}
			return s.Read(p)
		}

		if err := s.geminiScanner.Err(); err != nil {
			return 0, err
		}

		if !s.streamState.completed {
			s.streamState.completed = true
			completed := buildResponseCompletedSSE(s.responseID, s.model.Name, s.streamState.usage)
			s.pipeBuffer.WriteString(completed)
			s.capturedBuffer.WriteString(completed)
			return s.pipeBuffer.Read(p)
		}

		return 0, io.EOF
	}

	if s.isChatCompletionsStream {
		return s.readChatCompletionsStream(p)
	}

	n, err = s.reader.Read(p)
	if n > 0 {
		s.capturedBuffer.Write(p[:n])
	}
	return
}

// readChatCompletionsStream parses upstream Chat Completions SSE and emits Responses API SSE events
func (s *ResponseStreamingResponse) readChatCompletionsStream(p []byte) (n int, err error) {
	if s.pipeBuffer.Len() > 0 {
		return s.pipeBuffer.Read(p)
	}

	if s.chatStreamState == nil {
		s.chatStreamState = &chatToResponseStreamState{
			toolCalls:     make(map[int]*streamingToolCall),
			completedSent: false,
		}
	}

	line, readErr := s.reader.ReadString('\n')
	if readErr != nil && line == "" {
		if readErr == io.EOF {
			if !s.chatStreamState.completedSent {
				s.chatStreamState.completed = true
				s.chatStreamState.completedSent = true
				completed := s.buildChatCompletionsCompletedSSE()
				if completed != "" {
					s.pipeBuffer.WriteString(completed)
					s.capturedBuffer.WriteString(completed)
					return s.pipeBuffer.Read(p)
				}
			}
			return 0, io.EOF
		}
		return 0, readErr
	}

	line = strings.TrimSpace(line)
	if line == "" {
		if readErr != nil && readErr != io.EOF {
			return 0, readErr
		}
		return s.readChatCompletionsStream(p)
	}

	if !strings.HasPrefix(line, "data: ") {
		if readErr == io.EOF && !s.chatStreamState.completedSent {
			s.chatStreamState.completed = true
			s.chatStreamState.completedSent = true
			completed := s.buildChatCompletionsCompletedSSE()
			if completed != "" {
				s.pipeBuffer.WriteString(completed)
				s.capturedBuffer.WriteString(completed)
				return s.pipeBuffer.Read(p)
			}
			return 0, io.EOF
		}
		if readErr != nil {
			return 0, readErr
		}
		return s.readChatCompletionsStream(p)
	}

	data := strings.TrimPrefix(line, "data: ")
	if data == "[DONE]" {
		if !s.chatStreamState.completedSent {
			s.chatStreamState.completed = true
			s.chatStreamState.completedSent = true
			completed := s.buildChatCompletionsCompletedSSE()
			if completed != "" {
				s.pipeBuffer.WriteString(completed)
				s.capturedBuffer.WriteString(completed)
				return s.pipeBuffer.Read(p)
			}
		}
		return 0, io.EOF
	}

	var chunk StreamChunk
	if err := json.Unmarshal([]byte(data), &chunk); err != nil {
		return s.readChatCompletionsStream(p)
	}

	events := s.convertChatChunkToResponseSSE(&chunk)
	if events == "" {
		return s.readChatCompletionsStream(p)
	}

	s.pipeBuffer.WriteString(events)
	s.capturedBuffer.WriteString(events)
	return s.pipeBuffer.Read(p)
}

// chatToResponseStreamState tracks state during Chat Completions -> Responses API stream conversion
type chatToResponseStreamState struct {
	createdSent     bool
	completedSent   bool // tracks whether response.completed SSE was sent
	textStarted     bool
	textOutputID    string
	fullText        strings.Builder
	reasoningBuf    strings.Builder
	toolCalls       map[int]*streamingToolCall // chunk delta index -> tool call state
	nextOutputIndex int                        // running counter for output_index in SSE events
	usage           *models.ResponseUsage
	completed       bool // tracks if finish_reason has been received
	finishReason    string
}

type streamingToolCall struct {
	callID    string
	outputID  string
	name      string
	arguments strings.Builder
}

func (s *ResponseStreamingResponse) convertChatChunkToResponseSSE(chunk *StreamChunk) string {
	var result strings.Builder
	state := s.chatStreamState

	// Extract usage from any chunk (some providers send it in usage-only chunk, others in final chunk)
	if chunk.Usage != nil && state.usage == nil {
		state.usage = &models.ResponseUsage{
			InputTokens:  chunk.Usage.PromptTokens,
			OutputTokens: chunk.Usage.CompletionTokens,
			TotalTokens:  chunk.Usage.TotalTokens,
		}
	}

	if len(chunk.Choices) == 0 {
		return ""
	}

	delta := chunk.Choices[0].Delta
	finishReason := chunk.Choices[0].FinishReason

	// Send response.created on first chunk
	if !state.createdSent {
		state.createdSent = true
		result.WriteString(formatResponseSSE(models.EventResponseCreated, models.ResponseStreamEvent{
			Type: models.EventResponseCreated,
			Response: &models.Response{
				ID: s.responseID, Object: "response", CreatedAt: time.Now().Unix(),
				Status: "in_progress", Model: s.model.Name,
			},
		}))
		result.WriteString(formatResponseSSE(models.EventResponseInProgress, models.ResponseStreamEvent{
			Type: models.EventResponseInProgress,
			Response: &models.Response{
				ID: s.responseID, Object: "response", CreatedAt: time.Now().Unix(),
				Status: "in_progress", Model: s.model.Name,
			},
		}))
	}

	// Handle tool calls — use running output_index counter
	for _, tc := range delta.ToolCalls {
		existing, exists := state.toolCalls[tc.Index]
		if !exists {
			// New tool call
			outputID := "fc_" + shortUUID()[:16]
			callID := tc.ID
			state.toolCalls[tc.Index] = &streamingToolCall{
				callID:   callID,
				outputID: outputID,
				name:     tc.Function.Name,
			}
			idx := state.nextOutputIndex
			state.nextOutputIndex++
			result.WriteString(formatResponseSSE(models.EventResponseOutputItemAdded, models.ResponseStreamEvent{
				Type: models.EventResponseOutputItemAdded, ItemID: s.responseID, OutputIndex: idx,
				Item: &models.ResponseOutput{Type: "function_call", ID: outputID, CallID: callID, Name: tc.Function.Name, Arguments: tc.Function.Arguments, Status: "in_progress"},
			}))
			if tc.Function.Arguments != "" {
				result.WriteString(formatResponseSSE("response.function_call_arguments.delta", models.ResponseStreamEvent{
					Type: "response.function_call_arguments.delta", ItemID: s.responseID, OutputIndex: idx, Delta: tc.Function.Arguments,
				}))
			}
		} else {
			// Existing tool call — accumulate arguments
			if tc.Function.Arguments != "" {
				existing.arguments.WriteString(tc.Function.Arguments)
				result.WriteString(formatResponseSSE("response.function_call_arguments.delta", models.ResponseStreamEvent{
					Type: "response.function_call_arguments.delta", ItemID: s.responseID, Delta: tc.Function.Arguments,
				}))
			}
		}
	}

	// Handle reasoning (capture but don't forward)
	reasoning := delta.Reasoning
	if reasoning == "" {
		reasoning = delta.ReasoningContent
	}
	if reasoning != "" {
		state.reasoningBuf.WriteString(reasoning)
	}

	// Handle text content
	if delta.Content != "" {
		if !state.textStarted {
			state.textStarted = true
			state.textOutputID = "msg_" + shortUUID()[:16]
			idx := state.nextOutputIndex
			state.nextOutputIndex++
			result.WriteString(formatResponseSSE(models.EventResponseOutputItemAdded, models.ResponseStreamEvent{
				Type: models.EventResponseOutputItemAdded, ItemID: s.responseID, OutputIndex: idx,
				Item: &models.ResponseOutput{Type: "message", ID: state.textOutputID, Status: "in_progress", Role: "assistant"},
			}))
			result.WriteString(formatResponseSSE(models.EventResponseContentPartAdded, models.ResponseStreamEvent{
				Type: models.EventResponseContentPartAdded, ItemID: s.responseID, OutputIndex: idx, ContentIndex: 0,
				Part: &models.OutputContent{Type: "output_text"},
			}))
		}
		state.fullText.WriteString(delta.Content)
		result.WriteString(formatResponseSSE(models.EventResponseOutputTextDelta, models.ResponseStreamEvent{
			Type: models.EventResponseOutputTextDelta, ItemID: s.responseID, Delta: delta.Content,
		}))
	}

	// Handle finish reason — mark state, but DON'T emit done events here.
	// Done events + response.completed are emitted by buildChatCompletionsCompletedSSE on [DONE]/EOF.
	if finishReason != nil && *finishReason != "" && !state.completed {
		state.completed = true
		state.finishReason = *finishReason
	}

	return result.String()
}

func (s *ResponseStreamingResponse) buildChatCompletionsCompletedSSE() string {
	state := s.chatStreamState

	var result strings.Builder

	// Close text item if started
	text := state.fullText.String()
	text = thinkTagRegex.ReplaceAllString(text, "")
	if state.textStarted {
		result.WriteString(formatResponseSSE(models.EventResponseOutputTextDone, models.ResponseStreamEvent{
			Type: models.EventResponseOutputTextDone, ItemID: s.responseID,
			Part: &models.OutputContent{Type: "output_text", Text: text},
		}))
		result.WriteString(formatResponseSSE(models.EventResponseContentPartDone, models.ResponseStreamEvent{
			Type: models.EventResponseContentPartDone, ItemID: s.responseID, ContentIndex: 0,
			Part: &models.OutputContent{Type: "output_text", Text: text},
		}))
		result.WriteString(formatResponseSSE(models.EventResponseOutputItemDone, models.ResponseStreamEvent{
			Type: models.EventResponseOutputItemDone, ItemID: s.responseID,
			Item: &models.ResponseOutput{Type: "message", ID: state.textOutputID, Status: "completed", Role: "assistant",
				Content: []models.OutputContent{{Type: "output_text", Text: text}}},
		}))
	}

	// Close function call items
	for _, tc := range state.toolCalls {
		args := tc.arguments.String()
		result.WriteString(formatResponseSSE("response.function_call_arguments.done", models.ResponseStreamEvent{
			Type: "response.function_call_arguments.done", ItemID: s.responseID, Delta: args,
		}))
		result.WriteString(formatResponseSSE(models.EventResponseOutputItemDone, models.ResponseStreamEvent{
			Type: models.EventResponseOutputItemDone, ItemID: s.responseID,
			Item: &models.ResponseOutput{Type: "function_call", ID: tc.outputID, CallID: tc.callID, Name: tc.name, Arguments: args, Status: "completed"},
		}))
	}

	// Build output items for response.completed
	output := make([]models.ResponseOutput, 0)
	if text != "" {
		output = append(output, models.ResponseOutput{
			Type: "message", ID: state.textOutputID, Status: "completed", Role: "assistant",
			Content: []models.OutputContent{{Type: "output_text", Text: text}},
		})
	}
	for _, tc := range state.toolCalls {
		output = append(output, models.ResponseOutput{
			Type: "function_call", ID: tc.outputID, CallID: tc.callID, Name: tc.name,
			Arguments: tc.arguments.String(), Status: "completed",
		})
	}

	// Map finish reason
	status := "completed"
	if state.finishReason == "length" {
		status = "incomplete"
	}

	completedAt := time.Now().Unix()
	resp := &models.Response{
		ID: s.responseID, Object: "response", CreatedAt: completedAt, CompletedAt: &completedAt,
		Status: status, Model: s.model.Name, Output: output, Usage: state.usage,
	}

	result.WriteString(formatResponseSSE(models.EventResponseCompleted, models.ResponseStreamEvent{
		Type: models.EventResponseCompleted, Response: resp,
	}))
	return result.String()
}

// GetCapturedData returns the captured streaming data and parses it for Responses API format
func (s *ResponseStreamingResponse) GetCapturedData() (responseID string, content string, usage *models.ResponseUsage, items []models.ResponseOutput, rawData string) {
	rawData = s.capturedBuffer.String()

	// Parse Responses API SSE format: "event: xxx\ndata: {...}"
	scanner := bufio.NewScanner(strings.NewReader(rawData))
	var contentBuilder strings.Builder
	usage = &models.ResponseUsage{}

	var eventType string
	var outputItems []models.ResponseOutput
	var textOutputID string
	var textOutput *models.ResponseOutput

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
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil && event.Response != nil {
				if event.Response.ID != "" {
					responseID = event.Response.ID
				}
			}
		case models.EventResponseOutputItemAdded:
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil && event.Item != nil {
				outputItems = append(outputItems, *event.Item)
				if event.Item.Type == "message" {
					textOutputID = event.Item.ID
					textOutput = &models.ResponseOutput{}
					*textOutput = outputItems[len(outputItems)-1]
				}
			}
		case models.EventResponseOutputTextDelta:
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil {
				contentBuilder.WriteString(event.Delta)
			}
		case models.EventResponseOutputTextDone:
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil && event.Part != nil {
				// Update text output item with final content
				if textOutput != nil && textOutputID != "" {
					textOutput.Content = []models.OutputContent{
						{Type: "output_text", Text: event.Part.Text},
					}
					// Update in outputItems
					for i, item := range outputItems {
						if item.Type == "message" && item.ID == textOutputID {
							outputItems[i] = *textOutput
							break
						}
					}
				}
			}
		case "response.function_call_arguments.delta":
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil {
				// Update function_call item with accumulated arguments
				for i, item := range outputItems {
					if item.Type == "function_call" && item.CallID == event.ItemID {
						outputItems[i].Arguments += event.Delta
						break
					}
				}
			}
		case "response.function_call_arguments.done":
			var event models.ResponseStreamEvent
			if err := json.Unmarshal([]byte(data), &event); err == nil {
				// Update function_call item with final arguments
				for i, item := range outputItems {
					if item.Type == "function_call" && item.CallID == event.ItemID {
						outputItems[i].Arguments = event.Delta
						break
					}
				}
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
				// If the completed response has output items, use those
				if len(event.Response.Output) > 0 {
					outputItems = event.Response.Output
				}
			}
		}
	}

	content = contentBuilder.String()
	return responseID, content, usage, outputItems, rawData
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

	responseID, content, usage, _, _ := s.GetCapturedData()
	latency := time.Since(s.startTime).Milliseconds()

	// Cache response ID -> provider mapping
	if s.providerType == "openai" && responseID != "" && s.provider != nil && s.cache != nil {
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
		"latency":          int(latency),
		"promptTokens":     usage.InputTokens,
		"completionTokens": completionTokens,
		"totalTokens":      usage.InputTokens + completionTokens,
		"cost":             cost,
		"status":           status,
		"completion":       content,
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
		// Store raw captured streaming data (actual SSE sent to client)
		rawData := s.capturedBuffer.Bytes()
		respGz, _ := utils.GzipCompress(rawData)

		// Update existing LogDetail with response body
		s.logDetailRepo.UpdateResponseBody(ctx, s.logID, respGz)
	}
}

// Close closes the underlying response body and logs the request
func (s *ResponseStreamingResponse) Close() error {
	// Use background context for final logging to ensure it completes even if request is cancelled
	ctx := context.Background()
	s.LogAfterComplete(ctx)
	return s.ResponseBody.Body.Close()
}
