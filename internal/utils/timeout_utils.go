package utils

import (
	"context"
	"net/http"
	"time"
)

// TimeoutConfig holds timeout settings
type TimeoutConfig struct {
	Connection time.Duration
	Response   time.Duration
	Total      time.Duration
	ModelLoad  time.Duration
}

// DefaultTimeoutConfig returns default timeout settings
func DefaultTimeoutConfig() *TimeoutConfig {
	return &TimeoutConfig{
		Connection: 30 * time.Second,
		Response:   180 * time.Second,
		Total:      240 * time.Second,
		ModelLoad:  30 * time.Second,
	}
}

// CreateTimeoutContext creates a context with timeout
func CreateTimeoutContext(timeout time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), timeout)
}

// CreateTimeoutClient creates an HTTP client with timeout
func CreateTimeoutClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			ResponseHeaderTimeout: timeout,
		},
	}
}