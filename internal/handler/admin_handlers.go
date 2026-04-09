package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/service"
)

type ProviderHandler struct {
	providerRepo     *repository.ProviderRepository
	modelRepo        *repository.ModelRepository
	modelRouteRepo   *repository.ModelRouteRepository
	modelSyncService *service.ModelSyncService
}

func NewProviderHandler(providerRepo *repository.ProviderRepository, modelRepo *repository.ModelRepository, modelRouteRepo *repository.ModelRouteRepository, modelSyncService *service.ModelSyncService) *ProviderHandler {
	return &ProviderHandler{
		providerRepo:     providerRepo,
		modelRepo:        modelRepo,
		modelRouteRepo:   modelRouteRepo,
		modelSyncService: modelSyncService,
	}
}

func (h *ProviderHandler) ListProviders(c *gin.Context) {
	providers, err := h.providerRepo.List(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	// Mask API keys and populate TypesList
	for i := range providers {
		providers[i].APIKeyMasked = models.MaskAPIKey(providers[i].APIKey)
		providers[i].TypesList = providers[i].GetTypes()
	}
	c.JSON(http.StatusOK, providers)
}

func (h *ProviderHandler) CreateProvider(c *gin.Context) {
	var req struct {
		Name               string   `json:"name" binding:"required"`
		BaseURL            string   `json:"baseURL"`
		BaseURLSnake       string   `json:"base_url"`
		APIKey             string   `json:"apiKey"`
		APIKeySnake        string   `json:"api_key"`
		Type               string   `json:"type"`
		Types              string   `json:"types"`     // JSON array string
		TypesList          []string `json:"typesList"` // Array format
		AutoLoadModels     bool     `json:"autoLoadModels"`
		AutoLoadModelsSnake bool    `json:"auto_load_models"`
		Disabled           bool     `json:"disabled"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Support both camelCase and snake_case
	baseURL := req.BaseURL
	if baseURL == "" {
		baseURL = req.BaseURLSnake
	}
	apiKey := req.APIKey
	if apiKey == "" {
		apiKey = req.APIKeySnake
	}
	autoLoadModels := req.AutoLoadModels || req.AutoLoadModelsSnake

	provider := &models.Provider{
		Name:           req.Name,
		BaseURL:        baseURL,
		APIKey:         apiKey,
		Type:           req.Type,
		AutoLoadModels: autoLoadModels,
		Disabled:       req.Disabled,
		CreatedAt:      time.Now(),
	}

	// Handle Types array
	if len(req.TypesList) > 0 {
		provider.SetTypes(req.TypesList)
	} else if req.Types != "" {
		provider.Types = req.Types
		provider.TypesList = provider.GetTypes()
	} else if req.Type != "" {
		provider.SetTypes([]string{req.Type})
	} else {
		provider.SetTypes([]string{"openai"}) // Default
	}

	if err := h.providerRepo.Create(c.Request.Context(), provider); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Mask API key in response and populate TypesList
	provider.APIKeyMasked = models.MaskAPIKey(provider.APIKey)
	provider.TypesList = provider.GetTypes()
	c.JSON(http.StatusCreated, provider)
}

func (h *ProviderHandler) GetProvider(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	provider, err := h.providerRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
		return
	}

	// Mask API key in response
	provider.APIKeyMasked = models.MaskAPIKey(provider.APIKey)
	c.JSON(http.StatusOK, provider)
}

func (h *ProviderHandler) UpdateProvider(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Name               string   `json:"name"`
		BaseURL            string   `json:"baseURL"`
		BaseURLSnake       string   `json:"base_url"`
		APIKey             string   `json:"apiKey"`
		APIKeySnake        string   `json:"api_key"`
		Type               string   `json:"type"`
		Types              string   `json:"types"`     // JSON array string
		TypesList          []string `json:"typesList"` // Array format
		AutoLoadModels     bool     `json:"autoLoadModels"`
		AutoLoadModelsSnake bool    `json:"auto_load_models"`
		Disabled           bool     `json:"disabled"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	provider, err := h.providerRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
		return
	}

	if req.Name != "" {
		provider.Name = req.Name
	}
	// Support both camelCase and snake_case
	baseURL := req.BaseURL
	if baseURL == "" {
		baseURL = req.BaseURLSnake
	}
	if baseURL != "" {
		provider.BaseURL = baseURL
	}
	// Support both camelCase and snake_case
	apiKey := req.APIKey
	if apiKey == "" {
		apiKey = req.APIKeySnake
	}
	// Only update APIKey if a new value is provided
		if apiKey != "" {
			provider.APIKey = apiKey
		}
	// Handle Types array
	if len(req.TypesList) > 0 {
		provider.SetTypes(req.TypesList)
	} else if req.Types != "" {
		provider.Types = req.Types
	} else if req.Type != "" {
		provider.SetTypes([]string{req.Type})
	}
	// Support both camelCase and snake_case
	provider.AutoLoadModels = req.AutoLoadModels || req.AutoLoadModelsSnake
	provider.Disabled = req.Disabled

	if err := h.providerRepo.Update(c.Request.Context(), provider); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Mask API key in response and populate TypesList
	provider.APIKeyMasked = models.MaskAPIKey(provider.APIKey)
	provider.TypesList = provider.GetTypes()
	c.JSON(http.StatusOK, provider)
}

func (h *ProviderHandler) DeleteProvider(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	if err := h.providerRepo.Delete(c.Request.Context(), id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Provider deleted"})
}

func (h *ProviderHandler) LoadModels(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	provider, err := h.providerRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
		return
	}

	var models []map[string]interface{}

	// Determine provider type and fetch models accordingly
	switch strings.ToLower(provider.Type) {
	case "openai":
		models, err = h.fetchOpenAIModels(provider.BaseURL, provider.APIKey)
	case "gemini":
		models, err = h.fetchGeminiModels(provider.BaseURL, provider.APIKey)
	default:
		// Try OpenAI-compatible API for custom providers
		models, err = h.fetchOpenAIModels(provider.BaseURL, provider.APIKey)
	}

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, models)
}

