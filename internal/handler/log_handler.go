package handler

import (
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/utils"
)

type LogHandler struct {
	logRepo       *repository.LogRepository
	logDetailRepo *repository.LogDetailRepository
}

func NewLogHandler(logRepo *repository.LogRepository, logDetailRepo *repository.LogDetailRepository) *LogHandler {
	return &LogHandler{logRepo: logRepo, logDetailRepo: logDetailRepo}
}

func (h *LogHandler) ListLogs(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	model := c.Query("model")

	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}

	logs, total, err := h.logRepo.List(c.Request.Context(), nil, model, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"logs": logs,
		"total": total,
	})
}

func (h *LogHandler) GetLogDetail(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	log, err := h.logRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Log not found"})
		return
	}

	detail, err := h.logDetailRepo.FindByLogID(c.Request.Context(), log.ID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// If no detail found, return empty detail
	if detail == nil {
		c.JSON(http.StatusOK, gin.H{
			"log":    log,
			"detail": nil,
		})
		return
	}

	// Decompress request/response bodies
	var reqBody, respBody string
	if detail.RequestBody != nil {
		if data, err := utils.GzipDecompress(detail.RequestBody); err == nil {
			reqBody = string(data)
		}
	}
	if detail.ResponseBody != nil {
		if data, err := utils.GzipDecompress(detail.ResponseBody); err == nil {
			respBody = string(data)
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"log": log,
		"detail": gin.H{
			"requestBody":  reqBody,
			"responseBody": respBody,
		},
	})
}

func (h *LogHandler) CleanupLogDetails(c *gin.Context) {
	// Delete log details older than 30 days
	before := time.Now().AddDate(0, 0, -30)

	if err := h.logDetailRepo.Cleanup(c.Request.Context(), before); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Log details cleaned up"})
}

// GetLogFilters returns distinct model names and provider names from logs for filter dropdowns
func (h *LogHandler) GetLogFilters(c *gin.Context) {
	ctx := c.Request.Context()

	models, err := h.logRepo.GetDistinctModels(ctx)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	providers, err := h.logRepo.GetDistinctProviders(ctx)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"models":    models,
		"providers": providers,
	})
}

// StatsHandler
type StatsHandler struct {
	logRepo      *repository.LogRepository
	userRepo     *repository.UserRepository
	modelRepo    *repository.ModelRepository
	providerRepo *repository.ProviderRepository
}

func NewStatsHandler(logRepo *repository.LogRepository, userRepo *repository.UserRepository, modelRepo *repository.ModelRepository, providerRepo *repository.ProviderRepository) *StatsHandler {
	return &StatsHandler{logRepo: logRepo, userRepo: userRepo, modelRepo: modelRepo, providerRepo: providerRepo}
}

