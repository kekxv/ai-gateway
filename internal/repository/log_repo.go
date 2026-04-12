package repository

import (
	"context"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

type LogRepository struct {
	db *gorm.DB
}

func NewLogRepository(db *gorm.DB) *LogRepository {
	return &LogRepository{db: db}
}

func (r *LogRepository) Create(ctx context.Context, log *models.Log) error {
	return r.db.WithContext(ctx).Create(log).Error
}

// UpdateByID updates a log entry by ID with the given fields
func (r *LogRepository) UpdateByID(ctx context.Context, id uint, updates map[string]interface{}) error {
	return r.db.WithContext(ctx).Model(&models.Log{}).Where("id = ?", id).Updates(updates).Error
}

func (r *LogRepository) List(ctx context.Context, apiKeyID *uint, model string, page, limit int) ([]models.Log, int64, error) {
	var logs []models.Log
	var total int64

	query := r.db.WithContext(ctx).Model(&models.Log{})
	if apiKeyID != nil {
		query = query.Where("apiKeyId = ?", *apiKeyID)
	}
	if model != "" {
		query = query.Where("modelName = ?", model)
	}

	query.Count(&total)

	offset := (page - 1) * limit
	err := query.
		Preload("APIKey.User").
		Preload("OwnerChannel").
		Order("createdAt DESC").
		Offset(offset).Limit(limit).
		Find(&logs).Error
	return logs, total, err
}

func (r *LogRepository) FindByID(ctx context.Context, id uint) (*models.Log, error) {
	var log models.Log
	err := r.db.WithContext(ctx).
		Preload("APIKey.User").
		Preload("OwnerChannel").
		First(&log, id).Error
	if err != nil {
		return nil, err
	}
	return &log, nil
}

type LogDetailRepository struct {
	db *gorm.DB
}

func NewLogDetailRepository(db *gorm.DB) *LogDetailRepository {
	return &LogDetailRepository{db: db}
}

func (r *LogDetailRepository) Create(ctx context.Context, detail *models.LogDetail) error {
	return r.db.WithContext(ctx).Create(detail).Error
}

func (r *LogDetailRepository) FindByLogID(ctx context.Context, logID uint) (*models.LogDetail, error) {
	var detail models.LogDetail
	// Use Session with silent logger to avoid "record not found" warning log
	err := r.db.WithContext(ctx).
		Session(&gorm.Session{Logger: logger.Default.LogMode(logger.Silent)}).
		Where("logId = ?", logID).
		First(&detail).Error
	if err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, err
	}
	return &detail, nil
}

func (r *LogDetailRepository) Cleanup(ctx context.Context, before time.Time) error {
	return r.db.WithContext(ctx).Where("createdAt < ?", before).Delete(&models.LogDetail{}).Error
}

// UpdateResponseBody updates the response body of an existing log detail
func (r *LogDetailRepository) UpdateResponseBody(ctx context.Context, logID uint, responseBody []byte) error {
	return r.db.WithContext(ctx).
		Model(&models.LogDetail{}).
		Where("logId = ?", logID).
		Update("responseBody", responseBody).Error
}

type SettingsRepository struct {
	db *gorm.DB
}

func NewSettingsRepository(db *gorm.DB) *SettingsRepository {
	return &SettingsRepository{db: db}
}

func (r *SettingsRepository) Get(ctx context.Context, key string) (string, error) {
	var setting models.Settings
	err := r.db.WithContext(ctx).Where("key = ?", key).First(&setting).Error
	if err != nil {
		return "", err
	}
	return setting.Value, nil
}

func (r *SettingsRepository) Set(ctx context.Context, key, value string) error {
	return r.db.WithContext(ctx).Create(&models.Settings{Key: key, Value: value}).Error
}

func (r *SettingsRepository) GetJWTSecret(ctx context.Context) (string, error) {
	return r.Get(ctx, "JWT_SECRET")
}