func (h *ProviderHandler) fetchOpenAIModels(baseURL, apiKey string) ([]map[string]interface{}, error) {
	client := &http.Client{Timeout: 30 * time.Second}

	modelsURL := strings.TrimSuffix(baseURL, "/") + "/models"

	req, err := http.NewRequest("GET", modelsURL, nil)
	if err != nil {
		return nil, err
	}

	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := client.Do(req)
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

func (h *ProviderHandler) fetchGeminiModels(baseURL, apiKey string) ([]map[string]interface{}, error) {
	client := &http.Client{Timeout: 30 * time.Second}

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

	resp, err := client.Do(req)
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

func (h *ProviderHandler) SyncModels(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	// Use ModelSyncService if available
	if h.modelSyncService != nil {
		result := h.modelSyncService.SyncProviderModels(c.Request.Context(), id)
		if result.Error != nil {
			if strings.Contains(result.Error.Error(), "provider not found") {
				c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
			} else if strings.Contains(result.Error.Error(), "autoLoadModels enabled") {
				c.JSON(http.StatusBadRequest, gin.H{"error": "此提供商未启用自动加载模型"})
			} else {
				c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
			}
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"message":        "模型同步成功",
			"modelsCreated":  result.ModelsCreated,
			"routesCreated":  result.RoutesCreated,
			"modelsRemoved":  result.ModelsRemoved,
			"routesRemoved":  result.RoutesRemoved,
			"totalFetched":   result.TotalFetched,
		})
		return
	}

	// Fallback to original implementation (for backwards compatibility)
	provider, err := h.providerRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
		return
	}

	// Check if autoLoadModels is enabled
	if !provider.AutoLoadModels {
		c.JSON(http.StatusBadRequest, gin.H{"error": "此提供商未启用自动加载模型"})
		return
	}

	// Fetch models from provider
	var fetchedModels []map[string]interface{}
	switch strings.ToLower(provider.Type) {
	case "openai":
		fetchedModels, err = h.fetchOpenAIModels(provider.BaseURL, provider.APIKey)
	case "gemini":
		fetchedModels, err = h.fetchGeminiModels(provider.BaseURL, provider.APIKey)
	default:
		fetchedModels, err = h.fetchOpenAIModels(provider.BaseURL, provider.APIKey)
	}

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	ctx := c.Request.Context()

	// Get existing routes for this provider
	existingRoutes, _ := h.modelRouteRepo.FindByProviderID(ctx, id)
	existingRouteMap := make(map[uint]models.ModelRoute)
	for _, route := range existingRoutes {
		existingRouteMap[route.ModelID] = route
	}

	// Track remote model names
	remoteModelNames := make(map[string]bool)

	modelsCreated := 0
	routesCreated := 0

	// Process remote models
	for _, m := range fetchedModels {
		modelName, ok := m["name"].(string)
		if !ok {
			continue
		}
		remoteModelNames[modelName] = true

		// Check if model exists
		existingModel, _ := h.modelRepo.FindByNameOrAlias(ctx, modelName)
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
			if err := h.modelRepo.Create(ctx, newModel); err != nil {
				continue
			}
			existingModel = newModel
			modelsCreated++
		}

		// Check if route exists
		if _, hasRoute := existingRouteMap[existingModel.ID]; !hasRoute {
			// Create route
			route := &models.ModelRoute{
				ModelID:    existingModel.ID,
				ProviderID: id,
				Weight:     1,
				CreatedAt:  time.Now(),
			}
			if err := h.modelRouteRepo.Create(ctx, route); err == nil {
				routesCreated++
			}
		}
	}

	// Remove models that no longer exist remotely
	modelsRemoved := 0
	routesRemoved := 0
	for _, route := range existingRoutes {
		model, _ := h.modelRepo.FindByID(ctx, route.ModelID)
		if model != nil && !remoteModelNames[model.Name] {
			// Check if model has other provider associations
			otherRoutes, _ := h.modelRouteRepo.FindByModel(ctx, model.ID)
			hasOtherProvider := false
			for _, r := range otherRoutes {
				if r.ProviderID != id {
					hasOtherProvider = true
					break
				}
			}

			// Delete the route
			h.modelRouteRepo.Delete(ctx, route.ID)
			routesRemoved++

			// Only delete model if no other associations
			if !hasOtherProvider && len(otherRoutes) <= 1 {
				h.modelRepo.Delete(ctx, model.ID)
				modelsRemoved++
			}
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"message":        "模型同步成功",
		"modelsCreated":  modelsCreated,
		"routesCreated":  routesCreated,
		"modelsRemoved":  modelsRemoved,
		"routesRemoved":  routesRemoved,
		"totalFetched":   len(fetchedModels),
	})
}

