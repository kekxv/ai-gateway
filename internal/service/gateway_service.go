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
	"math/rand"
	"net/http"
	"net/url"
	"strings"
	"sync"
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

// Headers that should NOT be forwarded to upstream
var excludedHeaders = []string{
	"authorization",
	"cookie",
	"host",
	"content-length",
	"content-type", // We set our own
	"x-real-ip",
	"x-forwarded-proto",
	"x-forwarded-host",
	"x-forwarded-for",
	"te",
	"trailer",
	"upgrade",
	"proxy-authorization",
	"proxy-authenticate",
	"proxy-connection",
}

// extractForwardableHeaders extracts headers that should be forwarded to upstream
// and returns them as a map for forwarding and a JSON string for logging
func extractForwardableHeaders(header http.Header) (map[string]string, string) {
	result := make(map[string]string)

	for key, values := range header {
		keyLower := strings.ToLower(key)
		// Skip excluded headers
		skip := false
		for _, excluded := range excludedHeaders {
			if keyLower == excluded {
				skip = true
				break
			}
		}
		if skip {
			continue
		}
		// Take first value
		if len(values) > 0 {
			result[key] = values[0]
		}
	}

	// Convert to JSON for logging
	headersJSON, _ := json.Marshal(result)
	return result, string(headersJSON)
}

// getAPIKeyIDPtr returns a pointer to the API key ID, or nil if ID is 0
func getAPIKeyIDPtr(id uint) *uint {
	if id == 0 {
		return nil
	}
	return &id
}

// extractResponseHeaders extracts relevant headers from upstream response
func extractResponseHeaders(header http.Header) map[string]string {
	result := make(map[string]string)
	// Headers to capture from upstream response
	captureHeaders := []string{
		"Content-Type",
		"X-Request-Id",
		"X-RateLimit-Limit",
		"X-RateLimit-Remaining",
		"X-RateLimit-Reset",
		"Openai-Model",
		"Openai-Organization",
		"Openai-Version",
		"Openai-Processing-Ms",
	}

	for _, key := range captureHeaders {
		if value := header.Get(key); value != "" {
			result[key] = value
		}
	}
	return result
}

type ChatRequest struct {
	Model       string                 `json:"model"`
	Messages    []ChatMessage          `json:"messages"`
	Stream      bool                   `json:"stream,omitempty"`
	Temperature float64                `json:"temperature,omitempty"`
	MaxTokens   int                    `json:"max_tokens,omitempty"`
	Tools       []ToolDefinition       `json:"tools,omitempty"`
	Extra       map[string]interface{} `json:"-"` // Additional fields
}

// ToolDefinition represents a tool for function calling
type ToolDefinition struct {
	Type     string           `json:"type"` // "function"
	Function ToolFunctionSpec `json:"function"`
}

// ToolFunctionSpec represents the function specification
type ToolFunctionSpec struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	Parameters  map[string]interface{} `json:"parameters,omitempty"` // JSON Schema
}

// ChatMessageContent can be string or array of content parts (for multimodal)
type ChatMessageContent struct {
	StringContent string
	Parts         []ChatContentPart
}

// ChatContentPart represents a part of multimodal content
type ChatContentPart struct {
	Type     string            `json:"type"` // "text", "image_url", "video_url"
	Text     string            `json:"text,omitempty"`
	ImageURL *ChatMediaURL     `json:"image_url,omitempty"`
	VideoURL *ChatMediaURL     `json:"video_url,omitempty"` // Extended for video support
}

// ChatMediaURL represents a media URL or base64 data
type ChatMediaURL struct {
	URL    string `json:"url"`
	Detail string `json:"detail,omitempty"` // "auto", "low", "high" (for images)
}

// ChatImageURL is an alias for backward compatibility
type ChatImageURL = ChatMediaURL

// UnmarshalJSON handles both string and array formats for content
func (c *ChatMessageContent) UnmarshalJSON(data []byte) error {
	// Try string first
	var str string
	if err := json.Unmarshal(data, &str); err == nil {
		c.StringContent = str
		return nil
	}
	// Try array
	var parts []ChatContentPart
	if err := json.Unmarshal(data, &parts); err != nil {
		return err
	}
	c.Parts = parts
	return nil
}

// MarshalJSON handles both string and array formats for content
func (c ChatMessageContent) MarshalJSON() ([]byte, error) {
	if c.StringContent != "" && len(c.Parts) == 0 {
		return json.Marshal(c.StringContent)
	}
	if len(c.Parts) > 0 {
		return json.Marshal(c.Parts)
	}
	return json.Marshal("")
}

// GetText extracts text content
func (c ChatMessageContent) GetText() string {
	if c.StringContent != "" {
		return c.StringContent
	}
	for _, part := range c.Parts {
		if part.Type == "text" {
			return part.Text
		}
	}
	return ""
}

// HasImage checks if content contains image
func (c ChatMessageContent) HasImage() bool {
	for _, part := range c.Parts {
		if part.Type == "image_url" {
			return true
		}
	}
	return false
}

type ChatMessage struct {
	Role      string             `json:"role"`
	Content   ChatMessageContent `json:"content"`
	ToolCalls []ToolCall         `json:"tool_calls,omitempty"`
}

// ToolCall represents a tool/function call
type ToolCall struct {
	Index    int        `json:"index,omitempty"`
	ID       string     `json:"id,omitempty"`
	Type     string     `json:"type"`
	Function FunctionCall `json:"function"`
}

