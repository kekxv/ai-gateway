package models

// ChannelProvider - Many-to-many association between Channel and Provider
type ChannelProvider struct {
	ChannelID  uint `gorm:"primaryKey;not null;column:channelId"`
	ProviderID uint `gorm:"primaryKey;not null;column:providerId"`
}

func (ChannelProvider) TableName() string {
	return "ChannelProvider"
}

// GatewayAPIKeyChannel - Many-to-many association between GatewayAPIKey and Channel
type GatewayAPIKeyChannel struct {
	APIKeyID  uint `gorm:"primaryKey;not null;column:apiKeyId"`
	ChannelID uint `gorm:"primaryKey;not null;column:channelId"`
}

func (GatewayAPIKeyChannel) TableName() string {
	return "GatewayApiKeyChannel"
}

// ChannelAllowedModel - Many-to-many association between Channel and Model
type ChannelAllowedModel struct {
	ChannelID uint `gorm:"primaryKey;not null;column:channelId"`
	ModelID   uint `gorm:"primaryKey;not null;column:modelId"`
}

func (ChannelAllowedModel) TableName() string {
	return "ChannelAllowedModel"
}

// ProviderModel - Many-to-many association between Provider and Model
type ProviderModel struct {
	ProviderID uint `gorm:"primaryKey;not null;column:providerId"`
	ModelID    uint `gorm:"primaryKey;not null;column:modelId"`
}

func (ProviderModel) TableName() string {
	return "ProviderModel"
}