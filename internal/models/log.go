package models

import (
	"time"
)

type Log struct {
	ID               uint      `gorm:"primaryKey" json:"id"`
	Latency          int       `gorm:"column:latency;not null" json:"latency"`
	PromptTokens     int       `gorm:"column:promptTokens;default:0;not null" json:"promptTokens"`
	CompletionTokens int       `gorm:"column:completionTokens;default:0;not null" json:"completionTokens"`
	CacheReadTokens  int       `gorm:"column:cacheReadTokens;default:0" json:"cacheReadTokens"`
	CacheWriteTokens int       `gorm:"column:cacheWriteTokens;default:0" json:"cacheWriteTokens"`
	TotalTokens      int       `gorm:"column:totalTokens;default:0;not null" json:"totalTokens"`
	Cost             int64     `gorm:"column:cost;default:0;not null" json:"cost"`
	Status           int       `gorm:"column:status;default:200;not null" json:"status"`
	ErrorMessage     string    `gorm:"column:errorMessage" json:"errorMessage"`
	APIKeyID         *uint     `gorm:"index;column:apiKeyId" json:"apiKeyId"` // Nullable for chat requests
	APIKey           *GatewayAPIKey `gorm:"foreignKey:APIKeyID;constraint:OnDelete:SET NULL" json:"apiKey,omitempty"`
	ModelName        string    `gorm:"column:modelName" json:"modelName"`
	ProviderName     string    `gorm:"column:providerName" json:"providerName"`
	OwnerChannelID   *uint     `gorm:"column:ownerChannelId" json:"ownerChannelId"`
	OwnerChannel     *Channel  `gorm:"foreignKey:OwnerChannelID" json:"ownerChannel,omitempty"`
	OwnerChannelUserID *uint   `gorm:"column:ownerChannelUserId" json:"ownerChannelUserId"`
	RequestPath      string    `gorm:"column:requestPath;type:varchar(255)" json:"requestPath"`
	RequestHeaders   string    `gorm:"column:requestHeaders;type:text" json:"requestHeaders"`  // JSON format
	ResponseHeaders  string    `gorm:"column:responseHeaders;type:text" json:"responseHeaders"` // JSON format
	CreatedAt        time.Time `gorm:"column:createdAt;index" json:"createdAt"`
}

func (Log) TableName() string {
	return "Log"
}