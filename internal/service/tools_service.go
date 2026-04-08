package service

import (
	"bytes"
	"compress/gzip"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"

	"golang.org/x/text/encoding/htmlindex"
	"golang.org/x/text/encoding/simplifiedchinese"
	"golang.org/x/text/encoding/traditionalchinese"
	"golang.org/x/text/transform"
)

var (
	ErrRateLimitExceeded = errors.New("rate limit exceeded")
	ErrInvalidURL        = errors.New("invalid URL")
	ErrRequestFailed     = errors.New("request failed")
	ErrTimeout           = errors.New("request timeout")
	ErrSearchFailed      = errors.New("search failed")
)

// RateLimiter simple in-memory rate limiter
type RateLimiter struct {
	mu       sync.RWMutex
	requests map[string]*rateLimitEntry
}

type rateLimitEntry struct {
	count     int
	expiresAt time.Time
}

func NewRateLimiter() *RateLimiter {
	return &RateLimiter{
		requests: make(map[string]*rateLimitEntry),
	}
}

// Check checks if the request is allowed and increments the counter
func (rl *RateLimiter) Check(key string, limit int, window time.Duration) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	entry, exists := rl.requests[key]

	if !exists || entry.expiresAt.Before(now) {
		rl.requests[key] = &rateLimitEntry{
			count:     1,
			expiresAt: now.Add(window),
		}
		return true
	}

	if entry.count >= limit {
		return false
	}

	entry.count++
	return true
}

// WebSearchRequest request for web search
type WebSearchRequest struct {
	Query    string `json:"query"`
	Location string `json:"location"`
	Hl       string `json:"hl"`
	Gl       string `json:"gl"`
}

// WebSearchResult result for web search
type WebSearchResult struct {
	Query        string             `json:"query"`
	TotalResults int                `json:"total_results"`
	Results      []SearchResultItem `json:"results"`
}

// SearchResultItem single search result
type SearchResultItem struct {
	Title   string `json:"title"`
	Snippet string `json:"snippet"`
	URL     string `json:"url"`
}

// FetchWebpageRequest request for fetching webpage
type FetchWebpageRequest struct {
	URL      string `json:"url"`
	Selector string `json:"selector"`
	Format   string `json:"format"` // "html" or "text", default "text"
}

// FetchWebpageResult result for fetching webpage
type FetchWebpageResult struct {
	URL         string            `json:"url"`
	Title       string            `json:"title"`
	Description string            `json:"description"`
	TextContent string            `json:"textContent,omitempty"`
	HTMLContent string            `json:"htmlContent,omitempty"`
	HTMLLength  int               `json:"htmlLength"`
	Contents    []SelectorContent `json:"contents,omitempty"`
	Selector    string            `json:"selector,omitempty"`
	Matched     int               `json:"matched,omitempty"`
	Encoding    string            `json:"encoding"`
	Format      string            `json:"format"`
}

// SelectorContent content extracted by selector
type SelectorContent struct {
	Text string `json:"text"`
	HTML string `json:"html"`
}

// ToolsService handles tool proxy requests
type ToolsService struct {
	httpClient *http.Client

	// Rate limits
	webSearchLimit     int
	webSearchWindow    time.Duration
	fetchWebpageLimit  int
	fetchWebpageWindow time.Duration

	// Max content size (bytes)
	maxContentSize int64
}

// ToolsService creates a new tools service
func NewToolsService() *ToolsService {
	return &ToolsService{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
			Transport: &http.Transport{
				Proxy: http.ProxyFromEnvironment,
			},
		},
		webSearchLimit:     10,         // 10 requests per minute
		webSearchWindow:    time.Minute,
		fetchWebpageLimit:  20,         // 20 requests per minute
		fetchWebpageWindow: time.Minute,
		maxContentSize:     2 * 1024 * 1024, // 2MB max
	}
}

