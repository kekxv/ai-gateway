import { NextRequest, NextResponse } from 'next/server';
import { POST as postResponses, GET as getResponses } from '../route';
import { GET as getResponseById, DELETE as deleteResponseById } from '../[id]/route';

// Mock modules
jest.mock('@/lib/db');
jest.mock('@/app/api/v1/_lib/gateway-helpers');

import { getInitializedDb } from '@/lib/db';
import {
  authenticateRequest,
  findModel,
  findModelById,
  selectUpstreamRoute,
  checkApiKeyPermission,
  checkInitialBalance,
  handleUpstreamRequest,
  findRouteForModelPattern,
} from '@/app/api/v1/_lib/gateway-helpers';

const mockGetInitializedDb = getInitializedDb as jest.Mock;
const mockAuthenticateRequest = authenticateRequest as jest.Mock;
const mockFindModel = findModel as jest.Mock;
const mockFindModelById = findModelById as jest.Mock;
const mockSelectUpstreamRoute = selectUpstreamRoute as jest.Mock;
const mockCheckApiKeyPermission = checkApiKeyPermission as jest.Mock;
const mockCheckInitialBalance = checkInitialBalance as jest.Mock;
const mockHandleUpstreamRequest = handleUpstreamRequest as jest.Mock;
const mockFindRouteForModelPattern = findRouteForModelPattern as jest.Mock;

// Mock fetch globally
global.fetch = jest.fn();

