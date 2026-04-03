package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
	"github.com/kekxv/ai-gateway/internal/service"
)

type ProviderHandler struct {
	providerRepo *repository.ProviderRepository
	modelRepo    *repository.ModelRepository
}

func NewProviderHandler(providerRepo *repository.ProviderRepository, modelRepo *repository.ModelRepository) *ProviderHandler {
	return &ProviderHandler{providerRepo: providerRepo, modelRepo: modelRepo}
}

func (h *ProviderHandler) ListProviders(c *gin.Context) {
	// Parse pagination params
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 10
	}

	providers, total, err := h.providerRepo.ListWithCount(c.Request.Context(), nil, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"providers": providers,
		"total":     total,
	})
}

func (h *ProviderHandler) CreateProvider(c *gin.Context) {
	var req struct {
		Name               string `json:"name" binding:"required"`
		BaseURL            string `json:"baseURL"`
		BaseURLSnake       string `json:"base_url"`
		APIKey             string `json:"apiKey"`
		APIKeySnake        string `json:"api_key"`
		Type               string `json:"type"`
		AutoLoadModels     bool   `json:"autoLoadModels"`
		AutoLoadModelsSnake bool   `json:"auto_load_models"`
		Disabled           bool   `json:"disabled"`
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

	if err := h.providerRepo.Create(c.Request.Context(), provider); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, provider)
}

func (h *ProviderHandler) GetProvider(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	provider, err := h.providerRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Provider not found"})
		return
	}

	c.JSON(http.StatusOK, provider)
}

func (h *ProviderHandler) UpdateProvider(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	var req struct {
		Name               string `json:"name"`
		BaseURL            string `json:"baseURL"`
		BaseURLSnake       string `json:"base_url"`
		APIKey             string `json:"apiKey"`
		APIKeySnake        string `json:"api_key"`
		Type               string `json:"type"`
		AutoLoadModels     bool   `json:"autoLoadModels"`
		AutoLoadModelsSnake bool   `json:"auto_load_models"`
		Disabled           bool   `json:"disabled"`
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
	provider.APIKey = apiKey
	provider.Type = req.Type
	// Support both camelCase and snake_case
	provider.AutoLoadModels = req.AutoLoadModels || req.AutoLoadModelsSnake
	provider.Disabled = req.Disabled

	if err := h.providerRepo.Update(c.Request.Context(), provider); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

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

	// Sync models to database
	newModelsCount := 0
	ctx := c.Request.Context()

	for _, m := range fetchedModels {
		modelName, ok := m["name"].(string)
		if !ok {
			continue
		}

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
			newModelsCount++
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"message":          "模型同步成功",
		"newModelsAdded":   newModelsCount,
		"totalModelsFound": len(fetchedModels),
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
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 10
	}

	channels, total, err := h.channelRepo.ListWithRelationsPaginated(c.Request.Context(), nil, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"channels": channels,
		"total":    total,
	})
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
	modelRepo      *repository.ModelRepository
	modelRouteRepo *repository.ModelRouteRepository
}

func NewModelHandler(modelRepo *repository.ModelRepository, modelRouteRepo *repository.ModelRouteRepository) *ModelHandler {
	return &ModelHandler{modelRepo: modelRepo, modelRouteRepo: modelRouteRepo}
}

func (h *ModelHandler) ListModels(c *gin.Context) {
	name := c.Query("name")
	if name != "" {
		model, err := h.modelRepo.FindByNameOrAlias(c.Request.Context(), name)
		if err != nil {
			c.JSON(http.StatusOK, gin.H{
				"models": []models.Model{},
				"total":  0,
			})
			return
		}
		// Load routes for this model
		modelWithRoutes, err := h.modelRepo.FindWithRoutes(c.Request.Context(), model.ID)
		if err != nil {
			c.JSON(http.StatusOK, gin.H{
				"models": []models.Model{*model},
				"total":  1,
			})
			return
		}
		c.JSON(http.StatusOK, gin.H{
			"models": []models.Model{*modelWithRoutes},
			"total":  1,
		})
		return
	}

	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 10
	}

	modelsList, total, err := h.modelRepo.ListWithRoutesPaginated(c.Request.Context(), nil, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"models": modelsList,
		"total":  total,
	})
}

func (h *ModelHandler) CreateModel(c *gin.Context) {
	var req struct {
		Name                 string `json:"name" binding:"required"`
		Alias                string `json:"alias"`
		Description          string `json:"description"`
		InputTokenPrice      int64  `json:"inputTokenPrice"`
		InputTokenPriceSnake int64  `json:"input_price"`
		OutputTokenPrice     int64  `json:"outputTokenPrice"`
		OutputTokenPriceSnake int64  `json:"output_price"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

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
		Name:            req.Name,
		Alias:           req.Alias,
		Description:     req.Description,
		InputTokenPrice: inputPrice,
		OutputTokenPrice: outputPrice,
		CreatedAt:       time.Now(),
		UpdatedAt:       time.Now(),
	}

	if err := h.modelRepo.Create(c.Request.Context(), model); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, model)
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
		Name                 string `json:"name"`
		Alias                string `json:"alias"`
		Description          string `json:"description"`
		InputTokenPrice      int64  `json:"inputTokenPrice"`
		InputTokenPriceSnake int64  `json:"input_price"`
		OutputTokenPrice     int64  `json:"outputTokenPrice"`
		OutputTokenPriceSnake int64  `json:"output_price"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	model, err := h.modelRepo.FindByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Model not found"})
		return
	}

	if req.Name != "" {
		model.Name = req.Name
	}
	model.Alias = req.Alias
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

	if err := h.modelRepo.Update(c.Request.Context(), model); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, model)
}

func (h *ModelHandler) DeleteModel(c *gin.Context) {
	id := parseUintParam(c.Param("id"))

	if err := h.modelRepo.Delete(c.Request.Context(), id); err != nil {
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

// APIKeyHandler
type APIKeyHandler struct {
	apiKeyRepo  *repository.APIKeyRepository
	authService *service.AuthService
}

func NewAPIKeyHandler(apiKeyRepo *repository.APIKeyRepository, authService *service.AuthService) *APIKeyHandler {
	return &APIKeyHandler{apiKeyRepo: apiKeyRepo, authService: authService}
}

func (h *APIKeyHandler) ListAPIKeys(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 10
	}

	keys, total, err := h.apiKeyRepo.ListWithCount(c.Request.Context(), nil, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"keys":  keys,
		"total": total,
	})
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