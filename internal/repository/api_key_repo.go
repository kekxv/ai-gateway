package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type APIKeyRepository struct {
	db *gorm.DB
}

func NewAPIKeyRepository(db *gorm.DB) *APIKeyRepository {
	return &APIKeyRepository{db: db}
}

func (r *APIKeyRepository) FindByKey(ctx context.Context, key string) (*models.GatewayAPIKey, error) {
	var apiKey models.GatewayAPIKey
	err := r.db.WithContext(ctx).Where("key = ?", key).First(&apiKey).Error
	if err != nil {
		return nil, err
	}
	return &apiKey, nil
}

func (r *APIKeyRepository) FindByID(ctx context.Context, id uint) (*models.GatewayAPIKey, error) {
	var apiKey models.GatewayAPIKey
	err := r.db.WithContext(ctx).First(&apiKey, id).Error
	if err != nil {
		return nil, err
	}
	return &apiKey, nil
}

func (r *APIKeyRepository) List(ctx context.Context, userID *uint) ([]models.GatewayAPIKey, error) {
	var keys []models.GatewayAPIKey
	query := r.db.WithContext(ctx)
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Find(&keys).Error
	return keys, err
}

// ListWithCount returns API keys with pagination support
func (r *APIKeyRepository) ListWithCount(ctx context.Context, userID *uint, page, pageSize int) ([]models.GatewayAPIKey, int64, error) {
	var keys []models.GatewayAPIKey
	var total int64

	query := r.db.WithContext(ctx).Model(&models.GatewayAPIKey{})
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}

	// Get total count
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	// Get paginated data
	offset := (page - 1) * pageSize
	query = r.db.WithContext(ctx)
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Offset(offset).Limit(pageSize).Find(&keys).Error
	if err != nil {
		return nil, 0, err
	}

	// Load channels for each key
	for i := range keys {
		if !keys[i].BindToAllChannels {
			var channelBindings []models.GatewayAPIKeyChannel
			r.db.WithContext(ctx).Where("apiKeyId = ?", keys[i].ID).Find(&channelBindings)
			if len(channelBindings) > 0 {
				var channelIDs []uint
				for _, b := range channelBindings {
					channelIDs = append(channelIDs, b.ChannelID)
				}
				var channels []models.Channel
				r.db.WithContext(ctx).Where("id IN ?", channelIDs).Find(&channels)
				keys[i].ChannelList = channels
			}
		}
	}

	return keys, total, err
}

func (r *APIKeyRepository) Create(ctx context.Context, apiKey *models.GatewayAPIKey) error {
	return r.db.WithContext(ctx).Create(apiKey).Error
}

func (r *APIKeyRepository) Update(ctx context.Context, apiKey *models.GatewayAPIKey) error {
	return r.db.WithContext(ctx).Save(apiKey).Error
}

func (r *APIKeyRepository) UpdateLastUsed(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Model(&models.GatewayAPIKey{}).Where("id = ?", id).
		Update("lastUsed", gorm.Expr("CURRENT_TIMESTAMP")).Error
}

func (r *APIKeyRepository) GetChannels(ctx context.Context, apiKeyID uint) ([]models.GatewayAPIKeyChannel, error) {
	var channels []models.GatewayAPIKeyChannel
	err := r.db.WithContext(ctx).Where("apiKeyId = ?", apiKeyID).Find(&channels).Error
	return channels, err
}

func (r *APIKeyRepository) BindChannels(ctx context.Context, apiKeyID uint, channelIDs []uint) error {
	// First delete existing bindings
	r.db.WithContext(ctx).Where("apiKeyId = ?", apiKeyID).Delete(&models.GatewayAPIKeyChannel{})

	// Then create new bindings
	for _, channelID := range channelIDs {
		binding := models.GatewayAPIKeyChannel{APIKeyID: apiKeyID, ChannelID: channelID}
		if err := r.db.WithContext(ctx).Create(&binding).Error; err != nil {
			return err
		}
	}
	return nil
}