// AddModels adds multiple models and creates routes to the provider
func (h *ProviderHandler) AddModels(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	provider, err := h.providerRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
		return
	}

	var req struct {
		Models []struct {
			Name        string `json:"name"`
			Description string `json:"description"`
		} `json:"models"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ctx := c.Request.Context()
	modelsCreated := 0
	routesCreated := 0
	alreadyAssociated := 0

	for _, m := range req.Models {
		if m.Name == "" {
			continue
		}

		// Check if model exists
		existingModel, _ := h.modelRepo.FindByNameOrAlias(ctx, m.Name)
		if existingModel == nil {
			// Create new model
			newModel := &models.Model{
				Name:        m.Name,
				Description: m.Description,
				CreatedAt:   time.Now(),
				UpdatedAt:   time.Now(),
			}
			if err := h.modelRepo.Create(ctx, newModel); err != nil {
				continue
			}
			existingModel = newModel
			modelsCreated++
		}

		// Check if route already exists
		routes, _ := h.modelRouteRepo.FindByModel(ctx, existingModel.ID)
		hasRoute := false
		for _, r := range routes {
			if r.ProviderID == provider.ID {
				hasRoute = true
				break
			}
		}
		if hasRoute {
			alreadyAssociated++
			continue
		}

		// Create route
		route := &models.ModelRoute{
			ModelID:    existingModel.ID,
			ProviderID: provider.ID,
			Weight:     1,
			CreatedAt:  time.Now(),
		}
		if err := h.modelRouteRepo.Create(ctx, route); err != nil {
			continue
		}
		routesCreated++
	}

	c.JSON(http.StatusOK, gin.H{
		"message":           "模型添加成功",
		"modelsCreated":     modelsCreated,
		"routesCreated":     routesCreated,
		"alreadyAssociated": alreadyAssociated,
	})
}

// ChannelHandler
type ChannelHandler struct {
	channelRepo *repository.ChannelRepository
}

func NewChannelHandler(channelRepo *repository.ChannelRepository) *ChannelHandler {
	return &ChannelHandler{channelRepo: channelRepo}
}

func (h *ChannelHandler) ListChannels(c *gin.Context) {
	channels, err := h.channelRepo.ListWithRelations(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, channels)
}

func (h *ChannelHandler) CreateChannel(c *gin.Context) {
	var req struct {
		Name            string `json:"name" binding:"required"`
		Shared          bool   `json:"shared"`
		ProviderID      uint   `json:"providerId"`
		ProviderIDSnake uint   `json:"provider_id"`
		ProviderIDs     []uint `json:"providerIds"`
		ModelIDs        []uint `json:"modelIds"`
		ModelIDsSnake   []uint `json:"models"`
		Enabled         bool   `json:"enabled"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	channel := &models.Channel{
		Name:    req.Name,
		Shared:  req.Shared,
		Enabled: true,
	}

	if err := h.channelRepo.Create(c.Request.Context(), channel); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Support both providerId and providerIds
	providerIDs := req.ProviderIDs
	if len(providerIDs) == 0 && (req.ProviderID != 0 || req.ProviderIDSnake != 0) {
		pid := req.ProviderID
		if pid == 0 {
			pid = req.ProviderIDSnake
		}
		if pid != 0 {
			providerIDs = []uint{pid}
		}
	}
	if len(providerIDs) > 0 {
		h.channelRepo.BindProviders(c.Request.Context(), channel.ID, providerIDs)
	}

	// Support both modelIds and models
	modelIDs := req.ModelIDs
	if len(modelIDs) == 0 {
		modelIDs = req.ModelIDsSnake
	}
	if len(modelIDs) > 0 {
		h.channelRepo.BindModels(c.Request.Context(), channel.ID, modelIDs)
	}

	c.JSON(http.StatusCreated, channel)
}

