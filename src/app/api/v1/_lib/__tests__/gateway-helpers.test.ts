import { NextRequest, NextResponse } from 'next/server';
import {
  authenticateRequest,
  findModel,
  selectUpstreamRoute,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamRequest,
  handleUpstreamFormRequest,
  logRequestAndCalculateCost,
} from '@/app/api/v1/_lib/gateway-helpers';

// Mock the fetch function
global.fetch = jest.fn();

// Suppress console output during tests unless explicitly checked
beforeEach(() => {
  console.log = jest.fn();
  console.warn = jest.fn();
  console.error = jest.fn();
});

describe('Gateway Helpers - Authentication', () => {
  let mockDb: any;
  let mockRequest: any;

  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();

    mockDb = {
      get: jest.fn(),
      run: jest.fn(),
      all: jest.fn(),
    };

    mockRequest = {
      headers: {
        get: jest.fn(),
      },
    };
  });

  describe('authenticateRequest', () => {
    it('should reject request without Authorization header', async () => {
      mockRequest.headers.get.mockReturnValue(null);

      const result = await authenticateRequest(mockRequest as any, mockDb);

      expect(result.apiKeyData).toBeNull();
      expect(result.errorResponse).toBeDefined();
      expect(result.errorResponse?.status).toBe(401);
    });

    it('should reject request with invalid Authorization header format', async () => {
      mockRequest.headers.get.mockReturnValue('InvalidFormat');

      const result = await authenticateRequest(mockRequest as any, mockDb);

      expect(result.apiKeyData).toBeNull();
      expect(result.errorResponse?.status).toBe(401);
    });

    it('should reject request with invalid API key', async () => {
      mockRequest.headers.get.mockReturnValue('Bearer invalid-key');
      mockDb.get.mockResolvedValue(null);

      const result = await authenticateRequest(mockRequest as any, mockDb);

      expect(result.apiKeyData).toBeNull();
      expect(result.errorResponse?.status).toBe(401);
    });

    it('should reject request with disabled API key', async () => {
      mockRequest.headers.get.mockReturnValue('Bearer valid-key');
      mockDb.get.mockResolvedValue({ id: 1, key: 'valid-key', enabled: false });

      const result = await authenticateRequest(mockRequest as any, mockDb);

      expect(result.apiKeyData).toBeNull();
      expect(result.errorResponse?.status).toBe(401);
    });

    it('should accept request with valid enabled API key', async () => {
      mockRequest.headers.get.mockReturnValue('Bearer valid-key');
      mockDb.get.mockResolvedValue({
        id: 1,
        key: 'valid-key',
        enabled: true,
        userId: 10,
      });
      mockDb.run.mockResolvedValue({ lastID: 1 });

      const result = await authenticateRequest(mockRequest as any, mockDb);

      expect(result.apiKeyData).not.toBeNull();
      expect(result.apiKeyData?.id).toBe(1);
      expect(result.errorResponse).toBeNull();
      expect(mockDb.run).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE GatewayApiKey'),
        expect.any(String),
        1
      );
    });

    it('should handle database errors gracefully', async () => {
      mockRequest.headers.get.mockReturnValue('Bearer valid-key');
      mockDb.get.mockRejectedValue(new Error('Database connection error'));

      const result = await authenticateRequest(mockRequest as any, mockDb);

      expect(result.apiKeyData).toBeNull();
      expect(result.errorResponse?.status).toBe(500);
    });
  });
});

