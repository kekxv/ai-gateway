import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  ...(process.env.CI ? { workers: 1 } : {}),
  use: {
    baseURL: process.env.CONSOLE_BASE_URL ?? 'http://127.0.0.1:8000/console/',
    testIdAttribute: 'data-test',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  ...(process.env.CONSOLE_BASE_URL
    ? {}
    : {
        webServer: {
          command: 'uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000',
          cwd: '..',
          url: 'http://127.0.0.1:8000/health',
          reuseExistingServer: !process.env.CI,
        },
      }),
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
