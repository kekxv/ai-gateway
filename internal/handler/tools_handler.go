package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/middleware"
	"github.com/kekxv/ai-gateway/internal/service"
)

type ToolsHandler struct {
	toolsService *service.ToolsService
}

func NewToolsHandler(toolsService *service.ToolsService) *ToolsHandler {
	return &ToolsHandler{toolsService: toolsService}
}

// WebSearch handles web search requests
// @Summary Web Search
// @Description Search the web using SerpAPI
// @Tags Tools
// @Accept json
// @Produce json
// @Param request body service.WebSearchRequest true "Search request"
// @Success 200 {object} service.WebSearchResult
// @Failure 400 {object} map[string]string
// @Failure 401 {object} map[string]string
// @Failure 429 {object} map[string]string
// @Failure 500 {object} map[string]string
// @Router /api/tools/web-search [post]
func (h *ToolsHandler) WebSearch(c *gin.Context) {
	// Get user ID from JWT token
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "请先登录"})
		return
	}

	// Check rate limit
	if !h.toolsService.CheckRateLimit(userID, "web_search") {
		c.JSON(http.StatusTooManyRequests, gin.H{"error": "请求过于频繁，请稍后再试"})
		return
	}

	// Parse request
	var req service.WebSearchRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "参数错误: " + err.Error()})
		return
	}

	// Validate query
	if req.Query == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "搜索关键词不能为空"})
		return
	}

	// Perform search
	result, err := h.toolsService.WebSearch(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, result)
}

// FetchWebpage handles webpage fetching requests
// @Summary Fetch Webpage
// @Description Fetch content from a webpage
// @Tags Tools
// @Accept json
// @Produce json
// @Param request body service.FetchWebpageRequest true "Fetch request"
// @Success 200 {object} service.FetchWebpageResult
// @Failure 400 {object} map[string]string
// @Failure 401 {object} map[string]string
// @Failure 429 {object} map[string]string
// @Failure 500 {object} map[string]string
// @Router /api/tools/fetch-webpage [post]
func (h *ToolsHandler) FetchWebpage(c *gin.Context) {
	// Get user ID from JWT token
	userID := middleware.GetUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "请先登录"})
		return
	}

	// Check rate limit
	if !h.toolsService.CheckRateLimit(userID, "fetch_webpage") {
		c.JSON(http.StatusTooManyRequests, gin.H{"error": "请求过于频繁，请稍后再试"})
		return
	}

	// Parse request
	var req service.FetchWebpageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "参数错误: " + err.Error()})
		return
	}

	// Validate URL
	if req.URL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "URL 不能为空"})
		return
	}

	// Fetch webpage
	result, err := h.toolsService.FetchWebpage(c.Request.Context(), &req)
	if err != nil {
		if err == service.ErrInvalidURL {
			c.JSON(http.StatusBadRequest, gin.H{"error": "无效的 URL"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, result)
}