describe('Gateway Helpers - Model Operations', () => {
  let mockDb: any;

  beforeEach(() => {
    jest.clearAllMocks();
    mockDb = {
      get: jest.fn(),
      all: jest.fn(),
      run: jest.fn(),
    };
  });

  describe('findModel', () => {
    it('should find model by exact name with version', async () => {
      mockDb.get.mockResolvedValue({
        id: 1,
        name: 'gpt-4:latest',
        description: 'GPT-4 model',
      });

      const result = await findModel('gpt-4:latest', mockDb);

      expect(result).not.toBeNull();
      expect(result.name).toBe('gpt-4:latest');
      expect(mockDb.get).toHaveBeenCalledWith(
        'SELECT * FROM Model WHERE (name = ? OR alias = ?)',
        'gpt-4:latest',
        'gpt-4:latest'
      );
    });

    it('should find model by name without version, preferring :latest', async () => {
      mockDb.get.mockResolvedValue({
        id: 1,
        name: 'gpt-4:latest',
        description: 'GPT-4 model',
      });

      const result = await findModel('gpt-4', mockDb);

      expect(result).not.toBeNull();
      expect(result.name).toBe('gpt-4:latest');
    });

    it('should return null when model not found', async () => {
      mockDb.get.mockResolvedValue(null);

      const result = await findModel('non-existent', mockDb);

      expect(result).toBeNull();
    });

    it('should find model by alias', async () => {
      mockDb.get.mockResolvedValue({
        id: 2,
        name: 'gpt-4:latest',
        alias: 'gpt4',
        description: 'GPT-4 model',
      });

      const result = await findModel('gpt4', mockDb);

      expect(result).not.toBeNull();
      expect(result.alias).toBe('gpt4');
    });

    it('should handle database errors gracefully', async () => {
      // Test that database errors are handled gracefully by returning null
      mockDb.get.mockRejectedValueOnce('Database error');

      const result = await findModel('gpt-4', mockDb);
      expect(result).toBeNull();
    });
  });

  describe('selectUpstreamRoute', () => {
    it('should select route when eligible routes exist', async () => {
      mockDb.all.mockResolvedValue([
        {
          id: 1,
          modelId: 1,
          weight: 1,
          providerName: 'OpenAI',
          baseURL: 'https://api.openai.com/v1',
          apiKey: 'sk-123',
        },
        {
          id: 2,
          modelId: 1,
          weight: 1,
          providerName: 'Azure',
          baseURL: 'https://api.azure.com',
          apiKey: 'azure-key',
        },
      ]);

      const result = await selectUpstreamRoute(1, mockDb);

      expect(result).not.toBeNull();
      expect([1, 2]).toContain(result.id);
    });

    it('should return null when no eligible routes exist', async () => {
      mockDb.all.mockResolvedValue([]);

      const result = await selectUpstreamRoute(999, mockDb);

      expect(result).toBeNull();
    });

    it('should respect route weights in selection', async () => {
      // Mock multiple calls to test weighted selection distribution
      const routes = [
        { id: 1, modelId: 1, weight: 9, providerName: 'OpenAI' },
        { id: 2, modelId: 1, weight: 1, providerName: 'Azure' },
      ];
      mockDb.all.mockResolvedValue(routes);

      // Call multiple times and verify OpenAI (weight 9) is selected more often
      const selections: number[] = [];
      for (let i = 0; i < 100; i++) {
        // Need to reset mock for each call
        mockDb.all.mockResolvedValue([...routes]);
        const result = await selectUpstreamRoute(1, mockDb);
        selections.push(result.id);
      }

      const openaiCount = selections.filter((id) => id === 1).length;
      expect(openaiCount).toBeGreaterThan(50); // Should be selected ~90% of the time
    });

    it('should handle database errors gracefully', async () => {
      mockDb.all.mockRejectedValue(new Error('Database error'));

      const result = await selectUpstreamRoute(1, mockDb);

      expect(result).toBeNull();
    });
  });
});

