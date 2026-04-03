package repository

import (
	"context"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
)

// StatsResult represents aggregated stats for a single entity
type StatsResult struct {
	Name             string
	RequestCount     int64
	PromptTokens     int64
	CompletionTokens int64
	TotalTokens      int64
	Cost             int64
}

// DailyStats represents stats for a single day
type DailyStats struct {
	Date             string
	RequestCount     int64
	PromptTokens     int64
	CompletionTokens int64
	TotalTokens      int64
	Cost             int64
}

// UserStats represents user statistics
type UserStats struct {
	Total    int64
	Active   int64
	Disabled int64
	Expired  int64
}

// GetStatsByProvider returns aggregated stats grouped by provider
func (r *LogRepository) GetStatsByProvider(ctx context.Context, startDate, endDate time.Time) ([]StatsResult, error) {
	var results []StatsResult
	err := r.db.WithContext(ctx).Model(&models.Log{}).
		Select("providerName as name, COUNT(*) as request_count, SUM(promptTokens) as prompt_tokens, SUM(completionTokens) as completion_tokens, SUM(totalTokens) as total_tokens, SUM(cost) as cost").
		Where("createdAt >= ? AND createdAt <= ?", startDate, endDate).
		Group("providerName").
		Scan(&results).Error
	return results, err
}

// GetStatsByModel returns aggregated stats grouped by model
func (r *LogRepository) GetStatsByModel(ctx context.Context, startDate, endDate time.Time) ([]StatsResult, error) {
	var results []StatsResult
	err := r.db.WithContext(ctx).Model(&models.Log{}).
		Select("modelName as name, COUNT(*) as request_count, SUM(promptTokens) as prompt_tokens, SUM(completionTokens) as completion_tokens, SUM(totalTokens) as total_tokens, SUM(cost) as cost").
		Where("createdAt >= ? AND createdAt <= ?", startDate, endDate).
		Group("modelName").
		Scan(&results).Error
	return results, err
}

// GetStatsByAPIKey returns aggregated stats grouped by API key
func (r *LogRepository) GetStatsByAPIKey(ctx context.Context, startDate, endDate time.Time) ([]StatsResult, error) {
	var results []StatsResult
	err := r.db.WithContext(ctx).Model(&models.Log{}).
		Select("CAST(apiKeyId AS TEXT) as name, COUNT(*) as request_count, SUM(promptTokens) as prompt_tokens, SUM(completionTokens) as completion_tokens, SUM(totalTokens) as total_tokens, SUM(cost) as cost").
		Where("createdAt >= ? AND createdAt <= ?", startDate, endDate).
		Group("apiKeyId").
		Scan(&results).Error
	return results, err
}

// GetStatsByUser returns aggregated stats grouped by user (via API key)
func (r *LogRepository) GetStatsByUser(ctx context.Context, startDate, endDate time.Time) ([]StatsResult, error) {
	var results []StatsResult
	err := r.db.WithContext(ctx).Table("Log as l").
		Select("COALESCE(u.email, 'Unknown') as name, COUNT(*) as request_count, SUM(l.promptTokens) as prompt_tokens, SUM(l.completionTokens) as completion_tokens, SUM(l.totalTokens) as total_tokens, SUM(l.cost) as cost").
		Joins("LEFT JOIN GatewayApiKey g ON l.apiKeyId = g.id").
		Joins("LEFT JOIN User u ON g.userId = u.id").
		Where("l.createdAt >= ? AND l.createdAt <= ?", startDate, endDate).
		Group("u.email").
		Scan(&results).Error
	return results, err
}

// GetDailyUsage returns daily stats for a given period
func (r *LogRepository) GetDailyUsage(ctx context.Context, startDate, endDate time.Time) ([]DailyStats, error) {
	var results []DailyStats
	err := r.db.WithContext(ctx).Model(&models.Log{}).
		Select("DATE(createdAt) as date, COUNT(*) as request_count, SUM(promptTokens) as prompt_tokens, SUM(completionTokens) as completion_tokens, SUM(totalTokens) as total_tokens, SUM(cost) as cost").
		Where("createdAt >= ? AND createdAt <= ?", startDate, endDate).
		Group("DATE(createdAt)").
		Order("date ASC").
		Scan(&results).Error
	return results, err
}

