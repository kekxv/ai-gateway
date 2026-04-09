package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type ProviderTypeRepository struct {
	db *gorm.DB
}

func NewProviderTypeRepository(db *gorm.DB) *ProviderTypeRepository {
	return &ProviderTypeRepository{db: db}
}

// FindByProviderID returns all provider types for a given provider
func (r *ProviderTypeRepository) FindByProviderID(ctx context.Context, providerID uint) ([]models.ProviderType, error) {
	var types []models.ProviderType
	err := r.db.WithContext(ctx).
		Where("providerId = ?", providerID).
		Order("type").
		Find(&types).Error
	return types, err
}

// FindByProviderAndType returns a specific provider type configuration
func (r *ProviderTypeRepository) FindByProviderAndType(ctx context.Context, providerID uint, typeName string) (*models.ProviderType, error) {
	var pt models.ProviderType
	err := r.db.WithContext(ctx).
		Where("providerId = ? AND type = ?", providerID, typeName).
		First(&pt).Error
	if err != nil {
		return nil, err
	}
	return &pt, nil
}

// Create creates a new provider type
func (r *ProviderTypeRepository) Create(ctx context.Context, pt *models.ProviderType) error {
	return r.db.WithContext(ctx).Create(pt).Error
}

// Update updates an existing provider type
func (r *ProviderTypeRepository) Update(ctx context.Context, pt *models.ProviderType) error {
	return r.db.WithContext(ctx).Save(pt).Error
}

// DeleteByProviderID deletes all provider types for a given provider
func (r *ProviderTypeRepository) DeleteByProviderID(ctx context.Context, providerID uint) error {
	return r.db.WithContext(ctx).
		Where("providerId = ?", providerID).
		Delete(&models.ProviderType{}).Error
}

// UpdateProviderTypes replaces all provider types for a given provider
func (r *ProviderTypeRepository) UpdateProviderTypes(ctx context.Context, providerID uint, types []models.ProviderType) error {
	// Delete existing types
	if err := r.DeleteByProviderID(ctx, providerID); err != nil {
		return err
	}

	// Create new types
	if len(types) == 0 {
		return nil
	}

	for i := range types {
		types[i].ProviderID = providerID
	}

	return r.db.WithContext(ctx).Create(&types).Error
}

// GetBaseURLByType returns the base URL for a specific type, or empty string if not found
func (r *ProviderTypeRepository) GetBaseURLByType(ctx context.Context, providerID uint, typeName string) (string, error) {
	var baseURL string
	err := r.db.WithContext(ctx).
		Model(&models.ProviderType{}).
		Where("providerId = ? AND type = ?", providerID, typeName).
		Select("baseURL").
		First(&baseURL).Error
	if err == gorm.ErrRecordNotFound {
		return "", nil
	}
	return baseURL, err
}