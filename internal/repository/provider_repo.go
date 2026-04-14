package repository

import (
	"context"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type ProviderRepository struct {
	db *gorm.DB
}

func NewProviderRepository(db *gorm.DB) *ProviderRepository {
	return &ProviderRepository{db: db}
}

func (r *ProviderRepository) FindByID(ctx context.Context, id uint) (*models.Provider, error) {
	var provider models.Provider
	err := r.db.WithContext(ctx).First(&provider, id).Error
	if err != nil {
		return nil, err
	}
	return &provider, nil
}

// FindByIDWithTypes returns a provider with its ProviderTypes preloaded
func (r *ProviderRepository) FindByIDWithTypes(ctx context.Context, id uint) (*models.Provider, error) {
	var provider models.Provider
	err := r.db.WithContext(ctx).
		Preload("ProviderTypes").
		First(&provider, id).Error
	if err != nil {
		return nil, err
	}
	// Populate TypesList from ProviderTypes
	if len(provider.ProviderTypes) > 0 {
		provider.TypesList = make([]string, len(provider.ProviderTypes))
		for i, pt := range provider.ProviderTypes {
			provider.TypesList[i] = pt.Type
		}
	} else {
		provider.TypesList = provider.GetTypes()
	}
	return &provider, nil
}

func (r *ProviderRepository) List(ctx context.Context, userID *uint) ([]models.Provider, error) {
	var providers []models.Provider
	query := r.db.WithContext(ctx)
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Find(&providers).Error
	return providers, err
}

// ListWithTypes returns providers with ProviderTypes preloaded
func (r *ProviderRepository) ListWithTypes(ctx context.Context, userID *uint) ([]models.Provider, error) {
	var providers []models.Provider
	query := r.db.WithContext(ctx).Preload("ProviderTypes")
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Find(&providers).Error
	return providers, err
}

// ListWithCount returns providers with pagination support
func (r *ProviderRepository) ListWithCount(ctx context.Context, userID *uint, page, pageSize int) ([]models.Provider, int64, error) {
	var providers []models.Provider
	var total int64

	query := r.db.WithContext(ctx).Model(&models.Provider{})
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
	err := query.Offset(offset).Limit(pageSize).Find(&providers).Error
	return providers, total, err
}

func (r *ProviderRepository) Create(ctx context.Context, provider *models.Provider) error {
	return r.db.WithContext(ctx).Create(provider).Error
}

func (r *ProviderRepository) Update(ctx context.Context, provider *models.Provider) error {
	return r.db.WithContext(ctx).Save(provider).Error
}

func (r *ProviderRepository) Delete(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Delete(&models.Provider{}, id).Error
}

// Count returns total number of providers
func (r *ProviderRepository) Count(ctx context.Context) (int64, error) {
	var count int64
	err := r.db.WithContext(ctx).Model(&models.Provider{}).Count(&count).Error
	return count, err
}

// FindAutoLoadProviders finds all providers with autoLoadModels enabled and not disabled
func (r *ProviderRepository) FindAutoLoadProviders(ctx context.Context) ([]models.Provider, error) {
	var providers []models.Provider
	err := r.db.WithContext(ctx).
		Preload("ProviderTypes").
		Where("autoLoadModels = ?", true).
		Where("disabled = ?", false).
		Find(&providers).Error
	return providers, err
}

// GetModelIDsByProviderID returns all model IDs associated with a provider
func (r *ProviderRepository) GetModelIDsByProviderID(ctx context.Context, providerID uint) ([]uint, error) {
	var modelIDs []uint
	err := r.db.WithContext(ctx).
		Model(&models.ProviderModel{}).
		Where("providerId = ?", providerID).
		Pluck("modelId", &modelIDs).Error
	return modelIDs, err
}

// UnbindAllModels removes all model associations for a provider
func (r *ProviderRepository) UnbindAllModels(ctx context.Context, providerID uint) error {
	return r.db.WithContext(ctx).
		Where("providerId = ?", providerID).
		Delete(&models.ProviderModel{}).Error
}

// UnbindModelFromAllProviders removes all provider associations for a model
func (r *ProviderRepository) UnbindModelFromAllProviders(ctx context.Context, modelID uint) error {
	return r.db.WithContext(ctx).
		Where("modelId = ?", modelID).
		Delete(&models.ProviderModel{}).Error
}

// GetProvidersByModelID returns all provider IDs associated with a model
func (r *ProviderRepository) GetProvidersByModelID(ctx context.Context, modelID uint) ([]uint, error) {
	var providerIDs []uint
	err := r.db.WithContext(ctx).
		Model(&models.ProviderModel{}).
		Where("modelId = ?", modelID).
		Pluck("providerId", &providerIDs).Error
	return providerIDs, err
}

type ChannelRepository struct {
	db *gorm.DB
}

func NewChannelRepository(db *gorm.DB) *ChannelRepository {
	return &ChannelRepository{db: db}
}

func (r *ChannelRepository) FindByID(ctx context.Context, id uint) (*models.Channel, error) {
	var channel models.Channel
	err := r.db.WithContext(ctx).First(&channel, id).Error
	if err != nil {
		return nil, err
	}
	return &channel, nil
}

func (r *ChannelRepository) List(ctx context.Context, userID *uint) ([]models.Channel, error) {
	var channels []models.Channel
	query := r.db.WithContext(ctx)
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Find(&channels).Error
	return channels, err
}

func (r *ChannelRepository) Create(ctx context.Context, channel *models.Channel) error {
	channel.CreatedAt = time.Now()
	channel.UpdatedAt = time.Now()
	return r.db.WithContext(ctx).Create(channel).Error
}

func (r *ChannelRepository) Update(ctx context.Context, channel *models.Channel) error {
	channel.UpdatedAt = time.Now()
	return r.db.WithContext(ctx).Save(channel).Error
}

func (r *ChannelRepository) Delete(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Delete(&models.Channel{}, id).Error
}

func (r *ChannelRepository) BindProviders(ctx context.Context, channelID uint, providerIDs []uint) error {
	r.db.WithContext(ctx).Where("channelId = ?", channelID).Delete(&models.ChannelProvider{})
	for _, providerID := range providerIDs {
		binding := models.ChannelProvider{ChannelID: channelID, ProviderID: providerID}
		if err := r.db.WithContext(ctx).Create(&binding).Error; err != nil {
			return err
		}
	}
	return nil
}

// UnbindAllProviders removes all provider associations for a channel
func (r *ChannelRepository) UnbindAllProviders(ctx context.Context, channelID uint) error {
	return r.db.WithContext(ctx).
		Where("channelId = ?", channelID).
		Delete(&models.ChannelProvider{}).Error
}

// UnbindAllModels removes all model associations for a channel
func (r *ChannelRepository) UnbindAllModels(ctx context.Context, channelID uint) error {
	return r.db.WithContext(ctx).
		Where("channelId = ?", channelID).
		Delete(&models.ChannelAllowedModel{}).Error
}

func (r *ChannelRepository) BindModels(ctx context.Context, channelID uint, modelIDs []uint) error {
	r.db.WithContext(ctx).Where("channelId = ?", channelID).Delete(&models.ChannelAllowedModel{})
	for _, modelID := range modelIDs {
		binding := models.ChannelAllowedModel{ChannelID: channelID, ModelID: modelID}
		if err := r.db.WithContext(ctx).Create(&binding).Error; err != nil {
			return err
		}
	}
	return nil
}

// BindModelToChannel adds a single model binding to a channel (without clearing existing bindings)
func (r *ChannelRepository) BindModelToChannel(ctx context.Context, channelID uint, modelID uint) error {
	binding := models.ChannelAllowedModel{ChannelID: channelID, ModelID: modelID}
	return r.db.WithContext(ctx).Create(&binding).Error
}

func (r *ChannelRepository) GetProviders(ctx context.Context, channelID uint) ([]models.ChannelProvider, error) {
	var providers []models.ChannelProvider
	err := r.db.WithContext(ctx).Where("channelId = ?", channelID).Find(&providers).Error
	return providers, err
}

func (r *ChannelRepository) GetAllowedModels(ctx context.Context, channelID uint) ([]models.ChannelAllowedModel, error) {
	var modelsList []models.ChannelAllowedModel
	err := r.db.WithContext(ctx).Where("channelId = ?", channelID).Find(&modelsList).Error
	return modelsList, err
}

// GetChannelsByModelID finds all channel bindings for a specific model
func (r *ChannelRepository) GetChannelsByModelID(ctx context.Context, modelID uint) ([]models.ChannelAllowedModel, error) {
	var bindings []models.ChannelAllowedModel
	err := r.db.WithContext(ctx).Where("modelId = ?", modelID).Find(&bindings).Error
	return bindings, err
}

// DeleteModelBindings removes all channel associations for a model
func (r *ChannelRepository) DeleteModelBindings(ctx context.Context, modelID uint) error {
	return r.db.WithContext(ctx).
		Where("modelId = ?", modelID).
		Delete(&models.ChannelAllowedModel{}).Error
}

// ChannelWithRelations represents a channel with its associated providers and models
type ChannelWithRelations struct {
	ID               uint                   `json:"id"`
	Name             string                 `json:"name"`
	Enabled          bool                   `json:"enabled"`
	Shared           bool                   `json:"shared"`
	SupportsAllModels bool                  `json:"supportsAllModels"`
	UserID           *uint                  `json:"userId,omitempty"`
	Providers        []ProviderInfo         `json:"providers"`
	AllowedModels    []ModelInfo            `json:"allowedModels"`
	CreatedAt        time.Time              `json:"createdAt"`
	UpdatedAt        time.Time              `json:"updatedAt"`
}

type ProviderInfo struct {
	ID   uint   `json:"id"`
	Name string `json:"name"`
}

type ModelInfo struct {
	ID   uint   `json:"id"`
	Name string `json:"name"`
}

// ListWithRelations returns channels with their associated providers and models
func (r *ChannelRepository) ListWithRelations(ctx context.Context, userID *uint) ([]ChannelWithRelations, error) {
	channels, err := r.List(ctx, userID)
	if err != nil {
		return nil, err
	}

	result := make([]ChannelWithRelations, len(channels))
	for i, ch := range channels {
		result[i] = ChannelWithRelations{
			ID:               ch.ID,
			Name:             ch.Name,
			Enabled:          ch.Enabled,
			Shared:           ch.Shared,
			SupportsAllModels: ch.SupportsAllModels,
			UserID:           ch.UserID,
			CreatedAt:        ch.CreatedAt,
			UpdatedAt:        ch.UpdatedAt,
		}

		// Get providers
		var providerBindings []models.ChannelProvider
		r.db.WithContext(ctx).Where("channelId = ?", ch.ID).Find(&providerBindings)
		if len(providerBindings) > 0 {
			var providerIDs []uint
			for _, b := range providerBindings {
				providerIDs = append(providerIDs, b.ProviderID)
			}
			var providers []models.Provider
			r.db.WithContext(ctx).Where("id IN ?", providerIDs).Find(&providers)
			result[i].Providers = make([]ProviderInfo, len(providers))
			for j, p := range providers {
				result[i].Providers[j] = ProviderInfo{ID: p.ID, Name: p.Name}
			}
		}

		// Get allowed models
		var modelBindings []models.ChannelAllowedModel
		r.db.WithContext(ctx).Where("channelId = ?", ch.ID).Find(&modelBindings)
		if len(modelBindings) > 0 {
			var modelIDs []uint
			for _, b := range modelBindings {
				modelIDs = append(modelIDs, b.ModelID)
			}
			var modelsList []models.Model
			r.db.WithContext(ctx).Where("id IN ?", modelIDs).Find(&modelsList)
			result[i].AllowedModels = make([]ModelInfo, len(modelsList))
			for j, m := range modelsList {
				result[i].AllowedModels[j] = ModelInfo{ID: m.ID, Name: m.Name}
			}
		}
	}

	return result, nil
}

// ListWithRelationsPaginated returns channels with pagination and their associated providers and models
func (r *ChannelRepository) ListWithRelationsPaginated(ctx context.Context, userID *uint, page, pageSize int) ([]ChannelWithRelations, int64, error) {
	// Get total count
	var total int64
	query := r.db.WithContext(ctx).Model(&models.Channel{})
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	// Get paginated channels
	var channels []models.Channel
	offset := (page - 1) * pageSize
	query = r.db.WithContext(ctx)
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	if err := query.Offset(offset).Limit(pageSize).Find(&channels).Error; err != nil {
		return nil, 0, err
	}

	result := make([]ChannelWithRelations, len(channels))
	for i, ch := range channels {
		result[i] = ChannelWithRelations{
			ID:               ch.ID,
			Name:             ch.Name,
			Enabled:          ch.Enabled,
			Shared:           ch.Shared,
			SupportsAllModels: ch.SupportsAllModels,
			UserID:           ch.UserID,
			CreatedAt:        ch.CreatedAt,
			UpdatedAt:        ch.UpdatedAt,
		}

		// Get providers
		var providerBindings []models.ChannelProvider
		r.db.WithContext(ctx).Where("channelId = ?", ch.ID).Find(&providerBindings)
		if len(providerBindings) > 0 {
			var providerIDs []uint
			for _, b := range providerBindings {
				providerIDs = append(providerIDs, b.ProviderID)
			}
			var providers []models.Provider
			r.db.WithContext(ctx).Where("id IN ?", providerIDs).Find(&providers)
			result[i].Providers = make([]ProviderInfo, len(providers))
			for j, p := range providers {
				result[i].Providers[j] = ProviderInfo{ID: p.ID, Name: p.Name}
			}
		}

		// Get allowed models
		var modelBindings []models.ChannelAllowedModel
		r.db.WithContext(ctx).Where("channelId = ?", ch.ID).Find(&modelBindings)
		if len(modelBindings) > 0 {
			var modelIDs []uint
			for _, b := range modelBindings {
				modelIDs = append(modelIDs, b.ModelID)
			}
			var modelsList []models.Model
			r.db.WithContext(ctx).Where("id IN ?", modelIDs).Find(&modelsList)
			result[i].AllowedModels = make([]ModelInfo, len(modelsList))
			for j, m := range modelsList {
				result[i].AllowedModels[j] = ModelInfo{ID: m.ID, Name: m.Name}
			}
		}
	}

	return result, total, nil
}

// FindByIDWithRelations returns a single channel with its associated providers and models
func (r *ChannelRepository) FindByIDWithRelations(ctx context.Context, id uint) (*ChannelWithRelations, error) {
	channel, err := r.FindByID(ctx, id)
	if err != nil {
		return nil, err
	}

	result := &ChannelWithRelations{
		ID:        channel.ID,
		Name:      channel.Name,
		Enabled:   channel.Enabled,
		Shared:    channel.Shared,
		UserID:    channel.UserID,
		CreatedAt: channel.CreatedAt,
		UpdatedAt: channel.UpdatedAt,
	}

	// Get providers
	var providerBindings []models.ChannelProvider
	r.db.WithContext(ctx).Where("channelId = ?", id).Find(&providerBindings)
	if len(providerBindings) > 0 {
		var providerIDs []uint
		for _, b := range providerBindings {
			providerIDs = append(providerIDs, b.ProviderID)
		}
		var providers []models.Provider
		r.db.WithContext(ctx).Where("id IN ?", providerIDs).Find(&providers)
		result.Providers = make([]ProviderInfo, len(providers))
		for j, p := range providers {
			result.Providers[j] = ProviderInfo{ID: p.ID, Name: p.Name}
		}
	}

	// Get allowed models
	var modelBindings []models.ChannelAllowedModel
	r.db.WithContext(ctx).Where("channelId = ?", id).Find(&modelBindings)
	if len(modelBindings) > 0 {
		var modelIDs []uint
		for _, b := range modelBindings {
			modelIDs = append(modelIDs, b.ModelID)
		}
		var modelsList []models.Model
		r.db.WithContext(ctx).Where("id IN ?", modelIDs).Find(&modelsList)
		result.AllowedModels = make([]ModelInfo, len(modelsList))
		for j, m := range modelsList {
			result.AllowedModels[j] = ModelInfo{ID: m.ID, Name: m.Name}
		}
	}

	return result, nil
}