import { vi, describe, it, expect, beforeEach } from 'vitest'
import axios from 'axios'
import { userApi } from '@/api/auth'
import { providerApi } from '@/api/provider'
import { channelApi } from '@/api/channel'
import { modelApi } from '@/api/model'
import { apiKeyApi } from '@/api/apiKey'
import { logApi } from '@/api/log'
import { statsApi } from '@/api/stats'

// Mock axios
vi.mock('axios', () => {
  const mockAxios = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    create: vi.fn(() => mockAxios),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  }
  return {
    default: mockAxios,
    ...mockAxios
  }
})

describe('User API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('userApi', () => {
    it('should list users', async () => {
      const mockResponse = { data: [] }
      vi.mocked(axios.get).mockResolvedValue(mockResponse)

      const result = await userApi.list()

      expect(axios.get).toHaveBeenCalledWith('/users')
      expect(result).toEqual(mockResponse)
    })

    it('should create user', async () => {
      const mockResponse = { data: { id: 1, email: 'test@example.com' } }
      vi.mocked(axios.post).mockResolvedValue(mockResponse)

      const result = await userApi.create({
        email: 'test@example.com',
        password: 'password123',
        role: 'USER'
      })

      expect(axios.post).toHaveBeenCalledWith('/users', {
        email: 'test@example.com',
        password: 'password123',
        role: 'USER'
      })
      expect(result).toEqual(mockResponse)
    })

    it('should get user by id', async () => {
      const mockResponse = { data: { id: 1, email: 'test@example.com' } }
      vi.mocked(axios.get).mockResolvedValue(mockResponse)

      const result = await userApi.get(1)

      expect(axios.get).toHaveBeenCalledWith('/users/1')
      expect(result).toEqual(mockResponse)
    })

    it('should update user', async () => {
      const mockResponse = { data: { id: 1, role: 'ADMIN' } }
      vi.mocked(axios.put).mockResolvedValue(mockResponse)

      const result = await userApi.update(1, { role: 'ADMIN' })

      expect(axios.put).toHaveBeenCalledWith('/users/1', { role: 'ADMIN' })
      expect(result).toEqual(mockResponse)
    })

    it('should delete user', async () => {
      vi.mocked(axios.delete).mockResolvedValue({ data: {} })

      await userApi.delete(1)

      expect(axios.delete).toHaveBeenCalledWith('/users/1')
    })

    it('should update balance', async () => {
      vi.mocked(axios.put).mockResolvedValue({ data: {} })

      await userApi.updateBalance(1, { amount: 100, action: 'add' })

      expect(axios.put).toHaveBeenCalledWith('/users/1/balance', { amount: 100, action: 'add' })
    })

    it('should toggle disabled', async () => {
      vi.mocked(axios.post).mockResolvedValue({ data: {} })

      await userApi.toggleDisabled(1)

      expect(axios.post).toHaveBeenCalledWith('/users/1/toggle-disabled')
    })
  })
})

describe('Provider API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should list providers', async () => {
    const mockResponse = { data: [] }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await providerApi.list()

    expect(axios.get).toHaveBeenCalledWith('/providers')
    expect(result).toEqual(mockResponse)
  })

  it('should create provider', async () => {
    const mockResponse = { data: { id: 1, name: 'OpenAI' } }
    vi.mocked(axios.post).mockResolvedValue(mockResponse)

    const result = await providerApi.create({
      name: 'OpenAI',
      base_url: 'https://api.openai.com',
      type: 'OpenAI',
      api_key: 'sk-test'
    })

    expect(axios.post).toHaveBeenCalledWith('/providers', {
      name: 'OpenAI',
      base_url: 'https://api.openai.com',
      type: 'OpenAI',
      api_key: 'sk-test'
    })
    expect(result).toEqual(mockResponse)
  })

  it('should load models', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { models: [] } })

    await providerApi.loadModels(1)

    expect(axios.get).toHaveBeenCalledWith('/providers/1/load-models')
  })

  it('should sync models', async () => {
    vi.mocked(axios.post).mockResolvedValue({ data: {} })

    await providerApi.syncModels(1)

    expect(axios.post).toHaveBeenCalledWith('/providers/1/sync-models')
  })
})