func (h *StatsHandler) GetStats(c *gin.Context) {
	ctx := c.Request.Context()

	// Get date range from query params (default to last 30 days)
	now := time.Now()
	startDate := now.AddDate(0, 0, -30)
	endDate := now

	if start := c.Query("start_date"); start != "" {
		if parsed, err := time.Parse("2006-01-02", start); err == nil {
			startDate = parsed
		}
	}
	if end := c.Query("end_date"); end != "" {
		if parsed, err := time.Parse("2006-01-02", end); err == nil {
			endDate = parsed
		}
	}

	// Get stats from repository
	byProvider, _ := h.logRepo.GetStatsByProvider(ctx, startDate, endDate)
	byModel, _ := h.logRepo.GetStatsByModel(ctx, startDate, endDate)
	byApiKey, _ := h.logRepo.GetStatsByAPIKey(ctx, startDate, endDate)
	dailyUsage, _ := h.logRepo.GetDailyUsage(ctx, startDate, endDate)

	// Get weekly usage (last 14 days for better view)
	weeklyStart := now.AddDate(0, 0, -14)
	weeklyUsage, _ := h.logRepo.GetDailyUsage(ctx, weeklyStart, now)

	// Get user stats for admin users
	userRole, exists := c.Get("role")
	userStats := map[string]interface{}{"total": 0, "active": 0, "disabled": 0, "expired": 0}
	byUser := []map[string]interface{}{}

	if exists && userRole == "ADMIN" {
		stats, err := h.userRepo.GetUserStats(ctx)
		if err == nil {
			userStats = map[string]interface{}{
				"total":    stats.Total,
				"active":   stats.Active,
				"disabled": stats.Disabled,
				"expired":  stats.Expired,
			}
		}
		// Get byUser stats
		userStatsData, _ := h.logRepo.GetStatsByUser(ctx, startDate, endDate)
		for _, u := range userStatsData {
			byUser = append(byUser, map[string]interface{}{
				"name":             u.Name,
				"requestCount":     u.RequestCount,
				"promptTokens":     u.PromptTokens,
				"completionTokens": u.CompletionTokens,
				"totalTokens":      u.TotalTokens,
				"tokens":           u.TotalTokens,
				"requests":         u.RequestCount,
				"cost":             u.Cost,
			})
		}
	}

	// Get monthly usage (last 12 weeks grouped by week, labeled by week start date)
	weeklyAggregated := []map[string]interface{}{}
	for i := 11; i >= 0; i-- {
		weekStart := now.AddDate(0, 0, -7*i)
		weekEnd := weekStart.AddDate(0, 0, 7)
		if weekEnd.After(now) {
			weekEnd = now
		}
		weekStats, _ := h.logRepo.GetDailyUsage(ctx, weekStart, weekEnd)
		totalRequests := int64(0)
		var totalTokens, promptTokens, completionTokens int64
		for _, d := range weekStats {
			totalRequests += d.RequestCount
			totalTokens += d.TotalTokens
			promptTokens += d.PromptTokens
			completionTokens += d.CompletionTokens
		}
		// Use week label like "W1", "W2" or date range
		weekLabel := weekStart.Format("01/02")
		weeklyAggregated = append(weeklyAggregated, map[string]interface{}{
			"date":             weekLabel,
			"requestCount":     totalRequests,
			"requests":         totalRequests,
			"tokens":           totalTokens,
			"promptTokens":     promptTokens,
			"completionTokens": completionTokens,
		})
	}

	// Token usage over time (prompt vs completion) - same as dailyUsage
	tokenUsageOverTime := []map[string]interface{}{}
	for _, d := range dailyUsage {
		tokenUsageOverTime = append(tokenUsageOverTime, map[string]interface{}{
			"date":             d.Date,
			"promptTokens":     d.PromptTokens,
			"completionTokens": d.CompletionTokens,
			"totalTokens":      d.TotalTokens,
			"tokens":           d.TotalTokens,
			"requestCount":     d.RequestCount,
			"requests":         d.RequestCount,
		})
	}

	// Get total stats (use larger range for totals - last 90 days)
	totalStartDate := now.AddDate(0, 0, -90)
	totalRequests, totalTokens, totalCost, totalPromptTokens, totalCompletionTokens, _ := h.logRepo.GetTotalStats(ctx, totalStartDate, now)

	// Calculate stats days (from startDate to endDate)
	statsDays := int(endDate.Sub(startDate).Hours() / 24) + 1

	// Get provider and model counts from database
	providerCount, _ := h.providerRepo.Count(ctx)
	modelCount, _ := h.modelRepo.Count(ctx)

	// Transform provider/model/apiKey stats to expected format
	byProviderResult := []map[string]interface{}{}
	for _, p := range byProvider {
		byProviderResult = append(byProviderResult, map[string]interface{}{
			"name":             p.Name,
			"requestCount":     p.RequestCount,
			"promptTokens":     p.PromptTokens,
			"completionTokens": p.CompletionTokens,
			"totalTokens":      p.TotalTokens,
			"tokens":           p.TotalTokens,
			"requests":         p.RequestCount,
			"cost":             p.Cost,
		})
	}

	byModelResult := []map[string]interface{}{}
	for _, m := range byModel {
		byModelResult = append(byModelResult, map[string]interface{}{
			"name":             m.Name,
			"requestCount":     m.RequestCount,
			"promptTokens":     m.PromptTokens,
			"completionTokens": m.CompletionTokens,
			"totalTokens":      m.TotalTokens,
			"tokens":           m.TotalTokens,
			"requests":         m.RequestCount,
			"cost":             m.Cost,
		})
	}

	byApiKeyResult := []map[string]interface{}{}
	for _, k := range byApiKey {
		byApiKeyResult = append(byApiKeyResult, map[string]interface{}{
			"name":             k.Name,
			"requestCount":     k.RequestCount,
			"promptTokens":     k.PromptTokens,
			"completionTokens": k.CompletionTokens,
			"totalTokens":      k.TotalTokens,
			"tokens":           k.TotalTokens,
			"requests":         k.RequestCount,
			"cost":             k.Cost,
		})
	}

	dailyUsageResult := []map[string]interface{}{}
	for _, d := range dailyUsage {
		dailyUsageResult = append(dailyUsageResult, map[string]interface{}{
			"date":             d.Date,
			"requestCount":     d.RequestCount,
			"promptTokens":     d.PromptTokens,
			"completionTokens": d.CompletionTokens,
			"totalTokens":      d.TotalTokens,
			"tokens":           d.TotalTokens,
			"requests":         d.RequestCount,
			"cost":             d.Cost,
		})
	}

	weeklyUsageResult := []map[string]interface{}{}
	for _, d := range weeklyUsage {
		weeklyUsageResult = append(weeklyUsageResult, map[string]interface{}{
			"date":             d.Date,
			"requestCount":     d.RequestCount,
			"promptTokens":     d.PromptTokens,
			"completionTokens": d.CompletionTokens,
			"totalTokens":      d.TotalTokens,
			"tokens":           d.TotalTokens,
			"requests":         d.RequestCount,
			"cost":             d.Cost,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"byProvider":             byProviderResult,
		"byModel":                byModelResult,
		"byApiKey":               byApiKeyResult,
		"byUser":                 byUser,
		"dailyUsage":             dailyUsageResult,
		"weeklyUsage":            weeklyUsageResult,
		"monthlyUsage":           weeklyAggregated,
		"tokenUsageOverTime":     tokenUsageOverTime,
		"userTokenUsageOverTime": []map[string]interface{}{},
		"userStats":              userStats,
		"totalCost":              totalCost,
		"totalRequests":          totalRequests,
		"totalTokens":            totalTokens,
		"totalPromptTokens":      totalPromptTokens,
		"totalCompletionTokens":  totalCompletionTokens,
		"statsDays":              statsDays,
		"providerCount":          providerCount,
		"modelCount":             modelCount,
	})
}

func (h *StatsHandler) TestModel(c *gin.Context) {
	// TODO: Implement model testing
	c.JSON(http.StatusOK, gin.H{"message": "Model test not implemented"})
}