// CheckRateLimit checks rate limit for a user and action
func (s *ToolsService) CheckRateLimit(userID uint, action string) bool {
	var limit int
	var window time.Duration

	switch action {
	case "web_search":
		limit = s.webSearchLimit
		window = s.webSearchWindow
	case "fetch_webpage":
		limit = s.fetchWebpageLimit
		window = s.fetchWebpageWindow
	default:
		return false
	}

	key := fmt.Sprintf("%d:%s", userID, action)
	return s.checkRateLimitInternal(key, limit, window)
}

func (s *ToolsService) checkRateLimitInternal(key string, limit int, window time.Duration) bool {
	// Simple in-memory rate limit check
	// For production, use Redis
	return true // Allow all for now, rate limiter can be added later
}

// WebSearch performs a web search using DuckDuckGo (no API key required)
func (s *ToolsService) WebSearch(ctx context.Context, req *WebSearchRequest) (*WebSearchResult, error) {
	if req.Query == "" {
		return nil, errors.New("query is required")
	}

	// Use DuckDuckGo HTML search
	searchURL := fmt.Sprintf("https://html.duckduckgo.com/html/?q=%s", url.QueryEscape(req.Query))

	httpReq, err := http.NewRequestWithContext(ctx, "GET", searchURL, nil)
	if err != nil {
		return nil, fmt.Errorf("create request failed: %w", err)
	}

	// Set headers to mimic browser
	httpReq.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
	httpReq.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	httpReq.Header.Set("Accept-Language", "en-US,en;q=0.5")

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: status %d", ErrRequestFailed, resp.StatusCode)
	}

	// Limit response size
	limitedReader := io.LimitReader(resp.Body, s.maxContentSize)
	body, err := io.ReadAll(limitedReader)
	if err != nil {
		return nil, fmt.Errorf("read response failed: %w", err)
	}

	// Detect and convert encoding
	body, _ = detectAndConvertEncoding(body, resp.Header.Get("Content-Type"))

	// Parse DuckDuckGo HTML results
	results := parseDuckDuckGoResults(string(body))

	return &WebSearchResult{
		Query:        req.Query,
		TotalResults: len(results),
		Results:      results,
	}, nil
}

// parseDuckDuckGoResults parses DuckDuckGo HTML search results
func parseDuckDuckGoResults(html string) []SearchResultItem {
	var results []SearchResultItem

	// DuckDuckGo HTML structure:
	// <a class="result__a" href="...">Title</a>
	// <a class="result__snippet" href="...">Snippet</a>

	// Find all result containers
	resultRegex := regexp.MustCompile(`<div class="result[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>`)
	matches := resultRegex.FindAllStringSubmatch(html, -1)

	for _, match := range matches {
		if len(match) < 2 {
			continue
		}

		resultHTML := match[1]

		// Extract title and URL
		titleRegex := regexp.MustCompile(`<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>`)
		titleMatch := titleRegex.FindStringSubmatch(resultHTML)

		if len(titleMatch) < 3 {
			continue
		}

		resultURL := titleMatch[1]
		title := cleanHTMLTags(titleMatch[2])

		// DuckDuckGo uses redirect URLs, extract actual URL
		if strings.Contains(resultURL, "uddg=") {
			if u, err := url.Parse(resultURL); err == nil {
				if actualURL := u.Query().Get("uddg"); actualURL != "" {
					resultURL = actualURL
				}
			}
		}

		// Extract snippet
		snippet := ""
		snippetRegex := regexp.MustCompile(`<a[^>]+class="result__snippet"[^>]*>([\s\S]*?)</a>`)
		snippetMatch := snippetRegex.FindStringSubmatch(resultHTML)
		if len(snippetMatch) > 1 {
			snippet = cleanHTMLTags(snippetMatch[1])
		}

		if title != "" && resultURL != "" {
			results = append(results, SearchResultItem{
				Title:   strings.TrimSpace(title),
				Snippet: strings.TrimSpace(snippet),
				URL:     resultURL,
			})
		}

		// Limit to 10 results
		if len(results) >= 10 {
			break
		}
	}

	return results
}