func (h *ChannelHandler) GetChannel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	channel, err := h.channelRepo.FindByIDWithRelations(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Channel not found"})
		return
	}

	c.JSON(http.StatusOK, channel)
}

func (h *ChannelHandler) UpdateChannel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Name            string `json:"name"`
		Enabled         bool   `json:"enabled"`
		Shared          bool   `json:"shared"`
		ProviderID      uint   `json:"providerId"`
		ProviderIDSnake uint   `json:"provider_id"`
		ProviderIDs     []uint `json:"providerIds"`
		ModelIDs        []uint `json:"modelIds"`
		ModelIDsSnake   []uint `json:"models"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	channel, err := h.channelRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Channel not found"})
		return
	}

	if req.Name != "" {
		channel.Name = req.Name
	}
	channel.Enabled = req.Enabled
	channel.Shared = req.Shared

	if err := h.channelRepo.Update(c.Request.Context(), channel); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Support both providerId and providerIds
	providerIDs := req.ProviderIDs
	if len(providerIDs) == 0 && (req.ProviderID != 0 || req.ProviderIDSnake != 0) {
		pid := req.ProviderID
		if pid == 0 {
			pid = req.ProviderIDSnake
		}
		if pid != 0 {
			providerIDs = []uint{pid}
		}
	}
	if len(providerIDs) > 0 {
		h.channelRepo.BindProviders(c.Request.Context(), channel.ID, providerIDs)
	}

	// Support both modelIds and models
	modelIDs := req.ModelIDs
	if len(modelIDs) == 0 {
		modelIDs = req.ModelIDsSnake
	}
	if len(modelIDs) > 0 {
		h.channelRepo.BindModels(c.Request.Context(), channel.ID, modelIDs)
	}

	c.JSON(http.StatusOK, channel)
}

func (h *ChannelHandler) DeleteChannel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	if err := h.channelRepo.Delete(c.Request.Context(), id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Channel deleted"})
}

func (h *ChannelHandler) BindProviders(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		ProviderIDs []uint `json:"provider_ids"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.channelRepo.BindProviders(c.Request.Context(), id, req.ProviderIDs); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Providers bound successfully"})
}

