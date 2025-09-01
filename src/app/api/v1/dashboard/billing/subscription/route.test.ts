import { test, expect } from '@jest/globals';
import { GET as subscriptionGET } from '@/app/api/v1/dashboard/billing/subscription/route';
import { GET as usageGET } from '@/app/api/v1/dashboard/billing/usage/route';

// Mock the database
jest.mock('@/lib/db', () => ({
  getInitializedDb: jest.fn(),
}));

test('Subscription API route compiles without error', async () => {
  expect(subscriptionGET).toBeDefined();
});

test('Usage API route compiles without error', async () => {
  expect(usageGET).toBeDefined();
});