// FunctionCall represents a function call
type FunctionCall struct {
	Name      string `json:"name,omitempty"`
	Arguments string `json:"arguments,omitempty"`
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
			Role      string     `json:"role,omitempty"`
			Content   string     `json:"content,omitempty"`
			Reasoning string     `json:"reasoning,omitempty"` // For Ollama/Gemma thinking
			ToolCalls []ToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	} `json:"choices"`
	Usage *Usage `json:"usage,omitempty"`
}

// RealtimeLogUpdater 实时日志更新器，使用防抖机制
type RealtimeLogUpdater struct {
	logRepo       *repository.LogRepository
	logDetailRepo *repository.LogDetailRepository
	logID         uint
	apiKey        *models.GatewayAPIKey
	model         *models.Model

	// 数据通道
	dataChan chan []byte   // 接收新数据
	doneChan chan struct{} // 流结束信号

	// 防抖
	debounceDur  time.Duration // 200ms 防抖延迟
	maxInterval  time.Duration // 1s 最大写入间隔

	// 累计内容（并发安全）
	contentMu    sync.Mutex
	rawBuffer    strings.Builder // 原始数据缓冲（用于按行解析）
	content      strings.Builder // 普通内容
	reasoning    strings.Builder // 思考内容
	toolCalls    []ToolCall      // 工具调用（按 index 累加）
	role         string          // 角色
	usage        *Usage          // token 使用量
	finishReason string          // 结束原因

	// 控制
	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

// NewRealtimeLogUpdater 创建实时日志更新器
func NewRealtimeLogUpdater(
	logRepo *repository.LogRepository,
	logDetailRepo *repository.LogDetailRepository,
	logID uint,
	apiKey *models.GatewayAPIKey,
	model *models.Model,
	debounceDur time.Duration,
) *RealtimeLogUpdater {
	if debounceDur == 0 {
		debounceDur = 200 * time.Millisecond
	}

	ctx, cancel := context.WithCancel(context.Background())

	u := &RealtimeLogUpdater{
		logRepo:       logRepo,
		logDetailRepo: logDetailRepo,
		logID:         logID,
		apiKey:        apiKey,
		model:         model,
		dataChan:      make(chan []byte, 100),
		doneChan:      make(chan struct{}),
		debounceDur:   debounceDur,
		maxInterval:   time.Second, // 最大 1 秒写入一次
		role:          "assistant", // 默认角色
		usage:         &Usage{},
		ctx:           ctx,
		cancel:        cancel,
	}

	u.wg.Add(1)
	go u.runDebouncer()

	return u
}

// runDebouncer 防抖处理循环
func (u *RealtimeLogUpdater) runDebouncer() {
	defer u.wg.Done()

	debounceTimer := time.NewTimer(u.debounceDur)
	if !debounceTimer.Stop() {
		<-debounceTimer.C
	}

	maxIntervalTimer := time.NewTimer(u.maxInterval)
	if !maxIntervalTimer.Stop() {
		<-maxIntervalTimer.C
	}

	lastFlushTime := time.Now()

	for {
		select {
		case data := <-u.dataChan:
			// 解析 SSE 并更新累计内容
			u.parseAndUpdateContent(data)

			// 检查是否超过最大间隔
			if time.Since(lastFlushTime) >= u.maxInterval {
				u.flushToDatabase()
				lastFlushTime = time.Now()
				// 重置两个计时器
				debounceTimer.Stop()
				maxIntervalTimer.Reset(u.maxInterval)
			} else {
				// 重置防抖计时器
				debounceTimer.Stop()
				debounceTimer.Reset(u.debounceDur)
			}

		case <-debounceTimer.C:
			// 防抖触发，写入数据库
			u.flushToDatabase()
			lastFlushTime = time.Now()
			maxIntervalTimer.Reset(u.maxInterval)

		case <-maxIntervalTimer.C:
			// 最大间隔触发，写入数据库
			u.flushToDatabase()
			lastFlushTime = time.Now()
			maxIntervalTimer.Reset(u.maxInterval)

		case <-u.doneChan:
			// 流结束，确保最后一次写入
			debounceTimer.Stop()
			maxIntervalTimer.Stop()
			u.flushToDatabase()
			return

		case <-u.ctx.Done():
			debounceTimer.Stop()
			maxIntervalTimer.Stop()
			return
		}
	}
}

// PushData 非阻塞推送数据
func (u *RealtimeLogUpdater) PushData(data []byte) {
	if u == nil {
		return
	}
	select {
	case u.dataChan <- data:
	default:
		// 通道满，丢弃（避免阻塞）
	}
}

// parseAndUpdateContent 解析 SSE 数据并累计内容
func (u *RealtimeLogUpdater) parseAndUpdateContent(data []byte) {
	u.contentMu.Lock()
	defer u.contentMu.Unlock()

	// 将新数据追加到 rawBuffer
	u.rawBuffer.Write(data)

	// 从 rawBuffer 中提取完整的行
	rawData := u.rawBuffer.String()
	lastNewline := strings.LastIndex(rawData, "\n")
	if lastNewline == -1 {
		// 没有完整的行，等待更多数据
		return
	}

	// 提取完整的行
	completeLines := rawData[:lastNewline+1]
	// 保留未完成的行
	u.rawBuffer.Reset()
	u.rawBuffer.WriteString(rawData[lastNewline+1:])

	// 解析完整的行
	scanner := bufio.NewScanner(strings.NewReader(completeLines))
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			continue
		}
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		dataStr := strings.TrimPrefix(line, "data: ")
		if dataStr == "[DONE]" {
			continue
		}

		var chunk StreamChunk
		if err := json.Unmarshal([]byte(dataStr), &chunk); err != nil {
			continue
		}

		for _, choice := range chunk.Choices {
			// 累加角色
			if choice.Delta.Role != "" {
				u.role = choice.Delta.Role
			}
			// 累加普通内容
			if choice.Delta.Content != "" {
				u.content.WriteString(choice.Delta.Content)
			}
			// 累加思考内容（reasoning）
			if choice.Delta.Reasoning != "" {
				u.reasoning.WriteString(choice.Delta.Reasoning)
			}
			// 累加工具调用（按 index 合并）
			for _, tc := range choice.Delta.ToolCalls {
				u.mergeToolCall(tc)
			}
			// 结束原因
			if choice.FinishReason != nil {
				u.finishReason = *choice.FinishReason
			}
		}
		// 更新 usage
		if chunk.Usage != nil {
			u.usage = chunk.Usage
		}
	}
}