// cleanHTMLTags removes HTML tags and decodes entities
func cleanHTMLTags(s string) string {
	// Remove HTML tags
	tagRegex := regexp.MustCompile(`<[^>]+>`)
	s = tagRegex.ReplaceAllString(s, " ")

	// Decode common HTML entities
	s = strings.ReplaceAll(s, "&amp;", "&")
	s = strings.ReplaceAll(s, "&lt;", "<")
	s = strings.ReplaceAll(s, "&gt;", ">")
	s = strings.ReplaceAll(s, "&quot;", "\"")
	s = strings.ReplaceAll(s, "&#39;", "'")
	s = strings.ReplaceAll(s, "&nbsp;", " ")

	// Clean whitespace
	s = strings.ReplaceAll(s, "\n", " ")
	s = strings.ReplaceAll(s, "\t", " ")
	for strings.Contains(s, "  ") {
		s = strings.ReplaceAll(s, "  ", " ")
	}

	return strings.TrimSpace(s)
}

// FetchWebpage fetches webpage content
func (s *ToolsService) FetchWebpage(ctx context.Context, req *FetchWebpageRequest) (*FetchWebpageResult, error) {
	// Validate URL
	if req.URL == "" {
		return nil, ErrInvalidURL
	}

	parsedURL, err := url.Parse(req.URL)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidURL, err)
	}

	if parsedURL.Scheme != "http" && parsedURL.Scheme != "https" {
		return nil, fmt.Errorf("%w: only http/https allowed", ErrInvalidURL)
	}

	// Default format is text
	format := req.Format
	if format == "" {
		format = "text"
	}

	// Try multiple approaches: direct request first, then proxies
	var body []byte
	var contentType string
	var detectedEncoding string

	// Approach 1: Direct request (works for many sites)
	body, contentType, err = s.tryDirectFetch(ctx, req.URL)
	if err == nil {
		body, detectedEncoding = detectAndConvertEncoding(body, contentType)
		return s.parseWebpageResult(req.URL, body, req.Selector, detectedEncoding, format), nil
	}

	// Approach 2: Try allorigins.win proxy
	body, err = s.tryAlloriginsProxy(ctx, req.URL)
	if err == nil {
		body, detectedEncoding = detectAndConvertEncoding(body, "")
		return s.parseWebpageResult(req.URL, body, req.Selector, detectedEncoding, format), nil
	}

	// Approach 3: Try corsproxy.io with different encoding
	body, err = s.tryCorsproxyFetch(ctx, req.URL)
	if err == nil {
		body, detectedEncoding = detectAndConvertEncoding(body, "")
		return s.parseWebpageResult(req.URL, body, req.Selector, detectedEncoding, format), nil
	}

	// All approaches failed
	return nil, fmt.Errorf("failed to fetch webpage after trying multiple proxies: %w", err)
}

// detectAndConvertEncoding detects encoding from Content-Type header and HTML meta tags, converts to UTF-8
func detectAndConvertEncoding(body []byte, contentType string) ([]byte, string) {
	// First, try to decompress gzip if needed
	body = decompressGzip(body)

	encodingName := detectEncoding(body, contentType)

	if encodingName == "" || encodingName == "utf-8" || encodingName == "utf8" {
		return body, "utf-8"
	}

	// Get encoder from encoding name
	enc, err := htmlindex.Get(encodingName)
	if err != nil {
		// Try common Chinese encodings
		switch strings.ToLower(encodingName) {
		case "gb2312", "gbk":
			enc = simplifiedchinese.GBK
		case "gb18030":
			enc = simplifiedchinese.GB18030
		case "big5":
			enc = traditionalchinese.Big5
		default:
			return body, "utf-8"
		}
	}

	// Convert to UTF-8
	reader := transform.NewReader(bytes.NewReader(body), enc.NewDecoder())
	converted, err := io.ReadAll(reader)
	if err != nil {
		return body, encodingName
	}

	return converted, encodingName
}

// decompressGzip tries to decompress gzip content
func decompressGzip(body []byte) []byte {
	// Check for gzip magic number (0x1f 0x8b)
	if len(body) < 2 || body[0] != 0x1f || body[1] != 0x8b {
		return body
	}

	gzipReader, err := gzip.NewReader(bytes.NewReader(body))
	if err != nil {
		return body
	}
	defer gzipReader.Close()

	decompressed, err := io.ReadAll(gzipReader)
	if err != nil {
		return body
	}

	return decompressed
}

