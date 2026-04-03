package config

import (
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	Server   ServerConfig
	Database DatabaseConfig
	Auth     AuthConfig
	Timeout  TimeoutConfig
	Proxy    ProxyConfig
}

type ServerConfig struct {
	Port int
	Mode string
}

type DatabaseConfig struct {
	Path string
}

type AuthConfig struct {
	JWTSecret  string
	JWTExpiry  time.Duration
}

type TimeoutConfig struct {
	Connection time.Duration
	Response   time.Duration
	Total      time.Duration
	ModelLoad  time.Duration
}

type ProxyConfig struct {
	HTTPProxy  string
	HTTPSProxy string
	NoProxy    string
}

func Load(configPath string) (*Config, error) {
	viper.SetConfigFile(configPath)
	viper.AutomaticEnv()

	// Set default values
	viper.SetDefault("server.port", 3000)
	viper.SetDefault("server.mode", "release")
	viper.SetDefault("database.path", "ai-gateway.db")
	viper.SetDefault("auth.jwt_expiry", 8*time.Hour)
	viper.SetDefault("timeout.connection", "30s")
	viper.SetDefault("timeout.response", "180s")
	viper.SetDefault("timeout.total", "240s")
	viper.SetDefault("timeout.model_load", "30s")

	if err := viper.ReadInConfig(); err != nil {
		return nil, err
	}

	var config Config
	if err := viper.Unmarshal(&config); err != nil {
		return nil, err
	}

	// Ensure JWT expiry is set
	if config.Auth.JWTExpiry == 0 {
		config.Auth.JWTExpiry = 8 * time.Hour
	}

	return &config, nil
}