// mergeToolCall 按 index 合并工具调用（arguments 是增量拼接）
func (u *RealtimeLogUpdater) mergeToolCall(tc ToolCall) {
	if tc.Index >= len(u.toolCalls) {
		// 扩展数组
		for i := len(u.toolCalls); i <= tc.Index; i++ {
			u.toolCalls = append(u.toolCalls, ToolCall{})
		}
	}
	existing := &u.toolCalls[tc.Index]
	if tc.ID != "" {
		existing.ID = tc.ID
	}
	if tc.Type != "" {
		existing.Type = tc.Type
	}
	if tc.Function.Name != "" {
		existing.Function.Name = tc.Function.Name
	}
	if tc.Function.Arguments != "" {
		existing.Function.Arguments += tc.Function.Arguments
	}
}

// flushToDatabase 写入数据库（Log + LogDetail）
func (u *RealtimeLogUpdater) flushToDatabase() {
	if u.logID == 0 || u.logRepo == nil {
		return
	}

	u.contentMu.Lock()
	content := u.content.String()
	reasoning := u.reasoning.String()
	toolCalls := u.toolCalls
	usage := u.usage
	role := u.role
	u.contentMu.Unlock()

	// 计算 completion tokens
	completionTokens := usage.CompletionTokens
	if completionTokens == 0 {
		// 粗略估计：content + reasoning + tool_calls arguments
		totalLen := len(content) + len(reasoning)
		for _, tc := range toolCalls {
			totalLen += len(tc.Function.Arguments)
		}
		completionTokens = totalLen / 4
	}

	// 更新 Log 表（token 使用量）
	updates := map[string]interface{}{
		"completionTokens": completionTokens,
		"totalTokens":      usage.PromptTokens + completionTokens,
	}
	if usage.PromptTokens > 0 {
		updates["promptTokens"] = usage.PromptTokens
	}
	u.logRepo.UpdateByID(u.ctx, u.logID, updates)

	// 更新 LogDetail 表（完整响应体）
	if u.apiKey != nil && u.apiKey.LogDetails && u.logDetailRepo != nil && u.model != nil {
		// 构建消息对象
		message := map[string]interface{}{
			"role":    role,
			"content": content,
		}
		if reasoning != "" {
			message["reasoning"] = reasoning
		}
		if len(toolCalls) > 0 {
			// 过滤掉空的 tool calls
			validToolCalls := make([]ToolCall, 0)
			for _, tc := range toolCalls {
				if tc.ID != "" || tc.Function.Name != "" {
					validToolCalls = append(validToolCalls, tc)
				}
			}
			if len(validToolCalls) > 0 {
				message["tool_calls"] = validToolCalls
			}
		}

		respObj := map[string]interface{}{
			"id":      "",
			"object":  "chat.completion",
			"created": time.Now().Unix(),
			"model":   u.model.Name,
			"choices": []map[string]interface{}{
				{
					"index":         0,
					"message":       message,
					"finish_reason": nil,
				},
			},
		}
		if usage.PromptTokens > 0 || completionTokens > 0 {
			respObj["usage"] = map[string]int{
				"prompt_tokens":     usage.PromptTokens,
				"completion_tokens": completionTokens,
				"total_tokens":      usage.PromptTokens + completionTokens,
			}
		}

		respBody, _ := json.Marshal(respObj)
		respGz, _ := utils.GzipCompress(respBody)
		u.logDetailRepo.UpdateResponseBody(u.ctx, u.logID, respGz)
	}
}

// Close 关闭更新器，确保最后一次写入完成
func (u *RealtimeLogUpdater) Close() {
	if u == nil {
		return
	}

	// 发送流结束信号
	close(u.doneChan)

	// 等待 goroutine 完成
	done := make(chan struct{})
	go func() {
		u.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		// 超时保护
	}

	u.cancel()
}

// StreamingResponse wraps an HTTP response for streaming with logging support
type StreamingResponse struct {
	ResponseBody   *http.Response
	capturedBuffer *bytes.Buffer
	reader         *bufio.Reader
	ctx            context.Context // Context for cancellation detection

	// For logging after streaming is complete
	logID          uint            // ID of the initial log entry
	apiKey         *models.GatewayAPIKey
	model          *models.Model
	providerName   string
	request        *ChatRequest
	startTime      time.Time
	logRepo        *repository.LogRepository
	logDetailRepo  *repository.LogDetailRepository
	billingService *BillingService
	responseHeaders map[string]string // Response headers for logging

	// 实时日志更新器
	realtimeLogger *RealtimeLogUpdater

	// Protocol indicator for Anthropic streaming
	isAnthropicStream bool // true if upstream returns Anthropic format, false if OpenAI format
}

