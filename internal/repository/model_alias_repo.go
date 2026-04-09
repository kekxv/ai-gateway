package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type ModelAliasRepository struct {
	db *gorm.DB
}

func NewModelAliasRepository(db *gorm.DB) *ModelAliasRepository {
	return &ModelAliasRepository{db: db}
}

// FindByModelID returns all aliases for a model
func (r *ModelAliasRepository) FindByModelID(ctx context.Context, modelID uint) ([]models.ModelAlias, error) {
	var aliases []models.ModelAlias
	err := r.db.WithContext(ctx).Where("modelId = ?", modelID).Find(&aliases).Error
	return aliases, err
}

// FindByAlias returns the model alias record for a given alias string
func (r *ModelAliasRepository) FindByAlias(ctx context.Context, alias string) (*models.ModelAlias, error) {
	var modelAlias models.ModelAlias
	err := r.db.WithContext(ctx).Where("alias = ?", alias).First(&modelAlias).Error
	if err != nil {
		return nil, err
	}
	return &modelAlias, nil
}

// Create creates a new alias for a model
func (r *ModelAliasRepository) Create(ctx context.Context, alias *models.ModelAlias) error {
	return r.db.WithContext(ctx).Create(alias).Error
}

// CreateBatch creates multiple aliases for a model
func (r *ModelAliasRepository) CreateBatch(ctx context.Context, aliases []models.ModelAlias) error {
	if len(aliases) == 0 {
		return nil
	}
	return r.db.WithContext(ctx).Create(&aliases).Error
}

// DeleteByModelID deletes all aliases for a model
func (r *ModelAliasRepository) DeleteByModelID(ctx context.Context, modelID uint) error {
	return r.db.WithContext(ctx).Where("modelId = ?", modelID).Delete(&models.ModelAlias{}).Error
}

// Delete deletes a specific alias
func (r *ModelAliasRepository) Delete(ctx context.Context, modelID uint, alias string) error {
	return r.db.WithContext(ctx).
		Where("modelId = ? AND alias = ?", modelID, alias).
		Delete(&models.ModelAlias{}).Error
}

// UpdateAliases replaces all aliases for a model (except the default name alias)
func (r *ModelAliasRepository) UpdateAliases(ctx context.Context, modelID uint, modelName string, newAliases []string) error {
	// Delete all aliases except the default name
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		// Delete non-name aliases
		if err := tx.Where("modelId = ? AND alias != ?", modelID, modelName).
			Delete(&models.ModelAlias{}).Error; err != nil {
			return err
		}

		// Insert new aliases (skip if it's the same as name)
		for _, alias := range newAliases {
			if alias == modelName {
				continue // Skip name alias, it should already exist
			}
			if err := tx.Create(&models.ModelAlias{
				ModelID: modelID,
				Alias:   alias,
			}).Error; err != nil {
				// Ignore duplicate errors
				if err != gorm.ErrDuplicatedKey {
					return err
				}
			}
		}
		return nil
	})
}

// GetAliases returns the list of alias strings for a model
func (r *ModelAliasRepository) GetAliases(ctx context.Context, modelID uint) ([]string, error) {
	var aliases []string
	err := r.db.WithContext(ctx).
		Model(&models.ModelAlias{}).
		Where("modelId = ?", modelID).
		Pluck("alias", &aliases).Error
	return aliases, err
}