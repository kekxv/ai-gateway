package service

import (
	"sync"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
)

// ResponseCacheEntry stores the mapping between response ID and provider
type ResponseCacheEntry struct {
	ProviderID  uint
	ProviderURL string
	ProviderKey string
	CreatedAt   time.Time
}

// ResponseCache is a simple in-memory cache for response ID to provider mapping
type ResponseCache struct {
	entries map[string]ResponseCacheEntry
	mu      sync.RWMutex
	ttl     time.Duration
}

// NewResponseCache creates a new response cache with specified TTL
func NewResponseCache(ttl time.Duration) *ResponseCache {
	cache := &ResponseCache{
		entries: make(map[string]ResponseCacheEntry),
		ttl:     ttl,
	}
	// Start cleanup goroutine
	go cache.cleanup()
	return cache
}

// Set stores a response ID to provider mapping
// baseURL should be the type-specific base URL to use for subsequent requests
func (c *ResponseCache) Set(responseID string, provider *models.Provider, baseURL string) {
	if baseURL == "" {
		baseURL = provider.BaseURL // fallback to default
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries[responseID] = ResponseCacheEntry{
		ProviderID:  provider.ID,
		ProviderURL: baseURL,
		ProviderKey: provider.APIKey,
		CreatedAt:   time.Now(),
	}
}

// Get retrieves the provider info for a response ID
func (c *ResponseCache) Get(responseID string) *ResponseCacheEntry {
	c.mu.RLock()
	defer c.mu.RUnlock()
	entry, ok := c.entries[responseID]
	if !ok {
		return nil
	}
	// Check if expired
	if time.Since(entry.CreatedAt) > c.ttl {
		return nil
	}
	return &entry
}

// Delete removes a response ID from cache
func (c *ResponseCache) Delete(responseID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.entries, responseID)
}

// cleanup periodically removes expired entries
func (c *ResponseCache) cleanup() {
	ticker := time.NewTicker(1 * time.Hour)
	for range ticker.C {
		c.mu.Lock()
		for id, entry := range c.entries {
			if time.Since(entry.CreatedAt) > c.ttl {
				delete(c.entries, id)
			}
		}
		c.mu.Unlock()
	}
}