func (h *ChannelHandler) BindModels(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		ModelIDs []uint `json:"model_ids"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.channelRepo.BindModels(c.Request.Context(), id, req.ModelIDs); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Models bound successfully"})
}

// ModelHandler
type ModelHandler struct {
	modelRepo       *repository.ModelRepository
	modelRouteRepo  *repository.ModelRouteRepository
	modelAliasRepo  *repository.ModelAliasRepository
	channelRepo     *repository.ChannelRepository
}

func NewModelHandler(modelRepo *repository.ModelRepository, modelRouteRepo *repository.ModelRouteRepository, modelAliasRepo *repository.ModelAliasRepository, channelRepo *repository.ChannelRepository) *ModelHandler {
	return &ModelHandler{
		modelRepo:       modelRepo,
		modelRouteRepo:  modelRouteRepo,
		modelAliasRepo:  modelAliasRepo,
		channelRepo:     channelRepo,
	}
}

func (h *ModelHandler) ListModels(c *gin.Context) {
	name := c.Query("name")
	if name != "" {
		model, err := h.modelRepo.FindByNameOrAlias(c.Request.Context(), name)
		if err != nil {
			c.JSON(http.StatusOK, []models.Model{})
			return
		}
		// Load routes for this model
		modelWithRoutes, err := h.modelRepo.FindWithRoutes(c.Request.Context(), model.ID)
		if err != nil {
			c.JSON(http.StatusOK, []*models.Model{model})
			return
		}
		c.JSON(http.StatusOK, []*models.Model{modelWithRoutes})
		return
	}

	modelsList, err := h.modelRepo.ListWithRoutes(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, modelsList)
}

func (h *ModelHandler) CreateModel(c *gin.Context) {
	var req struct {
		Name                  string   `json:"name" binding:"required"`
		Aliases               []string `json:"aliases"`
		Description           string   `json:"description"`
		InputTokenPrice      int64  `json:"inputTokenPrice"`
		InputTokenPriceSnake int64  `json:"input_price"`
		OutputTokenPrice     int64  `json:"outputTokenPrice"`
		OutputTokenPriceSnake int64  `json:"output_price"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ctx := c.Request.Context()

	// Support both camelCase and snake_case
	inputPrice := req.InputTokenPrice
	if inputPrice == 0 {
		inputPrice = req.InputTokenPriceSnake
	}
	outputPrice := req.OutputTokenPrice
	if outputPrice == 0 {
		outputPrice = req.OutputTokenPriceSnake
	}

	model := &models.Model{
		Name:             req.Name,
		Description:      req.Description,
		InputTokenPrice:  inputPrice,
		OutputTokenPrice: outputPrice,
		CreatedAt:        time.Now(),
		UpdatedAt:        time.Now(),
	}

	if err := h.modelRepo.Create(ctx, model); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Create default alias (model name)
	h.modelAliasRepo.Create(ctx, &models.ModelAlias{
		ModelID: model.ID,
		Alias:   model.Name,
	})

	// Create additional aliases
	for _, alias := range req.Aliases {
		if alias == model.Name {
			continue // Skip name alias, already created
		}
		h.modelAliasRepo.Create(ctx, &models.ModelAlias{
			ModelID: model.ID,
			Alias:   alias,
		})
	}

	// Return model with aliases
	aliases, _ := h.modelAliasRepo.GetAliases(ctx, model.ID)
	response := map[string]interface{}{
		"id":               model.ID,
		"name":             model.Name,
		"aliases":          aliases,
		"description":      model.Description,
		"inputTokenPrice":  model.InputTokenPrice,
		"outputTokenPrice": model.OutputTokenPrice,
		"userId":           model.UserID,
		"createdAt":        model.CreatedAt,
		"updatedAt":        model.UpdatedAt,
	}
	c.JSON(http.StatusCreated, response)
}