describe('Gateway Helpers - Permission and Balance Checks', () => {
  let mockDb: any;
  let mockApiKeyData: any;

  beforeEach(() => {
    jest.clearAllMocks();
    mockDb = {
      get: jest.fn(),
      all: jest.fn(),
      run: jest.fn(),
    };
    mockApiKeyData = {
      id: 1,
      userId: 10,
      bindToAllChannels: false,
    };
  });

  describe('checkApiKeyPermission', () => {
    it('should grant permission when key is bound to all channels', async () => {
      mockApiKeyData.bindToAllChannels = true;

      const result = await checkApiKeyPermission(mockApiKeyData, 1, mockDb);

      expect(result).toBeNull(); // null means permission granted
    });

    it('should deny permission when key is not bound to any channels', async () => {
      mockDb.all.mockResolvedValue([]);

      const result = await checkApiKeyPermission(mockApiKeyData, 1, mockDb);

      expect(result).not.toBeNull();
      expect(result?.status).toBe(403);
    });

    it('should grant permission when model is in allowed channels', async () => {
      mockDb.all.mockResolvedValue([{ channelId: 1 }, { channelId: 2 }]);
      mockDb.get.mockResolvedValue({ id: 1 }); // Model is allowed

      const result = await checkApiKeyPermission(mockApiKeyData, 1, mockDb);

      expect(result).toBeNull(); // Permission granted
    });

    it('should deny permission when model is not in allowed channels', async () => {
      mockDb.all.mockResolvedValue([{ channelId: 1 }, { channelId: 2 }]);
      mockDb.get.mockResolvedValue(null); // Model not found in allowed channels

      const result = await checkApiKeyPermission(mockApiKeyData, 1, mockDb);

      expect(result?.status).toBe(403);
    });

    it('should handle database errors gracefully', async () => {
      mockDb.all.mockRejectedValue(new Error('Database error'));

      const result = await checkApiKeyPermission(mockApiKeyData, 1, mockDb);

      expect(result?.status).toBe(500);
    });
  });

  describe('checkInitialBalance', () => {
    it('should allow request when user has sufficient balance', async () => {
      mockDb.get.mockResolvedValue({
        id: 10,
        balance: 1000,
      });

      const result = await checkInitialBalance(mockApiKeyData, { inputTokenPrice: 10, outputTokenPrice: 5 }, mockDb);

      expect(result).toBeNull(); // Permission granted
    });

    it('should deny request when user has insufficient balance and model has cost', async () => {
      mockDb.get.mockResolvedValue({
        id: 10,
        balance: 0,
      });

      const result = await checkInitialBalance(
        mockApiKeyData,
        { id: 1, inputTokenPrice: 10, outputTokenPrice: 5 },
        mockDb
      );

      expect(result?.status).toBe(403);
    });

    it('should allow request when model is free even with zero balance', async () => {
      mockDb.get.mockResolvedValue({
        id: 10,
        balance: 0,
      });

      const result = await checkInitialBalance(
        mockApiKeyData,
        { inputTokenPrice: 0, outputTokenPrice: 0 },
        mockDb
      );

      expect(result).toBeNull(); // Permission granted
    });

    it('should reject request when user is not found', async () => {
      mockDb.get.mockResolvedValue(null);

      const result = await checkInitialBalance(mockApiKeyData, { inputTokenPrice: 10 }, mockDb);

      expect(result?.status).toBe(500);
    });

    it('should handle database errors gracefully', async () => {
      mockDb.get.mockRejectedValue(new Error('Database error'));

      const result = await checkInitialBalance(mockApiKeyData, { inputTokenPrice: 10 }, mockDb);

      expect(result?.status).toBe(500);
    });
  });
});

