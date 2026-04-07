package repository

import (
	"context"

	"github.com/kekxv/ai-gateway/internal/models"
	"gorm.io/gorm"
)

// MessageRepository handles message database operations
type MessageRepository struct {
	db *gorm.DB
}

// NewMessageRepository creates a new message repository
func NewMessageRepository(db *gorm.DB) *MessageRepository {
	return &MessageRepository{db: db}
}

// Create creates a new message
func (r *MessageRepository) Create(ctx context.Context, message *models.Message) error {
	return r.db.WithContext(ctx).Create(message).Error
}

// GetByConversationID gets all messages for a conversation
func (r *MessageRepository) GetByConversationID(ctx context.Context, conversationID uint) ([]models.Message, error) {
	var messages []models.Message
	err := r.db.WithContext(ctx).
		Where("conversation_id = ?", conversationID).
		Order("id ASC").
		Find(&messages).Error
	return messages, err
}

// DeleteByConversationID deletes all messages for a conversation
func (r *MessageRepository) DeleteByConversationID(ctx context.Context, conversationID uint) error {
	return r.db.WithContext(ctx).
		Where("conversation_id = ?", conversationID).
		Delete(&models.Message{}).Error
}

// GetLastMessage gets the last message in a conversation
func (r *MessageRepository) GetLastMessage(ctx context.Context, conversationID uint) (*models.Message, error) {
	var message models.Message
	err := r.db.WithContext(ctx).
		Where("conversation_id = ?", conversationID).
		Order("created_at DESC").
		First(&message).Error
	if err != nil {
		return nil, err
	}
	return &message, nil
}

// DeleteAfterID deletes all messages after a specific message ID in a conversation
func (r *MessageRepository) DeleteAfterID(ctx context.Context, conversationID uint, messageID uint) error {
	return r.db.WithContext(ctx).
		Where("conversation_id = ? AND id > ?", conversationID, messageID).
		Delete(&models.Message{}).Error
}