describe('Channel API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should list channels', async () => {
    const mockResponse = { data: [] }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await channelApi.list()

    expect(axios.get).toHaveBeenCalledWith('/channels')
    expect(result).toEqual(mockResponse)
  })

  it('should create channel', async () => {
    const mockResponse = { data: { id: 1, name: 'Channel1' } }
    vi.mocked(axios.post).mockResolvedValue(mockResponse)

    await channelApi.create({
      name: 'Channel1',
      enabled: true
    })

    expect(axios.post).toHaveBeenCalledWith('/channels', {
      name: 'Channel1',
      enabled: true
    })
  })

  it('should bind providers', async () => {
    vi.mocked(axios.post).mockResolvedValue({ data: {} })

    await channelApi.bindProviders(1, [1, 2])

    expect(axios.post).toHaveBeenCalledWith('/channels/1/providers', { provider_ids: [1, 2] })
  })
})

describe('Model API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should list models', async () => {
    const mockResponse = { data: [] }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await modelApi.list()

    expect(axios.get).toHaveBeenCalledWith('/models', { params: undefined })
    expect(result).toEqual(mockResponse)
  })

  it('should create model', async () => {
    const mockResponse = { data: { id: 1, name: 'gpt-4' } }
    vi.mocked(axios.post).mockResolvedValue(mockResponse)

    await modelApi.create({
      name: 'gpt-4',
      input_price: 0.03,
      output_price: 0.06
    })

    expect(axios.post).toHaveBeenCalledWith('/models', {
      name: 'gpt-4',
      input_price: 0.03,
      output_price: 0.06
    })
  })

  it('should get routes', async () => {
    const mockResponse = { data: { routes: [] } }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await modelApi.getRoutes(1)

    expect(axios.get).toHaveBeenCalledWith('/models/1/routes')
    expect(result).toEqual(mockResponse)
  })

  it('should update routes', async () => {
    vi.mocked(axios.put).mockResolvedValue({ data: {} })

    await modelApi.updateRoutes(1, [{ channel_id: 1, model_name: 'gpt-4', weight: 1 }])

    expect(axios.put).toHaveBeenCalledWith('/models/1/routes', { routes: [{ channel_id: 1, model_name: 'gpt-4', weight: 1 }] })
  })
})

describe('API Key API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should list api keys', async () => {
    const mockResponse = { data: [] }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await apiKeyApi.list()

    expect(axios.get).toHaveBeenCalledWith('/keys')
    expect(result).toEqual(mockResponse)
  })

  it('should create api key', async () => {
    const mockResponse = { data: { id: 1, key: 'sk-xxx' } }
    vi.mocked(axios.post).mockResolvedValue(mockResponse)

    await apiKeyApi.create({
      name: 'TestKey',
      enabled: true
    })

    expect(axios.post).toHaveBeenCalledWith('/keys', {
      name: 'TestKey',
      enabled: true
    })
  })
})

describe('Log API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should list logs', async () => {
    const mockResponse = { data: { logs: [], total: 0 } }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await logApi.list({ page: 1 })

    expect(axios.get).toHaveBeenCalledWith('/logs', { params: { page: 1 } })
    expect(result).toEqual(mockResponse)
  })

  it('should get log detail', async () => {
    const mockResponse = { data: { id: 1, request: '{}', response: '{}' } }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await logApi.getDetail(1)

    expect(axios.get).toHaveBeenCalledWith('/logs/1')
    expect(result).toEqual(mockResponse)
  })

  it('should cleanup logs', async () => {
    vi.mocked(axios.delete).mockResolvedValue({ data: {} })

    await logApi.cleanup(30)

    expect(axios.delete).toHaveBeenCalledWith('/logs/cleanup', { params: { days: 30 } })
  })
})

describe('Stats API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should get stats without params', async () => {
    const mockResponse = { data: { totalRequests: 100, totalTokens: 5000 } }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await statsApi.getStats()

    expect(axios.get).toHaveBeenCalledWith('/stats', { params: undefined })
    expect(result).toEqual(mockResponse)
  })

  it('should get stats with date params', async () => {
    const mockResponse = { data: { totalRequests: 100 } }
    vi.mocked(axios.get).mockResolvedValue(mockResponse)

    const result = await statsApi.getStats({
      start_date: '2024-01-01',
      end_date: '2024-01-31'
    })

    expect(axios.get).toHaveBeenCalledWith('/stats', {
      params: { start_date: '2024-01-01', end_date: '2024-01-31' }
    })
    expect(result).toEqual(mockResponse)
  })

  it('should test model', async () => {
    vi.mocked(axios.post).mockResolvedValue({ data: { result: 'test output' } })

    await statsApi.testModel({
      providerId: 1,
      model: 'gpt-4',
      prompt: 'Hello'
    })

    expect(axios.post).toHaveBeenCalledWith('/test-model', {
      providerId: 1,
      model: 'gpt-4',
      prompt: 'Hello'
    })
  })
})