describe('Gateway Helpers - Request Handling', () => {
  let mockDb: any;
  let mockApiKeyData: any;
  let mockModel: any;
  let mockSelectedRoute: any;

  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();

    mockDb = {
      get: jest.fn(),
      all: jest.fn(),
      run: jest.fn(),
    };

    mockApiKeyData = {
      id: 1,
      userId: 10,
      bindToAllChannels: true,
      logDetails: false,
    };

    mockModel = {
      id: 1,
      name: 'gpt-4',
      inputTokenPrice: 10,
      outputTokenPrice: 5,
    };

    mockSelectedRoute = {
      id: 1,
      modelId: 1,
      providerName: 'OpenAI',
      baseURL: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
    };
  });

  describe('handleUpstreamRequest', () => {
    it('should handle successful non-streaming request', async () => {
      const mockResponse = {
        ok: true,
        status: 200,
        json: jest.fn().mockResolvedValue({
          id: 'chatcmpl-123',
          usage: {
            prompt_tokens: 10,
            completion_tokens: 20,
            total_tokens: 30,
          },
        }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);
      mockDb.run.mockResolvedValue({ lastID: 1 });

      const result = await handleUpstreamRequest(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        { model: 'gpt-4', messages: [] },
        'https://api.openai.com/v1/chat/completions',
        false
      );

      expect(result.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.openai.com/v1/chat/completions',
        expect.any(Object)
      );
    });

    it('should handle upstream error response', async () => {
      const mockResponse = {
        ok: false,
        status: 404,
        text: jest.fn().mockResolvedValue('Not Found'),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);
      mockDb.run.mockResolvedValue({ lastID: 1 });

      const result = await handleUpstreamRequest(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        { model: 'gpt-4', messages: [] },
        'https://api.openai.com/v1/chat/completions',
        false
      );

      expect(result.status).toBe(404);
      // Should have logged the error
      const calls = (mockDb.run as jest.Mock).mock.calls;
      const logCall = calls.find((call: any[]) => call[0]?.includes('INSERT INTO Log'));
      expect(logCall).toBeDefined();
      expect(logCall[0]).toContain('INSERT INTO Log');
      // Parameters: latency, promptTokens, completionTokens, totalTokens, apiKeyId, modelName, providerName, cost, ownerChannelId, ownerChannelUserId
      expect(logCall[2]).toBe(0); // promptTokens (index 2)
      expect(logCall[3]).toBe(0); // completionTokens (index 3)
      expect(logCall[4]).toBe(0); // totalTokens (index 4)
      expect(logCall[8]).toBe(0); // cost (index 8)
    });

    it('should handle streaming requests', async () => {
      const mockStream = {
        text: jest.fn().mockResolvedValue('stream data'),
      };
      const mockResponse = {
        ok: true,
        status: 200,
        body: mockStream,
        headers: {
          get: jest.fn().mockReturnValue('text/event-stream'),
        },
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);
      mockDb.run.mockResolvedValue({ lastID: 1 });

      const result = await handleUpstreamRequest(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        { model: 'gpt-4', messages: [], stream: true },
        'https://api.openai.com/v1/chat/completions',
        true
      );

      expect(result.status).toBe(200);
      expect(result.headers.get('content-type')).toBe('text/event-stream');
    });

    it('should handle network errors', async () => {
      (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));

      const result = await handleUpstreamRequest(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        { model: 'gpt-4', messages: [] },
        'https://api.openai.com/v1/chat/completions',
        false
      );

      expect(result.status).toBe(502);
    });
  });

  describe('handleUpstreamFormRequest', () => {
    it('should handle successful form request', async () => {
      const mockResponse = {
        ok: true,
        status: 200,
        json: jest.fn().mockResolvedValue({
          url: 'https://example.com/image.png',
        }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);
      mockDb.run.mockResolvedValue({ lastID: 1 });

      const formData = new FormData();
      formData.append('model', 'dall-e-3');

      const result = await handleUpstreamFormRequest(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        formData,
        'https://api.openai.com/v1/images/generations'
      );

      expect(result.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.openai.com/v1/images/generations',
        expect.any(Object)
      );
    });

    it('should handle form request errors', async () => {
      const mockResponse = {
        ok: false,
        status: 400,
        json: jest.fn().mockResolvedValue({
          error: { message: 'Invalid request' },
        }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);
      mockDb.run.mockResolvedValue({ lastID: 1 });

      const formData = new FormData();

      const result = await handleUpstreamFormRequest(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        formData,
        'https://api.openai.com/v1/images/generations'
      );

      expect(result.status).toBe(400);
    });
  });
});