describe('Responses API Endpoints', () => {
  let mockDb: any;
  let mockRequest: any;

  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();

    mockDb = {
      get: jest.fn(),
      all: jest.fn(),
      run: jest.fn(),
    };

    mockRequest = {
      url: 'http://localhost:3000/api/v1/responses',
      json: jest.fn(),
    };

    mockGetInitializedDb.mockResolvedValue(mockDb);
    console.log = jest.fn();
    console.error = jest.fn();
  });

  describe('POST /api/v1/responses', () => {
    it('should successfully create a response request', async () => {
      const requestBody = {
        model: 'gpt-4',
        messages: [{ role: 'user', content: 'Hello' }],
      };

      mockRequest.json.mockResolvedValue(requestBody);
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const mockModel = { id: 1, name: 'gpt-4', createdAt: '2024-01-01' };
      const mockRoute = {
        id: 1,
        modelId: 1,
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-123',
      };

      mockFindModel.mockResolvedValue(mockModel);
      mockSelectUpstreamRoute.mockResolvedValue(mockRoute);
      mockCheckApiKeyPermission.mockResolvedValue(null);
      mockCheckInitialBalance.mockResolvedValue(null);

      const mockResponse = NextResponse.json({ id: 'resp_123', model: 'gpt-4' });
      mockHandleUpstreamRequest.mockResolvedValue(mockResponse);

      const response = await postResponses(mockRequest as any);

      expect(response).toBeDefined();
      expect(mockFindModel).toHaveBeenCalledWith('gpt-4', mockDb);
    });

    it('should reject request without model parameter', async () => {
      const requestBody = {
        messages: [{ role: 'user', content: 'Hello' }],
      };

      mockRequest.json.mockResolvedValue(requestBody);
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const response = await postResponses(mockRequest as any);
      const data = await response.json();

      expect(response.status).toBe(400);
      expect(data.error).toContain('model');
    });

    it('should return 401 if authentication fails', async () => {
      const requestBody = { model: 'gpt-4', messages: [] };
      mockRequest.json.mockResolvedValue(requestBody);

      const errorResponse = NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: null,
        errorResponse,
      });

      const response = await postResponses(mockRequest as any);

      expect(response.status).toBe(401);
    });

    it('should handle model not found error', async () => {
      const requestBody = {
        model: 'unknown-model',
        messages: [{ role: 'user', content: 'Hello' }],
      };

      mockRequest.json.mockResolvedValue(requestBody);
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      mockFindModel.mockResolvedValue(null);

      const response = await postResponses(mockRequest as any);
      const data = await response.json();

      expect(response.status).toBe(404);
      expect(data.error).toContain('not found');
    });
  });

  describe('GET /api/v1/responses', () => {
    it('should successfully list responses', async () => {
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const mockRoute = {
        id: 1,
        modelId: 1,
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-123',
      };

      mockFindRouteForModelPattern.mockResolvedValue(mockRoute);
      mockFindModelById.mockResolvedValue({ id: 1, name: 'gpt-4' });
      mockCheckApiKeyPermission.mockResolvedValue(null);

      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          object: 'list',
          data: [{ id: 'resp_1', model: 'gpt-4' }],
        }),
      });

      const response = await getResponses(mockRequest as any);

      expect(response).toBeDefined();
      expect(mockFindRouteForModelPattern).toHaveBeenCalled();
    });

    it('should return 503 when no routes available', async () => {
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      mockFindRouteForModelPattern.mockResolvedValue(null);

      const response = await getResponses(mockRequest as any);
      const data = await response.json();

      expect(response.status).toBe(503);
      expect(data.error).toContain('routes');
    });

    it('should return 401 if authentication fails', async () => {
      const errorResponse = NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: null,
        errorResponse,
      });

      const response = await getResponses(mockRequest as any);

      expect(response.status).toBe(401);
    });
  });

  describe('GET /api/v1/responses/[id]', () => {
    it('should successfully retrieve a response by ID', async () => {
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const mockRoute = {
        id: 1,
        modelId: 1,
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-123',
      };

      mockFindRouteForModelPattern.mockResolvedValue(mockRoute);
      mockFindModelById.mockResolvedValue({ id: 1, name: 'gpt-4' });
      mockCheckApiKeyPermission.mockResolvedValue(null);

      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ id: 'resp_123', model: 'gpt-4', content: 'Hello' }),
      });

      const response = await getResponseById(
        mockRequest as any,
        { params: Promise.resolve({ id: 'resp_123' }) }
      );

      expect(response).toBeDefined();
      expect((global.fetch as jest.Mock).mock.calls[0][0]).toContain('resp_123');
    });

    it('should return 404 when response not found', async () => {
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const mockRoute = {
        id: 1,
        modelId: 1,
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-123',
      };

      mockFindRouteForModelPattern.mockResolvedValue(mockRoute);
      mockFindModelById.mockResolvedValue({ id: 1, name: 'gpt-4' });
      mockCheckApiKeyPermission.mockResolvedValue(null);

      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Response not found' }),
      });

      const response = await getResponseById(
        mockRequest as any,
        { params: Promise.resolve({ id: 'resp_notfound' }) }
      );

      expect(response.status).toBe(404);
    });

    it('should return 401 if authentication fails', async () => {
      const errorResponse = NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: null,
        errorResponse,
      });

      const response = await getResponseById(
        mockRequest as any,
        { params: Promise.resolve({ id: 'resp_123' }) }
      );

      expect(response.status).toBe(401);
    });
  });

  describe('DELETE /api/v1/responses/[id]', () => {
    it('should successfully delete a response', async () => {
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const mockRoute = {
        id: 1,
        modelId: 1,
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-123',
      };

      mockFindRouteForModelPattern.mockResolvedValue(mockRoute);
      mockFindModelById.mockResolvedValue({ id: 1, name: 'gpt-4' });
      mockCheckApiKeyPermission.mockResolvedValue(null);

      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ deleted: true, id: 'resp_123' }),
      });

      const response = await deleteResponseById(
        mockRequest as any,
        { params: Promise.resolve({ id: 'resp_123' }) }
      );

      expect(response).toBeDefined();
      expect((global.fetch as jest.Mock).mock.calls[0][1]?.method).toBe('DELETE');
    });

    it('should return 403 if permission denied', async () => {
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: { id: 1, userId: 1, enabled: true },
        errorResponse: null,
      });

      const mockRoute = {
        id: 1,
        modelId: 1,
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-123',
      };

      mockFindRouteForModelPattern.mockResolvedValue(mockRoute);
      mockFindModelById.mockResolvedValue({ id: 1, name: 'gpt-4' });

      const errorResponse = NextResponse.json(
        { error: 'Forbidden' },
        { status: 403 }
      );
      mockCheckApiKeyPermission.mockResolvedValue(errorResponse);

      const response = await deleteResponseById(
        mockRequest as any,
        { params: Promise.resolve({ id: 'resp_123' }) }
      );

      expect(response.status).toBe(403);
    });

    it('should return 401 if authentication fails', async () => {
      const errorResponse = NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
      mockAuthenticateRequest.mockResolvedValue({
        apiKeyData: null,
        errorResponse,
      });

      const response = await deleteResponseById(
        mockRequest as any,
        { params: Promise.resolve({ id: 'resp_123' }) }
      );

      expect(response.status).toBe(401);
    });
  });
});