// detectEncoding detects encoding from Content-Type header and HTML meta tags
func detectEncoding(body []byte, contentType string) string {
	// First, check Content-Type header
	if contentType != "" {
		// Parse charset from Content-Type: text/html; charset=GBK
		contentType = strings.ToLower(contentType)
		if idx := strings.Index(contentType, "charset="); idx != -1 {
			charset := contentType[idx+8:]
			charset = strings.Trim(charset, ` "'`)
			charset = strings.Split(charset, ";")[0]
			charset = strings.TrimSpace(charset)
			if charset != "" {
				return charset
			}
		}
	}

	// Second, check HTML meta tags
	htmlStr := string(body)

	// Check <meta charset="...">
	metaCharsetRegex := regexp.MustCompile(`<meta[^>]+charset\s*=\s*["']?([^"'\s>]+)["']?`)
	match := metaCharsetRegex.FindStringSubmatch(htmlStr)
	if len(match) > 1 {
		return strings.ToLower(match[1])
	}

	// Check <meta http-equiv="Content-Type" content="text/html; charset=...">
	metaContentTypeRegex := regexp.MustCompile(`<meta[^>]+http-equiv\s*=\s*["']?Content-Type["']?[^>]+content\s*=\s*["']([^"']+)["']`)
	match = metaContentTypeRegex.FindStringSubmatch(htmlStr)
	if len(match) > 1 {
		content := strings.ToLower(match[1])
		if idx := strings.Index(content, "charset="); idx != -1 {
			charset := content[idx+8:]
			charset = strings.Trim(charset, ` "'`)
			charset = strings.Split(charset, ";")[0]
			charset = strings.TrimSpace(charset)
			if charset != "" {
				return charset
			}
		}
	}

	// Default to UTF-8
	return "utf-8"
}

// tryDirectFetch attempts to fetch the URL directly
func (s *ToolsService) tryDirectFetch(ctx context.Context, targetURL string) ([]byte, string, error) {
	httpReq, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return nil, "", err
	}

	// Set headers to mimic browser (without Accept-Encoding to avoid gzip)
	httpReq.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
	httpReq.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
	httpReq.Header.Set("Accept-Language", "en-US,en;q=0.5,zh-CN;q=0.9,zh;q=0.8")
	httpReq.Header.Set("Connection", "keep-alive")

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, "", fmt.Errorf("status %d", resp.StatusCode)
	}

	limitedReader := io.LimitReader(resp.Body, s.maxContentSize)
	body, err := io.ReadAll(limitedReader)
	if err != nil {
		return nil, "", err
	}

	return body, resp.Header.Get("Content-Type"), nil
}

// tryAlloriginsProxy uses allorigins.win as proxy
func (s *ToolsService) tryAlloriginsProxy(ctx context.Context, targetURL string) ([]byte, error) {
	proxyURL := fmt.Sprintf("https://api.allorigins.win/raw?url=%s", url.QueryEscape(targetURL))

	httpReq, err := http.NewRequestWithContext(ctx, "GET", proxyURL, nil)
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status %d", resp.StatusCode)
	}

	limitedReader := io.LimitReader(resp.Body, s.maxContentSize)
	body, err := io.ReadAll(limitedReader)
	if err != nil {
		return nil, err
	}

	return body, nil
}

// tryCorsproxyFetch uses corsproxy.io with base64 encoding
func (s *ToolsService) tryCorsproxyFetch(ctx context.Context, targetURL string) ([]byte, error) {
	// Try different corsproxy.io URL formats
	formats := []string{
		fmt.Sprintf("https://corsproxy.io/?%s", url.QueryEscape(targetURL)),
		fmt.Sprintf("https://corsproxy.io/?url=%s", url.QueryEscape(targetURL)),
	}

	for _, proxyURL := range formats {
		httpReq, err := http.NewRequestWithContext(ctx, "GET", proxyURL, nil)
		if err != nil {
			continue
		}

		httpReq.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
		httpReq.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

		resp, err := s.httpClient.Do(httpReq)
		if err != nil {
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			limitedReader := io.LimitReader(resp.Body, s.maxContentSize)
			body, err := io.ReadAll(limitedReader)
			if err != nil {
				continue
			}
			return body, nil
		}
	}

	return nil, fmt.Errorf("corsproxy failed")
}

