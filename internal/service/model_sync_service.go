package service

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/utils"
)

// SyncResult represents the result of a provider model sync
type SyncResult struct {
	ProviderID     uint
	ProviderName   string
	ModelsCreated  int
	RoutesCreated  int
	ModelsRemoved  int
	RoutesRemoved  int
	TotalFetched   int
	Error          error
}

// ModelSyncService handles syncing models from providers
type ModelSyncService struct {
	providerRepo   *repository.ProviderRepository
	modelRepo      *repository.ModelRepository
	modelRouteRepo *repository.ModelRouteRepository
	httpClient     *http.Client
	proxyConfig    *ProxyConfig
}

// NewModelSyncService creates a new model sync service
func NewModelSyncService(
	providerRepo *repository.ProviderRepository,
	modelRepo *repository.ModelRepository,
	modelRouteRepo *repository.ModelRouteRepository,
	proxyConfig *ProxyConfig,
) *ModelSyncService {
	// Create custom transport with proxy bypass support
	transport := &http.Transport{
		Proxy: func(req *http.Request) (*url.URL, error) {
			if utils.ShouldBypassProxy(req.URL.String(), proxyConfig.NoProxy) {
				return nil, nil // Bypass proxy for matched URLs
			}
			return http.ProxyFromEnvironment(req)
		},
	}

	return &ModelSyncService{
		providerRepo:   providerRepo,
		modelRepo:      modelRepo,
		modelRouteRepo: modelRouteRepo,
		httpClient:     &http.Client{Timeout: 30 * time.Second, Transport: transport},
		proxyConfig:    proxyConfig,
	}
}

// SyncProviderModels syncs models for a specific provider
func (s *ModelSyncService) SyncProviderModels(ctx context.Context, providerID uint) *SyncResult {
	result := &SyncResult{
		ProviderID: providerID,
	}

	provider, err := s.providerRepo.FindByID(ctx, providerID)
	if err != nil {
		result.Error = fmt.Errorf("provider not found: %w", err)
		return result
	}

	result.ProviderName = provider.Name

	// Check if autoLoadModels is enabled
	if !provider.AutoLoadModels {
		result.Error = fmt.Errorf("provider %s does not have autoLoadModels enabled", provider.Name)
		return result
	}

	// Fetch models from provider
	fetchedModels, err := s.fetchModels(provider)
	if err != nil {
		result.Error = fmt.Errorf("failed to fetch models: %w", err)
		return result
	}

	result.TotalFetched = len(fetchedModels)

	// Get existing routes for this provider
	existingRoutes, _ := s.modelRouteRepo.FindByProviderID(ctx, providerID)
	existingRouteMap := make(map[uint]models.ModelRoute)
	for _, route := range existingRoutes {
		existingRouteMap[route.ModelID] = route
	}

	// Track remote model names
	remoteModelNames := make(map[string]bool)

	// Process remote models
	for _, m := range fetchedModels {
		modelName, ok := m["name"].(string)
		if !ok {
			continue
		}
		remoteModelNames[modelName] = true

		// Check if model exists (by name first, then by alias)
		existingModel, _ := s.modelRepo.FindByName(ctx, modelName)
		if existingModel == nil {
			existingModel, _ = s.modelRepo.FindByNameOrAlias(ctx, modelName)
		}
		if existingModel == nil {
			// Create new model
			description := ""
			if desc, ok := m["description"].(string); ok {
				description = desc
			}

			newModel := &models.Model{
				Name:        modelName,
				Description: description,
				CreatedAt:   time.Now(),
				UpdatedAt:   time.Now(),
			}
			if err := s.modelRepo.Create(ctx, newModel); err != nil {
				continue
			}
			existingModel = newModel
			result.ModelsCreated++
		}

		// Check if route exists
		if _, hasRoute := existingRouteMap[existingModel.ID]; !hasRoute {
			// Create route
			route := &models.ModelRoute{
				ModelID:    existingModel.ID,
				ProviderID: providerID,
				Weight:     1,
				CreatedAt:  time.Now(),
			}
			if err := s.modelRouteRepo.Create(ctx, route); err == nil {
				result.RoutesCreated++
			}
		}
	}

	// Remove models that no longer exist remotely
	for _, route := range existingRoutes {
		model, err := s.modelRepo.FindByID(ctx, route.ModelID)

		// Handle orphan routes (model not found in database)
		if err != nil || model == nil {
			s.modelRouteRepo.Delete(ctx, route.ID)
			result.RoutesRemoved++
			continue
		}

		// Check if model exists in remote
		if !remoteModelNames[model.Name] {
			// Check if model has other provider associations
			otherRoutes, _ := s.modelRouteRepo.FindByModel(ctx, model.ID)
			hasOtherProvider := false
			for _, r := range otherRoutes {
				if r.ProviderID != providerID {
					hasOtherProvider = true
					break
				}
			}

			// Delete the route
			s.modelRouteRepo.Delete(ctx, route.ID)
			result.RoutesRemoved++

			// Only delete model if no other associations
			if !hasOtherProvider && len(otherRoutes) <= 1 {
				s.modelRepo.Delete(ctx, model.ID)
				result.ModelsRemoved++
			}
		}
	}

	return result
}

