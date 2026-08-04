// @vitest-environment node

import { describe, expect, it } from 'vitest'

import viteConfig from '../vite.config'

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { clear: () => undefined, getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
})

describe('frontend test runtime policy', () => {
  it('bounds worker concurrency and per-operation timeouts', () => {
    expect(viteConfig).toMatchObject({
      test: {
        maxWorkers: 2,
        testTimeout: 5_000,
        hookTimeout: 10_000,
        teardownTimeout: 10_000,
      },
    })
  })
})