// NewStreamingResponse creates a new streaming response wrapper
func NewStreamingResponse(resp *http.Response, ctx context.Context) *StreamingResponse {
	return &StreamingResponse{
		ResponseBody:   resp,
		capturedBuffer: &bytes.Buffer{},
		reader:         bufio.NewReader(resp.Body),
		ctx:            ctx,
	}
}

// Read implements io.Reader for streaming
// It checks for context cancellation to stop reading when client disconnects
func (s *StreamingResponse) Read(p []byte) (n int, err error) {
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

	n, err = s.reader.Read(p)
	if n > 0 {
		s.capturedBuffer.Write(p[:n])

		// 推送数据到实时日志更新器
		if s.realtimeLogger != nil {
			dataCopy := make([]byte, n)
			copy(dataCopy, p[:n])
			s.realtimeLogger.PushData(dataCopy)
		}
	}
	return
}

// IsAnthropicStream returns whether the upstream stream is in Anthropic format
func (s *StreamingResponse) IsAnthropicStream() bool {
	return s.isAnthropicStream
}

// GetCapturedData returns the captured streaming data and parses it
func (s *StreamingResponse) GetCapturedData() (content string, usage *Usage, rawData string) {
	rawData = s.capturedBuffer.String()

	// Parse SSE format
	scanner := bufio.NewScanner(strings.NewReader(rawData))
	var contentBuilder strings.Builder
	usage = &Usage{}
	inReasoning := false

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

		// Extract content and reasoning from choices
		for _, choice := range chunk.Choices {
			// Handle reasoning tokens
			if choice.Delta.Reasoning != "" {
				if !inReasoning {
					contentBuilder.WriteString("<think>")
					inReasoning = true
				}
				contentBuilder.WriteString(choice.Delta.Reasoning)
			}

			// Handle regular content tokens
			if choice.Delta.Content != "" {
				// If we were in reasoning mode, close the think tag first
				if inReasoning {
					contentBuilder.WriteString("</think>")
					inReasoning = false
				}
				contentBuilder.WriteString(choice.Delta.Content)
			}
		}

		// Extract usage if present (some providers send it at the end)
		if chunk.Usage != nil {
			usage = chunk.Usage
		}
	}

	// Close reasoning block if it's still open at the end
	if inReasoning {
		contentBuilder.WriteString("</think>")
	}

	content = contentBuilder.String()
	return
}

// LogAfterComplete updates the log entry after streaming is complete
func (s *StreamingResponse) LogAfterComplete(ctx context.Context) {
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

	// Deduct cost only if request was successful
	if cost > 0 && status == 200 && s.apiKey.UserID != nil {
		s.billingService.DeductAndDistribute(ctx, s.apiKey.UserID, nil, cost)
	}

	// Update log entry
	updates := map[string]interface{}{
		"latency":           int(latency),
		"promptTokens":     usage.PromptTokens,
		"completionTokens": completionTokens,
		"totalTokens":      usage.PromptTokens + completionTokens,
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
				"promptTokens":     usage.PromptTokens,
				"completionTokens": completionTokens,
				"totalTokens":      usage.PromptTokens + completionTokens,
			},
		}
		respBody, _ := json.Marshal(respObj)
		respGz, _ := utils.GzipCompress(respBody)

		// Update existing LogDetail with response body
		s.logDetailRepo.UpdateResponseBody(ctx, s.logID, respGz)
	}
}

// Close closes the underlying response body and logs the request
func (s *StreamingResponse) Close() error {
	ctx := s.ctx
	if ctx == nil {
		ctx = context.Background()
	}

	// 先关闭实时日志更新器，确保最后一次写入完成
	if s.realtimeLogger != nil {
		s.realtimeLogger.Close()
	}

	s.LogAfterComplete(ctx)
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
	// Create custom transport with proxy bypass support
	transport := &http.Transport{
		Proxy: func(req *http.Request) (*url.URL, error) {
			if utils.ShouldBypassProxy(req.URL.String(), proxyConfig.NoProxy) {
				return nil, nil // Bypass proxy for matched URLs
			}
			return http.ProxyFromEnvironment(req)
		},
	}

	return &GatewayService{
		modelRepo:      modelRepo,
		modelRouteRepo: modelRouteRepo,
		apiKeyRepo:     apiKeyRepo,
		channelRepo:    channelRepo,
		userRepo:       userRepo,
		logRepo:        logRepo,
		logDetailRepo:  logDetailRepo,
		billingService: billingService,
		httpClient:     &http.Client{Timeout: 240 * time.Second, Transport: transport},
		proxyConfig:    proxyConfig,
	}
}

