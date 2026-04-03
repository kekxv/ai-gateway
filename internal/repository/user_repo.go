package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

type UserRepository struct {
	db *gorm.DB
}

func NewUserRepository(db *gorm.DB) *UserRepository {
	return &UserRepository{db: db}
}

func (r *UserRepository) FindByID(ctx context.Context, id uint) (*models.User, error) {
	var user models.User
	err := r.db.WithContext(ctx).First(&user, id).Error
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) FindByEmail(ctx context.Context, email string) (*models.User, error) {
	var user models.User
	err := r.db.WithContext(ctx).Where("email = ?", email).First(&user).Error
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) List(ctx context.Context) ([]models.User, error) {
	var users []models.User
	err := r.db.WithContext(ctx).Find(&users).Error
	return users, err
}

// ListWithCount returns users with pagination support
func (r *UserRepository) ListWithCount(ctx context.Context, page, pageSize int) ([]models.User, int64, error) {
	var users []models.User
	var total int64

	// Get total count
	if err := r.db.WithContext(ctx).Model(&models.User{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}

	// Get paginated data
	offset := (page - 1) * pageSize
	err := r.db.WithContext(ctx).Offset(offset).Limit(pageSize).Find(&users).Error
	return users, total, err
}

func (r *UserRepository) Create(ctx context.Context, user *models.User) error {
	return r.db.WithContext(ctx).Create(user).Error
}

func (r *UserRepository) Update(ctx context.Context, user *models.User) error {
	return r.db.WithContext(ctx).Save(user).Error
}

func (r *UserRepository) Delete(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Delete(&models.User{}, id).Error
}

func (r *UserRepository) UpdateBalance(ctx context.Context, id uint, amount int64) error {
	return r.db.WithContext(ctx).Model(&models.User{}).Where("id = ?", id).
		Update("balance", gorm.Expr("balance + ?", amount)).Error
}

func (r *UserRepository) SubtractBalance(ctx context.Context, id uint, amount int64) error {
	return r.db.WithContext(ctx).Model(&models.User{}).Where("id = ?", id).
		Update("balance", gorm.Expr("balance - ?", amount)).Error
}

func (r *UserRepository) Count(ctx context.Context) (int64, error) {
	var count int64
	err := r.db.WithContext(ctx).Model(&models.User{}).Count(&count).Error
	return count, err
}