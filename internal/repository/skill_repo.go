package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type SkillRepository struct {
	db *gorm.DB
}

func NewSkillRepository(db *gorm.DB) *SkillRepository {
	return &SkillRepository{db: db}
}

// FindByID finds a skill by ID
func (r *SkillRepository) FindByID(ctx context.Context, id uint) (*models.Skill, error) {
	var skill models.Skill
	err := r.db.WithContext(ctx).First(&skill, id).Error
	if err != nil {
		return nil, err
	}
	return &skill, nil
}

// FindByIDWithResources finds a skill with its resources preloaded
func (r *SkillRepository) FindByIDWithResources(ctx context.Context, id uint) (*models.Skill, error) {
	var skill models.Skill
	err := r.db.WithContext(ctx).
		Preload("SkillResources").
		First(&skill, id).Error
	if err != nil {
		return nil, err
	}
	return &skill, nil
}

// FindByName finds a skill by name for a specific user
func (r *SkillRepository) FindByName(ctx context.Context, userID uint, name string) (*models.Skill, error) {
	var skill models.Skill
	err := r.db.WithContext(ctx).
		Where("user_id = ? AND name = ?", userID, name).
		First(&skill).Error
	if err != nil {
		return nil, err
	}
	return &skill, nil
}

// List lists all skills for a user
func (r *SkillRepository) List(ctx context.Context, userID uint) ([]models.Skill, error) {
	var skills []models.Skill
	err := r.db.WithContext(ctx).
		Where("user_id = ?", userID).
		Order("name ASC").
		Find(&skills).Error
	return skills, err
}

// ListEnabled lists all enabled skills (for catalog)
func (r *SkillRepository) ListEnabled(ctx context.Context, userID uint) ([]models.Skill, error) {
	var skills []models.Skill
	err := r.db.WithContext(ctx).
		Where("user_id = ? AND enabled = ?", userID, true).
		Order("name ASC").
		Find(&skills).Error
	return skills, err
}

// GetCatalog returns lightweight catalog items (Tier 1 disclosure)
func (r *SkillRepository) GetCatalog(ctx context.Context, userID uint) ([]models.SkillCatalogItem, error) {
	var items []models.SkillCatalogItem
	err := r.db.WithContext(ctx).
		Model(&models.Skill{}).
		Select("name, description, location, source, enabled").
		Where("user_id = ?", userID).
		Order("name ASC").
		Scan(&items).Error
	return items, err
}

// Create creates a new skill
func (r *SkillRepository) Create(ctx context.Context, skill *models.Skill) error {
	return r.db.WithContext(ctx).Create(skill).Error
}

// Update updates a skill
func (r *SkillRepository) Update(ctx context.Context, skill *models.Skill) error {
	return r.db.WithContext(ctx).Save(skill).Error
}

// Delete deletes a skill and its resources
func (r *SkillRepository) Delete(ctx context.Context, id uint) error {
	// Delete resources first
	if err := r.db.WithContext(ctx).Where("skill_id = ?", id).Delete(&models.SkillResource{}).Error; err != nil {
		return err
	}
	return r.db.WithContext(ctx).Delete(&models.Skill{}, id).Error
}

// CreateResource creates a skill resource
func (r *SkillRepository) CreateResource(ctx context.Context, resource *models.SkillResource) error {
	return r.db.WithContext(ctx).Create(resource).Error
}

// DeleteResources deletes all resources for a skill
func (r *SkillRepository) DeleteResources(ctx context.Context, skillID uint) error {
	return r.db.WithContext(ctx).Where("skill_id = ?", skillID).Delete(&models.SkillResource{}).Error
}

// ListResources lists all resources for a skill
func (r *SkillRepository) ListResources(ctx context.Context, skillID uint) ([]models.SkillResource, error) {
	var resources []models.SkillResource
	err := r.db.WithContext(ctx).
		Where("skill_id = ?", skillID).
		Order("type ASC, name ASC").
		Find(&resources).Error
	return resources, err
}