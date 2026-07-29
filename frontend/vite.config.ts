import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({
  base: '/console/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: Object.fromEntries(
      ['/auth', '/user', '/admin', '/me', '/health', '/v1', '/v1beta'].map((path) => [
        path,
        {
          target: process.env.GATEWAY_DEV_URL ?? 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      ]),
    ),
  },
  test: {
    environment: 'jsdom',
    exclude: [...configDefaults.exclude, 'e2e/**'],
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    maxWorkers: 2,
    testTimeout: 5_000,
    hookTimeout: 10_000,
    teardownTimeout: 10_000,
  },
})