// HandleChatCompletions handles chat completions requests
// For streaming, returns (*StreamingResponse, error)
// For non-streaming, returns (*ChatResponse, error)
func (s *GatewayService) HandleChatCompletions(ctx context.Context, apiKey *models.GatewayAPIKey, req *ChatRequest, stream bool, requestHeaders http.Header) (interface{}, error) {
	startTime := time.Now()

	// Extract and filter headers for forwarding and logging
	forwardHeaders, headersJSON := extractForwardableHeaders(requestHeaders)

	// 1. Find model (supports alias and :latest)
	model, err := s.findModel(ctx, req.Model)
	if err != nil {
		log.Printf("[HandleChatCompletions] Model not found: %s, error: %v", req.Model, err)
		return nil, ErrModelNotFound
	}

	// 2. Select route (weighted random)
	route, err := s.selectRoute(ctx, model.ID)
	if err != nil {
		log.Printf("[HandleChatCompletions] No route available: model=%s, modelID=%d, error: %v", model.Name, model.ID, err)
		return nil, ErrNoRouteAvailable
	}

	// 3. Check permission
	if err := s.checkPermission(ctx, apiKey, model.ID); err != nil {
		log.Printf("[HandleChatCompletions] Permission denied: apiKeyID=%d, modelID=%d, error: %v", apiKey.ID, model.ID, err)
		return nil, err
	}

	// 4. Check balance
	if err := s.checkBalance(ctx, apiKey.UserID, model); err != nil {
		log.Printf("[HandleChatCompletions] Insufficient balance: userID=%v, model=%s", apiKey.UserID, model.Name)
		return nil, err
	}

	// Create initial log entry (status=0 means pending)
	// Skip logging for virtual API keys (ID=0) unless IsChatKey is true
	logEntry := &models.Log{
		APIKeyID:       getAPIKeyIDPtr(apiKey.ID),
		ModelName:      model.Name,
		ProviderName:   route.Provider.Name,
		Status:         0, // pending
		RequestHeaders: headersJSON,
	}
	// Log for real API keys or chat keys (IsChatKey=true)
	if apiKey.ID != 0 || apiKey.IsChatKey {
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

	// Helper to update log on completion
	updateLog := func(latency int, promptTokens, completionTokens, totalTokens int, cost int64, status int, errMsg string, respHeaders map[string]string) {
		if logEntry.ID == 0 {
			return
		}
		updates := map[string]interface{}{
			"latency":           latency,
			"promptTokens":     promptTokens,
			"completionTokens": completionTokens,
			"totalTokens":      totalTokens,
			"cost":              cost,
			"status":            status,
		}
		if errMsg != "" {
			updates["errorMessage"] = errMsg
		}
		if len(respHeaders) > 0 {
			respHeadersJSON, _ := json.Marshal(respHeaders)
			updates["responseHeaders"] = string(respHeadersJSON)
		}
		s.logRepo.UpdateByID(ctx, logEntry.ID, updates)
	}

	// 5. Build upstream request
	// Determine provider type to use (primary type from ProviderTypes or default)
	providerType := "openai" // default
	if len(route.Provider.ProviderTypes) > 0 {
		providerType = route.Provider.ProviderTypes[0].Type
	} else if route.Provider.Type != "" {
		providerType = route.Provider.Type
	}
	// Get base URL for the specific type (with fallback to default)
	baseURL := route.Provider.GetBaseURLForType(providerType)
	targetURL := fmt.Sprintf("%s/chat/completions", strings.TrimSuffix(baseURL, "/"))

	// Always use Model.Name for upstream request (not alias)
	upstreamReq := *req
	upstreamReq.Model = route.Model.Name

	// 6. Send upstream request with forwarded headers
	resp, err := s.sendUpstreamRequest(ctx, targetURL, route.Provider.APIKey, &upstreamReq, stream, forwardHeaders)
	if err != nil {
		log.Printf("[HandleChatCompletions] Upstream request failed: %v, URL: %s, Model: %s", err, targetURL, model.Name)
		latency := int(time.Since(startTime).Milliseconds())
		updateLog(latency, 0, 0, 0, 0, 502, err.Error(), nil)
		return nil, ErrUpstreamFailed
	}

	// Handle error responses
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		log.Printf("[HandleChatCompletions] Upstream error: status=%d, body=%s, URL: %s", resp.StatusCode, string(body), targetURL)
		latency := int(time.Since(startTime).Milliseconds())
		s.handleUpstreamError(ctx, resp, route)
		updateLog(latency, 0, 0, 0, 0, resp.StatusCode, fmt.Sprintf("Upstream error: %d, body: %s", resp.StatusCode, string(body)), nil)
		return nil, fmt.Errorf("upstream error: %d", resp.StatusCode)
	}

	// Handle streaming response
	if stream {
		streamResp := NewStreamingResponse(resp, ctx)
		streamResp.logID = logEntry.ID
		streamResp.apiKey = apiKey
		streamResp.model = model
		streamResp.providerName = route.Provider.Name
		streamResp.request = req
		streamResp.startTime = startTime
		streamResp.logRepo = s.logRepo
		streamResp.logDetailRepo = s.logDetailRepo
		streamResp.billingService = s.billingService
		// Extract response headers
		streamResp.responseHeaders = extractResponseHeaders(resp.Header)

		// 初始化实时日志更新器
		if logEntry.ID != 0 {
			streamResp.realtimeLogger = NewRealtimeLogUpdater(
				s.logRepo,
				s.logDetailRepo,
				logEntry.ID,
				apiKey,
				model,
				200*time.Millisecond,
			)
		}

		return streamResp, nil
	}

	// Handle non-streaming response
	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		log.Printf("[HandleChatCompletions] Read response body failed: %v", err)
		latency := int(time.Since(startTime).Milliseconds())
		updateLog(latency, 0, 0, 0, 0, 500, err.Error(), nil)
		return nil, err
	}

	var chatResp ChatResponse
	if err := json.Unmarshal(body, &chatResp); err != nil {
		log.Printf("[HandleChatCompletions] Parse response failed: %v, body: %s", err, string(body))
		latency := int(time.Since(startTime).Milliseconds())
		updateLog(latency, 0, 0, 0, 0, 500, fmt.Sprintf("Parse error: %v, body: %s", err, string(body)), nil)
		return nil, err
	}

	// Update log and calculate cost
	latency := int(time.Since(startTime).Milliseconds())
	respHeaders := extractResponseHeaders(resp.Header)
	s.updateLogAndCalculateCost(ctx, apiKey, model, route.Provider.Name, req, &chatResp, latency, logEntry.ID, respHeaders)

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
func (s *GatewayService) sendUpstreamRequest(ctx context.Context, url, apiKey string, req *ChatRequest, stream bool, forwardHeaders map[string]string) (*http.Response, error) {
	body, err := json.Marshal(req)
	if err != nil {
		log.Printf("[sendUpstreamRequest] Marshal request failed: %v", err)
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		log.Printf("[sendUpstreamRequest] Create request failed: %v, URL: %s", err, url)
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+apiKey)

	// Forward additional headers
	for key, value := range forwardHeaders {
		httpReq.Header.Set(key, value)
	}

	log.Printf("[sendUpstreamRequest] Sending request to: %s, stream: %v, model: %s", url, stream, req.Model)
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

// logAndCalculateCost logs the request and calculates cost (deprecated, use updateLogAndCalculateCost)
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

// updateLogAndCalculateCost updates an existing log entry and calculates cost
func (s *GatewayService) updateLogAndCalculateCost(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, req *ChatRequest, resp *ChatResponse, latency int, logID uint, respHeaders map[string]string) {
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

	// Update log entry
	if logID > 0 {
		updates := map[string]interface{}{
			"latency":              latency,
			"promptTokens":        promptTokens,
			"completionTokens":    completionTokens,
			"totalTokens":         totalTokens,
			"cost":                 cost,
			"ownerChannelId":     ownerChannelID,
			"ownerChannelUserId": ownerChannelUserID,
			"status":               200,
		}
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
}

// logError logs an error request
func (s *GatewayService) logError(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, latency, status int, errMsg string, req *ChatRequest, requestHeaders http.Header) {
	// Log for real API keys or chat keys (IsChatKey=true)
	if apiKey.ID == 0 && !apiKey.IsChatKey {
		return
	}

	// Extract headers for logging
	_, headersJSON := extractForwardableHeaders(requestHeaders)

	logEntry := &models.Log{
		Latency:        latency,
		APIKeyID:       getAPIKeyIDPtr(apiKey.ID),
		ModelName:      model.Name,
		ProviderName:   providerName,
		Status:         status,
		ErrorMessage:   errMsg,
		RequestHeaders: headersJSON,
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

// HandleAnthropicMessages handles Anthropic Messages API requests
// Supports direct forwarding if provider supports anthropic type, otherwise converts to OpenAI format
func (s *GatewayService) HandleAnthropicMessages(ctx context.Context, apiKey *models.GatewayAPIKey, req *models.AnthropicMessagesRequest, stream bool, requestHeaders http.Header) (interface{}, error) {
	startTime := time.Now()

	// Extract and filter headers for forwarding and logging
	forwardHeaders, headersJSON := extractForwardableHeaders(requestHeaders)

	// 1. Find model (supports alias and :latest)
	model, err := s.findModel(ctx, req.Model)
	if err != nil {
		log.Printf("[HandleAnthropicMessages] Model not found: %s, error: %v", req.Model, err)
		return nil, ErrModelNotFound
	}

	// 2. Select route (weighted random)
	route, err := s.selectRoute(ctx, model.ID)
	if err != nil {
		log.Printf("[HandleAnthropicMessages] No route available: model=%s, modelID=%d, error: %v", model.Name, model.ID, err)
		return nil, ErrNoRouteAvailable
	}

	// 3. Check permission
	if err := s.checkPermission(ctx, apiKey, model.ID); err != nil {
		log.Printf("[HandleAnthropicMessages] Permission denied: apiKeyID=%d, modelID=%d, error: %v", apiKey.ID, model.ID, err)
		return nil, err
	}

	// 4. Check balance
	if err := s.checkBalance(ctx, apiKey.UserID, model); err != nil {
		log.Printf("[HandleAnthropicMessages] Insufficient balance: userID=%v, model=%s", apiKey.UserID, model.Name)
		return nil, err
	}

	// Create initial log entry (status=0 means pending)
	logEntry := &models.Log{
		APIKeyID:       getAPIKeyIDPtr(apiKey.ID),
		ModelName:      model.Name,
		ProviderName:   route.Provider.Name,
		Status:         0, // pending
		RequestHeaders: headersJSON,
	}
	if apiKey.ID != 0 || apiKey.IsChatKey {
		if err := s.logRepo.Create(ctx, logEntry); err != nil {
			logEntry.ID = 0
		} else if apiKey.LogDetails {
			reqBody, _ := json.Marshal(req)
			reqGz, _ := utils.GzipCompress(reqBody)
			detail := &models.LogDetail{
				LogID:       logEntry.ID,
				RequestBody: reqGz,
			}
			s.logDetailRepo.Create(ctx, detail)
		}
	} else {
		logEntry.ID = 0
	}

	// Helper to update log on completion
	updateLog := func(latency int, promptTokens, completionTokens, totalTokens int, cost int64, status int, errMsg string, respHeaders map[string]string) {
		if logEntry.ID == 0 {
			return
		}
		updates := map[string]interface{}{
			"latency":           latency,
			"promptTokens":     promptTokens,
			"completionTokens": completionTokens,
			"totalTokens":      totalTokens,
			"cost":              cost,
			"status":            status,
		}
		if errMsg != "" {
			updates["errorMessage"] = errMsg
		}
		if len(respHeaders) > 0 {
			respHeadersJSON, _ := json.Marshal(respHeaders)
			updates["responseHeaders"] = string(respHeadersJSON)
		}
		s.logRepo.UpdateByID(ctx, logEntry.ID, updates)
	}

	// 5. Determine if provider supports anthropic protocol
	providerSupportsAnthropic := route.Provider.HasType("anthropic")
	converter := NewProtocolConverter()

	// Determine the upstream model name
	upstreamModelName := route.Model.Name

	if providerSupportsAnthropic {
		// Direct forwarding - provider supports anthropic
		baseURL := route.Provider.GetBaseURLForType("anthropic")
		targetURL := fmt.Sprintf("%s/messages", strings.TrimSuffix(baseURL, "/"))

		log.Printf("[HandleAnthropicMessages] Provider '%s' supports anthropic, direct forwarding to: %s", route.Provider.Name, targetURL)

		// Update model name in request
		upstreamReq := *req
		upstreamReq.Model = upstreamModelName

		// Send Anthropic format request
		resp, err := s.sendAnthropicUpstreamRequest(ctx, targetURL, route.Provider.APIKey, &upstreamReq, stream, forwardHeaders)
		if err != nil {
			log.Printf("[HandleAnthropicMessages] Upstream request failed: %v, URL: %s", err, targetURL)
			latency := int(time.Since(startTime).Milliseconds())
			updateLog(latency, 0, 0, 0, 0, 502, err.Error(), nil)
			return nil, ErrUpstreamFailed
		}

		if resp.StatusCode >= 400 {
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			log.Printf("[HandleAnthropicMessages] Upstream error: status=%d, body=%s, URL: %s", resp.StatusCode, string(body), targetURL)
			latency := int(time.Since(startTime).Milliseconds())
			s.handleUpstreamError(ctx, resp, route)
			updateLog(latency, 0, 0, 0, 0, resp.StatusCode, fmt.Sprintf("Upstream error: %d, body: %s", resp.StatusCode, string(body)), nil)
			return nil, fmt.Errorf("upstream error: %d", resp.StatusCode)
		}

		// Handle streaming response (direct Anthropic format)
		if stream {
			streamResp := NewStreamingResponse(resp, ctx)
			streamResp.logID = logEntry.ID
			streamResp.apiKey = apiKey
			streamResp.model = model
			streamResp.providerName = route.Provider.Name
			streamResp.isAnthropicStream = true
			streamResp.startTime = startTime
			streamResp.logRepo = s.logRepo
			streamResp.logDetailRepo = s.logDetailRepo
			streamResp.billingService = s.billingService
			streamResp.responseHeaders = extractResponseHeaders(resp.Header)

			if logEntry.ID != 0 {
				streamResp.realtimeLogger = NewRealtimeLogUpdater(
					s.logRepo,
					s.logDetailRepo,
					logEntry.ID,
					apiKey,
					model,
					200*time.Millisecond,
				)
			}

			log.Printf("[HandleAnthropicMessages] Response type: anthropic (direct stream)")
			return streamResp, nil
		}

		// Handle non-streaming response (direct Anthropic format)
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			log.Printf("[HandleAnthropicMessages] Read response body failed: %v", err)
			latency := int(time.Since(startTime).Milliseconds())
			updateLog(latency, 0, 0, 0, 0, 500, err.Error(), nil)
			return nil, err
		}

		var anthropicResp models.AnthropicMessagesResponse
		if err := json.Unmarshal(body, &anthropicResp); err != nil {
			log.Printf("[HandleAnthropicMessages] Parse response failed: %v, body: %s", err, string(body))
			latency := int(time.Since(startTime).Milliseconds())
			updateLog(latency, 0, 0, 0, 0, 500, fmt.Sprintf("Parse error: %v", err), nil)
			return nil, err
		}

		log.Printf("[HandleAnthropicMessages] Response type: anthropic (direct)")

		// Update log and calculate cost
		latency := int(time.Since(startTime).Milliseconds())
		respHeaders := extractResponseHeaders(resp.Header)
		s.updateAnthropicLogAndCalculateCost(ctx, apiKey, model, route.Provider.Name, req, &anthropicResp, latency, logEntry.ID, respHeaders)

		return &anthropicResp, nil
	}

	// Convert to OpenAI format - provider doesn't support anthropic
	log.Printf("[HandleAnthropicMessages] Provider '%s' doesn't support anthropic, converting to OpenAI format", route.Provider.Name)

	openAIReq, err := converter.ConvertRequest(req, ProtocolAnthropic, ProtocolOpenAI)
	if err != nil {
		log.Printf("[HandleAnthropicMessages] Convert request failed: %v", err)
		return nil, err
	}

	// Get OpenAI base URL
	baseURL := route.Provider.GetBaseURLForType("openai")
	targetURL := fmt.Sprintf("%s/chat/completions", strings.TrimSuffix(baseURL, "/"))

	log.Printf("[HandleAnthropicMessages] Sending OpenAI format request to: %s, stream: %v, model: %s", targetURL, stream, upstreamModelName)

	// Update model name in request
	chatReq := openAIReq.(*ChatRequest)
	chatReq.Model = upstreamModelName

	// Send OpenAI format request
	resp, err := s.sendUpstreamRequest(ctx, targetURL, route.Provider.APIKey, chatReq, stream, forwardHeaders)
	if err != nil {
		log.Printf("[HandleAnthropicMessages] Upstream request failed: %v, URL: %s", err, targetURL)
		latency := int(time.Since(startTime).Milliseconds())
		updateLog(latency, 0, 0, 0, 0, 502, err.Error(), nil)
		return nil, ErrUpstreamFailed
	}

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		log.Printf("[HandleAnthropicMessages] Upstream error: status=%d, body=%s, URL: %s", resp.StatusCode, string(body), targetURL)
		latency := int(time.Since(startTime).Milliseconds())
		s.handleUpstreamError(ctx, resp, route)
		updateLog(latency, 0, 0, 0, 0, resp.StatusCode, fmt.Sprintf("Upstream error: %d, body: %s", resp.StatusCode, string(body)), nil)
		return nil, fmt.Errorf("upstream error: %d", resp.StatusCode)
	}

	// Handle streaming response (need to convert back to Anthropic format)
	if stream {
		streamResp := NewStreamingResponse(resp, ctx)
		streamResp.logID = logEntry.ID
		streamResp.apiKey = apiKey
		streamResp.model = model
		streamResp.providerName = route.Provider.Name
		streamResp.isAnthropicStream = false // OpenAI stream that needs conversion
		streamResp.startTime = startTime
		streamResp.logRepo = s.logRepo
		streamResp.logDetailRepo = s.logDetailRepo
		streamResp.billingService = s.billingService
		streamResp.responseHeaders = extractResponseHeaders(resp.Header)

		if logEntry.ID != 0 {
			streamResp.realtimeLogger = NewRealtimeLogUpdater(
				s.logRepo,
				s.logDetailRepo,
				logEntry.ID,
				apiKey,
				model,
				200*time.Millisecond,
			)
		}

		log.Printf("[HandleAnthropicMessages] Response type: anthropic (converted from openai stream)")
		return streamResp, nil
	}

	// Handle non-streaming response (convert back to Anthropic format)
	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		log.Printf("[HandleAnthropicMessages] Read response body failed: %v", err)
		latency := int(time.Since(startTime).Milliseconds())
		updateLog(latency, 0, 0, 0, 0, 500, err.Error(), nil)
		return nil, err
	}

	var chatResp ChatResponse
	if err := json.Unmarshal(body, &chatResp); err != nil {
		log.Printf("[HandleAnthropicMessages] Parse response failed: %v, body: %s", err, string(body))
		latency := int(time.Since(startTime).Milliseconds())
		updateLog(latency, 0, 0, 0, 0, 500, fmt.Sprintf("Parse error: %v", err), nil)
		return nil, err
	}

	// Convert OpenAI response back to Anthropic format
	anthropicResp, err := converter.ConvertResponse(&chatResp, ProtocolOpenAI, ProtocolAnthropic, req.Model)
	if err != nil {
		log.Printf("[HandleAnthropicMessages] Convert response failed: %v", err)
		return nil, err
	}

	log.Printf("[HandleAnthropicMessages] Response type: anthropic (converted from openai)")

	// Update log and calculate cost
	latency := int(time.Since(startTime).Milliseconds())
	respHeaders := extractResponseHeaders(resp.Header)
	s.updateLogAndCalculateCost(ctx, apiKey, model, route.Provider.Name, chatReq, &chatResp, latency, logEntry.ID, respHeaders)

	return anthropicResp, nil
}

// sendAnthropicUpstreamRequest sends an Anthropic format request to the upstream provider
func (s *GatewayService) sendAnthropicUpstreamRequest(ctx context.Context, url, apiKey string, req *models.AnthropicMessagesRequest, stream bool, forwardHeaders map[string]string) (*http.Response, error) {
	body, err := json.Marshal(req)
	if err != nil {
		log.Printf("[sendAnthropicUpstreamRequest] Marshal request failed: %v", err)
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		log.Printf("[sendAnthropicUpstreamRequest] Create request failed: %v, URL: %s", err, url)
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", apiKey) // Anthropic uses x-api-key header
	httpReq.Header.Set("anthropic-version", "2023-06-01") // Required by Anthropic API

	// Forward additional headers
	for key, value := range forwardHeaders {
		httpReq.Header.Set(key, value)
	}

	log.Printf("[sendAnthropicUpstreamRequest] Sending request to: %s, stream: %v, model: %s", url, stream, req.Model)
	return s.httpClient.Do(httpReq)
}

// updateAnthropicLogAndCalculateCost updates log and calculates cost for Anthropic format responses
func (s *GatewayService) updateAnthropicLogAndCalculateCost(ctx context.Context, apiKey *models.GatewayAPIKey, model *models.Model, providerName string, req *models.AnthropicMessagesRequest, resp *models.AnthropicMessagesResponse, latency int, logID uint, respHeaders map[string]string) {
	var promptTokens, completionTokens, totalTokens int
	if resp.Usage != nil {
		promptTokens = resp.Usage.InputTokens
		completionTokens = resp.Usage.OutputTokens
		totalTokens = promptTokens + completionTokens
	}

	cost := s.billingService.CalculateCost(promptTokens, completionTokens, model.InputTokenPrice, model.OutputTokenPrice)

	// Determine owner channel (for shared channels)
	ownerChannelID, ownerChannelUserID := s.determineChannelOwner(ctx, apiKey, model.ID)

	// Deduct cost
	if cost > 0 && apiKey.UserID != nil {
		s.billingService.DeductAndDistribute(ctx, apiKey.UserID, ownerChannelUserID, cost)
	}

	// Update log entry
	if logID > 0 {
		updates := map[string]interface{}{
			"latency":              latency,
			"promptTokens":        promptTokens,
			"completionTokens":    completionTokens,
			"totalTokens":         totalTokens,
			"cost":                 cost,
			"ownerChannelId":     ownerChannelID,
			"ownerChannelUserId": ownerChannelUserID,
			"status":               200,
		}
		if len(respHeaders) > 0 {
			respHeadersJSON, _ := json.Marshal(respHeaders)
			updates["responseHeaders"] = string(respHeadersJSON)
		}
		s.logRepo.UpdateByID(ctx, logID, updates)

		if apiKey.LogDetails {
			respBody, _ := json.Marshal(resp)
			respGz, _ := utils.GzipCompress(respBody)
			s.logDetailRepo.UpdateResponseBody(ctx, logID, respGz)
		}
	}
}