// SyncAllProviders syncs models for all providers with autoLoadModels enabled
func (s *ModelSyncService) SyncAllProviders(ctx context.Context) []SyncResult {
	providers, err := s.providerRepo.FindAutoLoadProviders(ctx)
	if err != nil {
		return []SyncResult{{Error: fmt.Errorf("failed to find auto-load providers: %w", err)}}
	}

	results := make([]SyncResult, len(providers))
	for i, provider := range providers {
		results[i] = *s.SyncProviderModels(ctx, provider.ID)
	}

	return results
}

// Name returns the task name for scheduler (implements ScheduledTask interface)
func (s *ModelSyncService) Name() string {
	return "model_sync"
}

// Run executes the sync task (implements ScheduledTask interface)
func (s *ModelSyncService) Run(ctx context.Context) {
	results := s.SyncAllProviders(ctx)
	for _, result := range results {
		if result.Error != nil {
			fmt.Printf("[ModelSync] Provider %d (%s): ERROR - %v\n",
				result.ProviderID, result.ProviderName, result.Error)
		} else {
			fmt.Printf("[ModelSync] Provider %d (%s): created=%d, routes=%d, removed=%d, fetched=%d\n",
				result.ProviderID, result.ProviderName,
				result.ModelsCreated, result.RoutesCreated,
				result.ModelsRemoved, result.TotalFetched)
		}
	}
}

// fetchModels fetches models from a provider based on its type
func (s *ModelSyncService) fetchModels(provider *models.Provider) ([]map[string]interface{}, error) {
	switch strings.ToLower(provider.Type) {
	case "gemini":
		return s.fetchGeminiModels(provider.BaseURL, provider.APIKey)
	default:
		// OpenAI-compatible API (including OpenAI, Anthropic, custom)
		return s.fetchOpenAIModels(provider.BaseURL, provider.APIKey)
	}
}

// fetchOpenAIModels fetches models from an OpenAI-compatible API
func (s *ModelSyncService) fetchOpenAIModels(baseURL, apiKey string) ([]map[string]interface{}, error) {
	modelsURL := strings.TrimSuffix(baseURL, "/") + "/models"

	req, err := http.NewRequest("GET", modelsURL, nil)
	if err != nil {
		return nil, err
	}

	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("provider returned status %d", resp.StatusCode)
	}

	var result struct {
		Data []struct {
			ID      string `json:"id"`
			Object  string `json:"object"`
			OwnedBy string `json:"owned_by"`
		} `json:"data"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	models := make([]map[string]interface{}, len(result.Data))
	for i, m := range result.Data {
		models[i] = map[string]interface{}{
			"id":          m.ID,
			"name":        m.ID,
			"description": m.Object,
			"owned_by":    m.OwnedBy,
		}
	}

	return models, nil
}

// fetchGeminiModels fetches models from Gemini API
func (s *ModelSyncService) fetchGeminiModels(baseURL, apiKey string) ([]map[string]interface{}, error) {
	// Gemini uses different API endpoint
	geminiURL := strings.TrimSuffix(baseURL, "/")
	if !strings.Contains(geminiURL, "/v1beta") {
		geminiURL = geminiURL + "/v1beta"
	}
	geminiURL = geminiURL + "/models"

	req, err := http.NewRequest("GET", geminiURL, nil)
	if err != nil {
		return nil, err
	}

	if apiKey != "" {
		req.Header.Set("x-goog-api-key", apiKey)
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("gemini returned status %d", resp.StatusCode)
	}

	var result struct {
		Models []struct {
			Name        string `json:"name"`
			DisplayName string `json:"displayName"`
			Description string `json:"description"`
		} `json:"models"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	models := make([]map[string]interface{}, len(result.Models))
	for i, m := range result.Models {
		models[i] = map[string]interface{}{
			"id":          m.Name,
			"name":        m.DisplayName,
			"description": m.Description,
		}
	}

	return models, nil
}