// parseWebpageResult parses the HTML content and returns result
func (s *ToolsService) parseWebpageResult(targetURL string, body []byte, selector string, encoding string, format string) *FetchWebpageResult {
	result := &FetchWebpageResult{
		URL:        targetURL,
		HTMLLength: len(body),
		Encoding:   encoding,
		Format:     format,
	}

	// Extract title and description from HTML
	htmlStr := string(body)
	result.Title = extractMeta(htmlStr, `<title`)
	result.Description = extractMetaDescription(htmlStr)

	// Try to extract main content area first
	mainContent := extractMainContent(htmlStr)

	// Remove unwanted tags for cleaner content
	cleanHTML := removeTags(mainContent, "script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "form", "input", "button", "select", "textarea", "label", "fieldset", "legend", "optgroup", "option", "datalist", "keygen", "output", "progress", "meter")

	if format == "html" {
		// Return HTML content
		result.HTMLContent = cleanHTML
		// Also provide a short text summary
		result.TextContent = strings.TrimSpace(extractText(cleanHTML))
		if len(result.TextContent) > 1000 {
			result.TextContent = result.TextContent[:1000] + "..."
		}
	} else {
		// Return text content (default)
		result.TextContent = strings.TrimSpace(extractText(cleanHTML))
		if len(result.TextContent) > 10000 {
			result.TextContent = result.TextContent[:10000] + "..."
		}
	}

	// If selector is specified, we can't parse in Go without a proper HTML parser
	// For now, return the full content and let frontend handle selector
	if selector != "" {
		result.Selector = selector
		result.Matched = 0 // Will be computed by frontend
	}

	return result
}

// extractMainContent tries to find the main content area
func extractMainContent(html string) string {
	// Common content patterns to look for
	contentPatterns := []string{
		// Article tags
		`<article[^>]*>`,
		// Main tags
		`<main[^>]*>`,
		// Common content class/id patterns
		`<div[^>]+class="[^"]*content[^"]*"[^>]*>`,
		`<div[^>]+id="[^"]*content[^"]*"[^>]*>`,
		`<div[^>]+class="[^"]*article[^"]*"[^>]*>`,
		`<div[^>]+class="[^"]*post[^"]*"[^>]*>`,
		`<div[^>]+class="[^"]*main[^"]*"[^>]*>`,
		`<div[^>]+id="[^"]*main[^"]*"[^>]*>`,
		`<div[^>]+class="[^"]*body[^"]*"[^>]*>`,
		`<section[^>]+class="[^"]*content[^"]*"[^>]*>`,
	}

	for _, pattern := range contentPatterns {
		re := regexp.MustCompile(pattern)
		match := re.FindStringIndex(html)
		if match != nil {
			start := match[0]
			// Find the corresponding closing tag
			content := extractTagContent(html, start)
			if content != "" && len(content) > 200 {
				return content
			}
		}
	}

	// If no main content found, use body
	bodyStart := strings.Index(html, "<body")
	if bodyStart != -1 {
		bodyEnd := strings.Index(html, "</body>")
		if bodyEnd != -1 {
			return html[bodyStart:bodyEnd + 7]
		}
	}

	return html
}

// extractTagContent extracts content between opening and closing tag
func extractTagContent(html string, start int) string {
	// Find the opening tag end
	tagEnd := strings.Index(html[start:], ">")
	if tagEnd == -1 {
		return ""
	}
	tagEnd += start + 1

	// Determine the tag name
	tagStartIdx := strings.Index(html[start:], "<")
	if tagStartIdx == -1 {
		return ""
	}
	tagNameEnd := strings.Index(html[start+tagStartIdx:], " ")
	if tagNameEnd == -1 {
		tagNameEnd = strings.Index(html[start+tagStartIdx:], ">")
	}
	if tagNameEnd == -1 {
		return ""
	}
	tagName := html[start+tagStartIdx+1 : start+tagStartIdx+tagNameEnd]

	// Find matching closing tag
	closeTag := "</" + tagName + ">"
	depth := 1
	pos := tagEnd

	for depth > 0 && pos < len(html) {
		// Find next opening or closing tag
		nextOpen := strings.Index(html[pos:], "<"+tagName)
		nextClose := strings.Index(html[pos:], closeTag)

		if nextClose == -1 {
			break
		}

		if nextOpen != -1 && nextOpen < nextClose {
			// Found another opening tag
			depth++
			pos += nextOpen + len(tagName) + 1
		} else {
			// Found closing tag
			depth--
			if depth == 0 {
				return html[start : pos+nextClose+len(closeTag)]
			}
			pos += nextClose + len(closeTag)
		}
	}

	return ""
}

// extractMeta extracts content from HTML meta tags
func extractMeta(html, tagStart string) string {
	idx := strings.Index(html, tagStart)
	if idx == -1 {
		return ""
	}

	// Find the end of opening tag
	start := strings.Index(html[idx:], ">")
	if start == -1 {
		return ""
	}
	start += idx + 1

	// Find closing tag
	end := strings.Index(html[start:], "</")
	if end == -1 {
		return ""
	}

	content := strings.TrimSpace(html[start : start+end])
	return cleanHTMLTags(content)
}

// extractMetaDescription extracts meta description
func extractMetaDescription(html string) string {
	// Try different patterns for meta description
	patterns := []string{
		`<meta[^>]+name=["']description["']`,
		`<meta[^>]+property=["']og:description["']`,
	}

	for _, pattern := range patterns {
		re := regexp.MustCompile(pattern + `[^>]+content=["']([^"']+)["']`)
		match := re.FindStringSubmatch(html)
		if len(match) > 1 {
			return strings.TrimSpace(match[1])
		}

		// Try reversed attribute order
		re = regexp.MustCompile(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:name|property)=["'](?:description|og:description)["']`)
		match = re.FindStringSubmatch(html)
		if len(match) > 1 {
			return strings.TrimSpace(match[1])
		}
	}

	return ""
}

// removeTags removes content between specified tags
func removeTags(html string, tags ...string) string {
	result := html
	for _, tag := range tags {
		// Remove self-closing tags first
		selfClosingRegex := regexp.MustCompile(`<` + tag + `[^>]*/>`)
		result = selfClosingRegex.ReplaceAllString(result, "")

		// Remove opening and closing tags with content
		openTagRegex := regexp.MustCompile(`<` + tag + `[^>]*>`)
		closeTag := "</" + tag + ">"

		// Keep removing until all instances are gone
		for {
			match := openTagRegex.FindStringIndex(result)
			if match == nil {
				break
			}
			start := match[0]

			// Find corresponding closing tag
			end := strings.Index(result[start:], closeTag)
			if end == -1 {
				// No closing tag, just remove opening tag
				result = result[:start] + result[match[1]:]
				continue
			}
			end += start + len(closeTag)
			result = result[:start] + result[end:]
		}
	}
	return result
}

// extractText extracts text content from HTML
func extractText(html string) string {
	// Remove HTML tags and preserve some structure
	var result strings.Builder
	inTag := false
	tagName := ""
	tagNameStart := -1

	for i, r := range html {
		if r == '<' {
			inTag = true
			tagNameStart = i + 1
			continue
		}
		if r == '>' {
			inTag = false
			// Get tag name
			if tagNameStart != -1 && i > tagNameStart {
				tagName = strings.ToLower(html[tagNameStart:i])
				// Check if it's a block-level tag
				if isBlockTag(tagName) {
					result.WriteString("\n")
				}
			}
			tagNameStart = -1
			tagName = ""
			continue
		}
		if inTag {
			// Skip tag attributes, just track tag name
			if tagNameStart != -1 && (r == ' ' || r == '/' || r == '\t' || r == '\n') {
				tagName = strings.ToLower(html[tagNameStart:i])
			}
			continue
		}
		result.WriteRune(r)
	}

	// Clean up whitespace
	text := result.String()

	// Decode HTML entities
	text = decodeHTMLEntities(text)

	// Normalize whitespace
	text = normalizeWhitespace(text)

	return text
}

// isBlockTag checks if tag is a block-level element
func isBlockTag(tag string) bool {
	blockTags := map[string]bool{
		"p":       true,
		"div":     true,
		"section": true,
		"article": true,
		"h1":      true,
		"h2":      true,
		"h3":      true,
		"h4":      true,
		"h5":      true,
		"h6":      true,
		"ul":      true,
		"ol":      true,
		"li":      true,
		"table":   true,
		"tr":      true,
		"td":      true,
		"th":      true,
		"br":      true,
		"hr":      true,
		"blockquote": true,
		"pre":     true,
	}
	return blockTags[tag]
}

// decodeHTMLEntities decodes common HTML entities
func decodeHTMLEntities(s string) string {
	// Common entities
	s = strings.ReplaceAll(s, "&amp;", "&")
	s = strings.ReplaceAll(s, "&lt;", "<")
	s = strings.ReplaceAll(s, "&gt;", ">")
	s = strings.ReplaceAll(s, "&quot;", "\"")
	s = strings.ReplaceAll(s, "&apos;", "'")
	s = strings.ReplaceAll(s, "&#39;", "'")
	s = strings.ReplaceAll(s, "&nbsp;", " ")
	s = strings.ReplaceAll(s, "&copy;", "©")
	s = strings.ReplaceAll(s, "&reg;", "®")
	s = strings.ReplaceAll(s, "&trade;", "™")

	// Decode numeric entities
	// &#xxx; format
	numericRegex := regexp.MustCompile(`&#(\d+);`)
	s = numericRegex.ReplaceAllStringFunc(s, func(match string) string {
		numStr := numericRegex.FindStringSubmatch(match)[1]
		num := 0
		for _, c := range numStr {
			num = num*10 + int(c-'0')
		}
		if num > 0 && num < 0x10FFFF {
			return string(rune(num))
		}
		return match
	})

	// &#xxxx; format (hex)
	hexRegex := regexp.MustCompile(`&#x([0-9a-fA-F]+);`)
	s = hexRegex.ReplaceAllStringFunc(s, func(match string) string {
		hexStr := hexRegex.FindStringSubmatch(match)[1]
		num := 0
		for _, c := range hexStr {
			digit := 0
			if c >= '0' && c <= '9' {
				digit = int(c - '0')
			} else if c >= 'a' && c <= 'f' {
				digit = int(c - 'a' + 10)
			} else if c >= 'A' && c <= 'F' {
				digit = int(c - 'A' + 10)
			}
			num = num*16 + digit
		}
		if num > 0 && num < 0x10FFFF {
			return string(rune(num))
		}
		return match
	})

	return s
}

// normalizeWhitespace normalizes whitespace in text
func normalizeWhitespace(s string) string {
	// Replace multiple newlines with single newline
	for strings.Contains(s, "\n\n\n") {
		s = strings.ReplaceAll(s, "\n\n\n", "\n\n")
	}

	// Replace multiple spaces with single space
	for strings.Contains(s, "  ") {
		s = strings.ReplaceAll(s, "  ", " ")
	}

	// Remove spaces at start/end of lines
	lines := strings.Split(s, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimSpace(line)
	}
	s = strings.Join(lines, "\n")

	// Remove empty lines (but keep one for paragraph separation)
	result := []string{}
	prevEmpty := false
	for _, line := range strings.Split(s, "\n") {
		if line == "" {
			if !prevEmpty {
				result = append(result, line)
				prevEmpty = true
			}
		} else {
			result = append(result, line)
			prevEmpty = false
		}
	}

	return strings.TrimSpace(strings.Join(result, "\n"))
}