describe('Gateway Helpers - Logging', () => {
  let mockDb: any;
  let mockApiKeyData: any;
  let mockModel: any;
  let mockSelectedRoute: any;

  beforeEach(() => {
    jest.clearAllMocks();
    mockDb = {
      get: jest.fn(),
      all: jest.fn(),
      run: jest.fn(),
    };

    mockApiKeyData = {
      id: 1,
      userId: 10,
      bindToAllChannels: true,
      logDetails: false,
    };

    mockModel = {
      id: 1,
      name: 'gpt-4',
      inputTokenPrice: 10,
      outputTokenPrice: 5,
    };

    mockSelectedRoute = {
      id: 1,
      providerName: 'OpenAI',
    };
  });

  describe('logRequestAndCalculateCost', () => {
    it('should log request with correct token calculations', async () => {
      mockDb.run.mockResolvedValue({ lastID: 1 });
      mockDb.get.mockResolvedValue(null);
      mockDb.all.mockResolvedValue([]);

      await logRequestAndCalculateCost(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        { model: 'gpt-4' },
        { usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 } },
        1000,
        false
      );

      // Should calculate cost: (100/1000)*10 + (50/1000)*5 = 1 + 0.25 = 1.25, rounded to 1
      expect(mockDb.run).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO Log'),
        1000, // latency
        100, // promptTokens
        50, // completionTokens
        150, // totalTokens
        1, // apiKeyId
        'gpt-4', // modelName
        'OpenAI', // providerName
        1, // cost (rounded)
        null, // ownerChannelId
        null // ownerChannelUserId
      );
    });

    it('should handle zero-cost requests', async () => {
      mockDb.run.mockResolvedValue({ lastID: 1 });
      mockDb.all.mockResolvedValue([]);

      await logRequestAndCalculateCost(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        {},
        { usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 } },
        100,
        false
      );

      expect(mockDb.run).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO Log'),
        100,
        0,
        0,
        0,
        1,
        'gpt-4',
        'OpenAI',
        0, // cost = 0
        null,
        null
      );
    });

    it('should store detailed log when logDetails is enabled', async () => {
      mockApiKeyData.logDetails = true;
      mockDb.run.mockResolvedValue({ lastID: 1 });
      mockDb.all.mockResolvedValue([]);

      await logRequestAndCalculateCost(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        { model: 'gpt-4' },
        { result: 'success' },
        100,
        false
      );

      // Should call INSERT INTO LogDetail
      expect(mockDb.run).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO LogDetail'),
        1, // logId
        expect.anything(), // gzipped request body
        expect.anything() // gzipped response body
      );
    });

    it('should handle missing user gracefully', async () => {
      mockDb.get.mockResolvedValue(null);
      mockDb.all.mockResolvedValue([]);
      mockDb.run.mockResolvedValue({ lastID: 1 });

      // Should not throw error even if user is not found
      await logRequestAndCalculateCost(
        mockDb,
        mockApiKeyData,
        mockModel,
        mockSelectedRoute,
        {},
        { usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 } },
        100,
        false
      );

      // Should still log the entry with correct cost calculation
      expect(mockDb.run).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO Log'),
        100, // latency
        100, // promptTokens
        50, // completionTokens
        150, // totalTokens
        1, // apiKeyId
        'gpt-4', // modelName
        'OpenAI', // providerName
        1, // cost
        null, // ownerChannelId
        null // ownerChannelUserId
      );
      expect(console.warn).toHaveBeenCalled();
    });

    it('should handle database errors gracefully', async () => {
      mockDb.run.mockRejectedValue(new Error('Database error'));

      // Should not throw, errors are caught and logged
      await expect(
        logRequestAndCalculateCost(
          mockDb,
          mockApiKeyData,
          mockModel,
          mockSelectedRoute,
          {},
          { usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 } },
          100,
          false
        )
      ).resolves.not.toThrow();
    });
  });
});