func (h *ModelHandler) GetModel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	model, err := h.modelRepo.FindWithRoutes(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		return
	}

	c.JSON(http.StatusOK, model)
}

func (h *ModelHandler) UpdateModel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Name                  string   `json:"name"`
		Aliases               []string `json:"aliases"`
		Description           string   `json:"description"`
		InputTokenPrice      int64  `json:"inputTokenPrice"`
		InputTokenPriceSnake int64  `json:"input_price"`
		OutputTokenPrice     int64  `json:"outputTokenPrice"`
		OutputTokenPriceSnake int64  `json:"output_price"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ctx := c.Request.Context()
	model, err := h.modelRepo.FindByID(ctx, id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		return
	}

	if req.Name != "" {
		model.Name = req.Name
	}
	// Support both camelCase and snake_case
	model.Description = req.Description
	// Support both camelCase and snake_case
	if req.InputTokenPrice != 0 {
		model.InputTokenPrice = req.InputTokenPrice
	} else if req.InputTokenPriceSnake != 0 {
		model.InputTokenPrice = req.InputTokenPriceSnake
	}
	if req.OutputTokenPrice != 0 {
		model.OutputTokenPrice = req.OutputTokenPrice
	} else if req.OutputTokenPriceSnake != 0 {
		model.OutputTokenPrice = req.OutputTokenPriceSnake
	}

	if err := h.modelRepo.Update(ctx, model); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Update aliases
	if req.Aliases != nil {
		h.modelAliasRepo.UpdateAliases(ctx, model.ID, model.Name, req.Aliases)
	}

	// Return model with aliases
	aliases, _ := h.modelAliasRepo.GetAliases(ctx, model.ID)
	response := map[string]interface{}{
		"id":               model.ID,
		"name":             model.Name,
		"aliases":          aliases,
		"description":      model.Description,
		"inputTokenPrice":  model.InputTokenPrice,
		"outputTokenPrice": model.OutputTokenPrice,
		"userId":           model.UserID,
		"createdAt":        model.CreatedAt,
		"updatedAt":        model.UpdatedAt,
	}
	c.JSON(http.StatusOK, response)
}

func (h *ModelHandler) DeleteModel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))
	ctx := c.Request.Context()

	// Check if model exists
	_, err := h.modelRepo.FindByID(ctx, id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		return
	}

	// Check if model is associated with any channels
	channelBindings, _ := h.channelRepo.GetChannelsByModelID(ctx, id)
	if len(channelBindings) > 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"error":    "无法删除，该模型被渠道关联",
			"channels": len(channelBindings),
		})
		return
	}

	// Delete associated routes first
	routes, _ := h.modelRouteRepo.FindByModel(ctx, id)
	for _, route := range routes {
		h.modelRouteRepo.Delete(ctx, route.ID)
	}

	// Delete aliases
	h.modelAliasRepo.DeleteByModelID(ctx, id)

	// Delete model
	if err := h.modelRepo.Delete(ctx, id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Model deleted"})
}

func (h *ModelHandler) GetModelRoutes(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	routes, err := h.modelRouteRepo.FindByModel(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, routes)
}

func (h *ModelHandler) UpdateModelRoutes(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Routes []models.ModelRoute `json:"routes"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ctx := c.Request.Context()

	// If routes are empty, perform cleanup
	if len(req.Routes) == 0 {
		// Delete all routes for this model
		h.modelRouteRepo.UpdateRoutesForModel(ctx, id, req.Routes)

		// Check for channel bindings
		channelBindings, _ := h.channelRepo.GetChannelsByModelID(ctx, id)
		if len(channelBindings) > 0 {
			// Model has channel bindings, just clear routes but keep model
			c.JSON(http.StatusOK, gin.H{
				"message":         "Routes cleared, model retained due to channel bindings",
				"channelBindings": len(channelBindings),
			})
			return
		}

		// Delete aliases
		h.modelAliasRepo.DeleteByModelID(ctx, id)

		// Delete the orphaned model
		h.modelRepo.Delete(ctx, id)

		c.JSON(http.StatusOK, gin.H{
			"message":      "Routes cleared and orphaned model deleted",
			"modelDeleted": true,
		})
		return
	}

	// Normal update with routes
	if err := h.modelRouteRepo.UpdateRoutesForModel(ctx, id, req.Routes); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Return updated routes
	routes, err := h.modelRouteRepo.FindByModel(ctx, id)
	if err != nil {
		c.JSON(http.StatusOK, req.Routes)
		return
	}

	c.JSON(http.StatusOK, routes)
}

