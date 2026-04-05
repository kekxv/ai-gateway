package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

// ConversationRepository handles conversation database operations
type ConversationRepository struct {
	db *gorm.DB
}

// NewConversationRepository creates a new conversation repository
func NewConversationRepository(db *gorm.DB) *ConversationRepository {
	return &ConversationRepository{db: db}
}

// Create creates a new conversation
func (r *ConversationRepository) Create(ctx context.Context, conversation *models.Conversation) error {
	return r.db.WithContext(ctx).Create(conversation).Error
}

// GetByID gets a conversation by ID
func (r *ConversationRepository) GetByID(ctx context.Context, id uint) (*models.Conversation, error) {
	var conversation models.Conversation
	err := r.db.WithContext(ctx).First(&conversation, id).Error
	if err != nil {
		return nil, err
	}
	return &conversation, nil
}

// GetByUserID gets all conversations for a user
func (r *ConversationRepository) GetByUserID(ctx context.Context, userID uint) ([]models.Conversation, error) {
	var conversations []models.Conversation
	err := r.db.WithContext(ctx).
		Where("user_id = ?", userID).
		Order("updated_at DESC").
		Find(&conversations).Error
	return conversations, err
}

// Update updates a conversation
func (r *ConversationRepository) Update(ctx context.Context, conversation *models.Conversation) error {
	return r.db.WithContext(ctx).Save(conversation).Error
}

// Delete deletes a conversation
func (r *ConversationRepository) Delete(ctx context.Context, id uint) error {
	return r.db.WithContext(ctx).Delete(&models.Conversation{}, id).Error
}

// DeleteByUserID deletes all conversations for a user
func (r *ConversationRepository) DeleteByUserID(ctx context.Context, userID uint) error {
	return r.db.WithContext(ctx).Where("user_id = ?", userID).Delete(&models.Conversation{}).Error
}

// UpdateTitle updates the title of a conversation
func (r *ConversationRepository) UpdateTitle(ctx context.Context, id uint, title string) error {
	return r.db.WithContext(ctx).
		Model(&models.Conversation{}).
		Where("id = ?", id).
		Update("title", title).Error
}