// GetTotalStats returns total stats for a given period
func (r *LogRepository) GetTotalStats(ctx context.Context, startDate, endDate time.Time) (int64, int64, int64, error) {
	var result struct {
		RequestCount int64
		TotalTokens  int64
		TotalCost    int64
	}
	err := r.db.WithContext(ctx).Model(&models.Log{}).
		Select("COUNT(*) as request_count, SUM(totalTokens) as total_tokens, SUM(cost) as total_cost").
		Where("createdAt >= ? AND createdAt <= ?", startDate, endDate).
		Scan(&result).Error
	return result.RequestCount, result.TotalTokens, result.TotalCost, err
}

// GetUserStats returns user statistics
func (r *UserRepository) GetUserStats(ctx context.Context) (UserStats, error) {
	var stats UserStats

	// Total users
	err := r.db.WithContext(ctx).Model(&models.User{}).Count(&stats.Total).Error
	if err != nil {
		return stats, err
	}

	// Active users (not disabled and not expired)
	now := time.Now()
	err = r.db.WithContext(ctx).Model(&models.User{}).
		Where("disabled = ? AND (validUntil IS NULL OR validUntil > ?)", false, now).
		Count(&stats.Active).Error
	if err != nil {
		return stats, err
	}

	// Disabled users
	err = r.db.WithContext(ctx).Model(&models.User{}).
		Where("disabled = ?", true).
		Count(&stats.Disabled).Error
	if err != nil {
		return stats, err
	}

	// Expired users
	err = r.db.WithContext(ctx).Model(&models.User{}).
		Where("validUntil IS NOT NULL AND validUntil <= ?", now).
		Count(&stats.Expired).Error
	if err != nil {
		return stats, err
	}

	return stats, nil
}

// GetUserTokenStats returns token usage stats for a specific user
func (r *LogRepository) GetUserTokenStats(ctx context.Context, userID uint) (promptTokens, completionTokens, totalTokens int64, err error) {
	var result struct {
		PromptTokens     int64
		CompletionTokens int64
		TotalTokens      int64
	}
	err = r.db.WithContext(ctx).Table("Log as l").
		Select("SUM(l.promptTokens) as prompt_tokens, SUM(l.completionTokens) as completion_tokens, SUM(l.totalTokens) as total_tokens").
		Joins("JOIN GatewayApiKey g ON l.apiKeyId = g.id").
		Where("g.userId = ?", userID).
		Scan(&result).Error
	return result.PromptTokens, result.CompletionTokens, result.TotalTokens, err
}

// GetUserDailyUsage returns daily usage stats for a specific user
func (r *LogRepository) GetUserDailyUsage(ctx context.Context, userID uint, startDate, endDate time.Time) ([]DailyStats, error) {
	var results []DailyStats
	err := r.db.WithContext(ctx).Table("Log as l").
		Select("DATE(l.createdAt) as date, COUNT(*) as request_count, SUM(l.promptTokens) as prompt_tokens, SUM(l.completionTokens) as completion_tokens, SUM(l.totalTokens) as total_tokens, SUM(l.cost) as cost").
		Joins("JOIN GatewayApiKey g ON l.apiKeyId = g.id").
		Where("g.userId = ?", userID).
		Where("l.createdAt >= ? AND l.createdAt <= ?", startDate, endDate).
		Group("DATE(l.createdAt)").
		Order("date ASC").
		Scan(&results).Error
	return results, err
}

// GetUserModelUsage returns usage stats by model for a specific user
func (r *LogRepository) GetUserModelUsage(ctx context.Context, userID uint) ([]StatsResult, error) {
	var results []StatsResult
	err := r.db.WithContext(ctx).Table("Log as l").
		Select("l.modelName as name, COUNT(*) as request_count, SUM(l.promptTokens) as prompt_tokens, SUM(l.completionTokens) as completion_tokens, SUM(l.totalTokens) as total_tokens, SUM(l.cost) as cost").
		Joins("JOIN GatewayApiKey g ON l.apiKeyId = g.id").
		Where("g.userId = ?", userID).
		Group("l.modelName").
		Order("total_tokens DESC").
		Scan(&results).Error
	return results, err
}