// APIKeyHandler
type APIKeyHandler struct {
	apiKeyRepo  *repository.APIKeyRepository
	authService *service.AuthService
}

func NewAPIKeyHandler(apiKeyRepo *repository.APIKeyRepository, authService *service.AuthService) *APIKeyHandler {
	return &APIKeyHandler{apiKeyRepo: apiKeyRepo, authService: authService}
}

func (h *APIKeyHandler) ListAPIKeys(c *gin.Context) {
	keys, err := h.apiKeyRepo.List(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, keys)
}

func (h *APIKeyHandler) CreateAPIKey(c *gin.Context) {
	var req struct {
		Name                string `json:"name" binding:"required"`
		BindToAllChannels   bool   `json:"bindToAllChannels"`
		BindToAllChannelsSnake bool `json:"bind_to_all"`
		ChannelIDs          []uint `json:"channelIds"`
		ChannelIDsSnake     []uint `json:"channels"`
		LogDetails          bool   `json:"logDetails"`
		LogDetailsSnake     bool   `json:"log_details"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	key, err := service.GenerateAPIKey()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Support both camelCase and snake_case
	bindToAll := req.BindToAllChannels || req.BindToAllChannelsSnake
	logDetails := req.LogDetails || req.LogDetailsSnake
	channelIDs := req.ChannelIDs
	if len(channelIDs) == 0 {
		channelIDs = req.ChannelIDsSnake
	}

	apiKey := &models.GatewayAPIKey{
		Key:              key,
		Name:             req.Name,
		Enabled:          true,
		BindToAllChannels: bindToAll,
		LogDetails:       logDetails,
		CreatedAt:        time.Now(),
	}

	if err := h.apiKeyRepo.Create(c.Request.Context(), apiKey); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Bind channels
	if !bindToAll && len(channelIDs) > 0 {
		h.apiKeyRepo.BindChannels(c.Request.Context(), apiKey.ID, channelIDs)
	}

	c.JSON(http.StatusCreated, apiKey)
}

func (h *APIKeyHandler) UpdateAPIKey(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Name                string `json:"name"`
		Enabled             bool   `json:"enabled"`
		BindToAllChannels   bool   `json:"bindToAllChannels"`
		BindToAllChannelsSnake bool `json:"bind_to_all"`
		ChannelIDs          []uint `json:"channelIds"`
		ChannelIDsSnake     []uint `json:"channels"`
		LogDetails          bool   `json:"logDetails"`
		LogDetailsSnake     bool   `json:"log_details"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	apiKey, err := h.apiKeyRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "API Key not found"})
		return
	}

	if req.Name != "" {
		apiKey.Name = req.Name
	}
	apiKey.Enabled = req.Enabled
	// Support both camelCase and snake_case
	apiKey.BindToAllChannels = req.BindToAllChannels || req.BindToAllChannelsSnake
	apiKey.LogDetails = req.LogDetails || req.LogDetailsSnake

	channelIDs := req.ChannelIDs
	if len(channelIDs) == 0 {
		channelIDs = req.ChannelIDsSnake
	}

	if err := h.apiKeyRepo.Update(c.Request.Context(), apiKey); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if !apiKey.BindToAllChannels && len(channelIDs) > 0 {
		h.apiKeyRepo.BindChannels(c.Request.Context(), apiKey.ID, channelIDs)
	}

	c.JSON(http.StatusOK, apiKey)
}

func (h *APIKeyHandler) DeleteAPIKey(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	apiKey, err := h.apiKeyRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "API Key not found"})
		return
	}

	apiKey.Enabled = false
	if err := h.apiKeyRepo.Update(c.Request.Context(), apiKey); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "API Key disabled"})
}