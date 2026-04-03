package repository

import (
	"context"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type ModelRepository struct {
	db *gorm.DB
}

func NewModelRepository(db *gorm.DB) *ModelRepository {
	return &ModelRepository{db: db}
}

func (r *ModelRepository) FindByID(ctx context.Context, id uint) (*models.Model, error) {
	var model models.Model
	err := r.db.WithContext(ctx).First(&model, id).Error
	if err != nil {
		return nil, err
	}
	return &model, nil
}

func (r *ModelRepository) FindByName(ctx context.Context, name string) (*models.Model, error) {
	var model models.Model
	err := r.db.WithContext(ctx).Where("name = ?", name).First(&model).Error
	if err != nil {
		return nil, err
	}
	return &model, nil
}

func (r *ModelRepository) FindByNameOrAlias(ctx context.Context, name string) (*models.Model, error) {
	var model models.Model
	err := r.db.WithContext(ctx).Where("name = ? OR alias = ?", name, name).First(&model).Error
	if err != nil {
		return nil, err
	}
	return &model, nil
}

func (r *ModelRepository) List(ctx context.Context, userID *uint) ([]models.Model, error) {
	var modelsList []models.Model
	query := r.db.WithContext(ctx)
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Find(&modelsList).Error
	return modelsList, err
}

// ListWithRoutes returns models with their associated routes and providers
func (r *ModelRepository) ListWithRoutes(ctx context.Context, userID *uint) ([]models.Model, error) {
	var modelsList []models.Model
	query := r.db.WithContext(ctx).Preload("ModelRoutes.Provider")
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Find(&modelsList).Error
	return modelsList, err
}

// ListWithRoutesPaginated returns models with pagination and their associated routes and providers
func (r *ModelRepository) ListWithRoutesPaginated(ctx context.Context, userID *uint, page, pageSize int) ([]models.Model, int64, error) {
	var modelsList []models.Model
	var total int64

	// Get total count
	query := r.db.WithContext(ctx).Model(&models.Model{})
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	// Get paginated data with routes
	offset := (page - 1) * pageSize
	query = r.db.WithContext(ctx).Preload("ModelRoutes.Provider")
	if userID != nil {
		query = query.Where("userId = ?", *userID)
	}
	err := query.Offset(offset).Limit(pageSize).Find(&modelsList).Error
	return modelsList, total, err
}

func (r *ModelRepository) Create(ctx context.Context, model *models.Model) error {
	return r.db.WithContext(ctx).Create(model).Error
}

func (r *ModelRepository) Update(ctx context.Context, model *models.Model) error {
	model.UpdatedAt = time.Now()
	return r.db.WithContext(ctx).Save(model).Error
}

func (r *ModelRepository) Delete(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Delete(&models.Model{}, id).Error
}

// Count returns total number of models
func (r *ModelRepository) Count(ctx context.Context) (int64, error) {
	var count int64
	err := r.db.WithContext(ctx).Model(&models.Model{}).Count(&count).Error
	return count, err
}

func (r *ModelRepository) UpdatePrices(ctx context.Context, id uint, inputPrice, outputPrice int64) error {
	return r.db.WithContext(ctx).Model(&models.Model{}).Where("id = ?", id).
		Updates(map[string]interface{}{
			"inputTokenPrice":  inputPrice,
			"outputTokenPrice": outputPrice,
			"updatedAt":        time.Now(),
		}).Error
}

func (r *ModelRepository) FindWithRoutes(ctx context.Context, id uint) (*models.Model, error) {
	var model models.Model
	err := r.db.WithContext(ctx).Preload("ModelRoutes.Provider").First(&model, id).Error
	if err != nil {
		return nil, err
	}
	return &model, nil
}

type ModelRouteRepository struct {
	db *gorm.DB
}

func NewModelRouteRepository(db *gorm.DB) *ModelRouteRepository {
	return &ModelRouteRepository{db: db}
}

func (r *ModelRouteRepository) FindEligibleRoutes(ctx context.Context, modelID uint) ([]models.ModelRoute, error) {
	var routes []models.ModelRoute
	err := r.db.WithContext(ctx).
		Preload("Provider").
		Joins("JOIN Provider p ON ModelRoute.providerId = p.id").
		Where("ModelRoute.modelId = ?", modelID).
		Where("p.disabled = FALSE").
		Where("ModelRoute.disabled = FALSE").
		Where("ModelRoute.disabledUntil IS NULL OR ModelRoute.disabledUntil < datetime('now')").
		Find(&routes).Error
	return routes, err
}

func (r *ModelRouteRepository) FindByModel(ctx context.Context, modelID uint) ([]models.ModelRoute, error) {
	var routes []models.ModelRoute
	err := r.db.WithContext(ctx).Preload("Provider").Where("modelId = ?", modelID).Find(&routes).Error
	return routes, err
}

func (r *ModelRouteRepository) Create(ctx context.Context, route *models.ModelRoute) error {
	return r.db.WithContext(ctx).Create(route).Error
}

func (r *ModelRouteRepository) UpdateWeight(ctx context.Context, id uint, weight int) error {
	return r.db.WithContext(ctx).Model(&models.ModelRoute{}).Where("id = ?", id).
		Update("weight", weight).Error
}

func (r *ModelRouteRepository) DisableUntil(ctx context.Context, id uint, until time.Time) error {
	return r.db.WithContext(ctx).Model(&models.ModelRoute{}).Where("id = ?", id).
		Updates(map[string]interface{}{
			"disabledUntil": until,
		}).Error
}

func (r *ModelRouteRepository) CountEligible(ctx context.Context, modelID uint) (int64, error) {
	var count int64
	err := r.db.WithContext(ctx).Model(&models.ModelRoute{}).
		Joins("JOIN Provider p ON ModelRoute.providerId = p.id").
		Where("ModelRoute.modelId = ?", modelID).
		Where("p.disabled = FALSE").
		Where("ModelRoute.disabled = FALSE").
		Where("ModelRoute.disabledUntil IS NULL OR ModelRoute.disabledUntil < datetime('now')").
		Count(&count).Error
	return count, err
}