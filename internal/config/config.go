package config

import (
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	Server    ServerConfig
	Database  DatabaseConfig
	Auth      AuthConfig
	Timeout   TimeoutConfig
	Proxy     ProxyConfig
	Scheduler SchedulerConfig
	LogCleanup LogCleanupConfig
}

type LogCleanupConfig struct {
	Enabled         bool
	DetailRetention time.Duration // 保留LogDetail的时间（默认30天）
	Interval        time.Duration // 清理任务执行间隔（默认24小时）
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

type SchedulerConfig struct {
	Enabled      bool
	SyncInterval time.Duration
	InitialDelay time.Duration
}

func Load(configPath string) (*Config, error) {
	viper.SetConfigFile(configPath)
	viper.AutomaticEnv()

	// Bind specific environment variables to config keys
	viper.BindEnv("database.path", "DATABASE_URL")
	viper.BindEnv("proxy.http_proxy", "HTTP_PROXY")
	viper.BindEnv("proxy.https_proxy", "HTTPS_PROXY")
	viper.BindEnv("proxy.no_proxy", "NO_PROXY")
	viper.BindEnv("auth.jwt_secret", "JWT_SECRET")

	// Set default values
	viper.SetDefault("server.port", 3000)
	viper.SetDefault("server.mode", "release")
	viper.SetDefault("database.path", "ai-gateway.db")
	viper.SetDefault("auth.jwt_expiry", 8*time.Hour)
	viper.SetDefault("timeout.connection", "30s")
	viper.SetDefault("timeout.response", "180s")
	viper.SetDefault("timeout.total", "240s")
	viper.SetDefault("timeout.model_load", "30s")

	// Scheduler defaults
	viper.SetDefault("scheduler.enabled", true)
	viper.SetDefault("scheduler.sync_interval", "1h")
	viper.SetDefault("scheduler.initial_delay", "10s")

	// LogCleanup defaults
	viper.SetDefault("logCleanup.enabled", true)
	viper.SetDefault("logCleanup.detailRetention", "720h") // 30 days
	viper.SetDefault("logCleanup.interval", "24h")        // Daily cleanup

	// Bind environment variables
	viper.BindEnv("logCleanup.enabled", "LOG_CLEANUP_ENABLED")
	viper.BindEnv("logCleanup.detailRetention", "LOG_DETAIL_RETENTION")
	viper.BindEnv("logCleanup.interval", "LOG_CLEANUP_INTERVAL")

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

	// Ensure scheduler defaults are set
	if config.Scheduler.SyncInterval == 0 {
		config.Scheduler.SyncInterval = 1 * time.Hour
	}
	if config.Scheduler.InitialDelay == 0 {
		config.Scheduler.InitialDelay = 10 * time.Second
	}

	// Ensure logCleanup defaults are set
	if config.LogCleanup.DetailRetention == 0 {
		config.LogCleanup.DetailRetention = 720 * time.Hour // 30 days
	}
	if config.LogCleanup.Interval == 0 {
		config.LogCleanup.Interval = 24 * time.Hour // Daily
	}

	return &config, nil
}