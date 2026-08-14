import { describe, expect, it } from 'vitest'

import { buildDeepSeekHarnessFiles } from '@/lib/deepseekHarness'

describe('DeepSeek Harness configuration serializer', () => {
  it('exports every selected supported input modality', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'gateway',
      displayName: 'Gateway',
      baseUrl: 'https://gateway.example/v1',
      apiKeyEnv: 'GATEWAY_API_KEY',
      apiKey: 'sk-gw-test',
      defaultModel: 'vision-chat',
      models: [{ canonical_name: 'vision-chat', model_types: ['text', 'image'], enabled: true }],
    })

    expect(files.settingsYaml).toContain('input: [text, image]')
  })

  it('exports image-only selections without adding text', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'gateway',
      displayName: 'Gateway',
      baseUrl: 'https://gateway.example/v1',
      apiKeyEnv: 'GATEWAY_API_KEY',
      apiKey: 'sk-gw-test',
      defaultModel: 'image-only',
      models: [{ canonical_name: 'image-only', model_types: ['image'], enabled: true }],
    })

    expect(files.settingsYaml).toContain('input: [image]')
  })

  it('falls back to text when selections contain no Harness input modality', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'gateway',
      displayName: 'Gateway',
      baseUrl: 'https://gateway.example/v1',
      apiKeyEnv: 'GATEWAY_API_KEY',
      apiKey: 'sk-gw-test',
      defaultModel: 'image-generator',
      models: [{ canonical_name: 'image-generator', model_types: ['text_to_image'], enabled: true }],
    })

    expect(files.settingsYaml).toContain('input: [text]')
  })

  it('uses the legacy scalar model type when selected types are absent', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'gateway',
      displayName: 'Gateway',
      baseUrl: 'https://gateway.example/v1',
      apiKeyEnv: 'GATEWAY_API_KEY',
      apiKey: 'sk-gw-test',
      defaultModel: 'legacy-vision',
      models: [{ canonical_name: 'legacy-vision', model_type: 'image', enabled: true }],
    })

    expect(files.settingsYaml).toContain('input: [image]')
  })

  it('serializes enabled models in canonical order with their supported inputs', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'kekxv',
      displayName: 'ai.kekxv.com',
      baseUrl: 'https://ai.kekxv.com/v1',
      apiKeyEnv: 'KEKXV_API_KEY',
      apiKey: 'sk-gw-test',
      api: 'openai-responses',
      defaultModel: 'chat',
      models: [
        { canonical_name: 'vision', model_type: 'image', enabled: true },
        { canonical_name: 'chat', model_type: 'text', enabled: true },
        { canonical_name: 'disabled', model_type: 'text', enabled: false },
      ],
    })

    expect(files.credentialsYaml).toBe('KEKXV_API_KEY: "sk-gw-test"\n')
    expect(files.settingsYaml).toContain('api: openai-responses')
    expect(files.settingsYaml).toContain('baseURL: "https://ai.kekxv.com/v1"')
    expect(files.settingsYaml).toContain('apiKeyEnv: KEKXV_API_KEY')
    expect(files.settingsYaml).toContain('agent-default-model:\n  provider: kekxv\n  model: chat')
    expect(files.settingsYaml).toContain('      - id: chat\n        name: chat\n        input: [text]')
    expect(files.settingsYaml).toContain('      - id: vision\n        name: vision\n        input: [image]')
    expect(files.settingsYaml.indexOf('- id: chat')).toBeLessThan(files.settingsYaml.indexOf('- id: vision'))
    expect(files.settingsYaml).not.toContain('disabled')
    expect(files.settingsYaml).not.toContain('sk-gw-test')
  })

  it('quotes YAML-significant scalar values', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'provider: one',
      displayName: 'yes',
      baseUrl: 'https://gateway.example/v1#preview',
      apiKeyEnv: 'KEY: VALUE',
      apiKey: 'a: b # secret',
      api: 'openai-completions',
      defaultModel: 'model: one',
      models: [{ canonical_name: 'model: one', model_type: 'text', enabled: true }],
    })

    expect(files.credentialsYaml).toBe('"KEY: VALUE": "a: b # secret"\n')
    expect(files.settingsYaml).toContain('    "provider: one":')
    expect(files.settingsYaml).toContain('      displayName: "yes"')
    expect(files.settingsYaml).toContain('      baseURL: "https://gateway.example/v1#preview"')
    expect(files.settingsYaml).toContain('  provider: "provider: one"\n  model: "model: one"')
  })

  it('defaults an omitted API to openai-responses', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'gateway',
      displayName: 'Gateway',
      baseUrl: 'https://gateway.example/v1',
      apiKeyEnv: 'GATEWAY_API_KEY',
      apiKey: 'sk-gw-test',
      defaultModel: 'chat',
      models: [{ canonical_name: 'chat', model_type: 'text', enabled: true }],
    })

    expect(files.settingsYaml).toContain('api: openai-responses')
  })

  it('orders model names by locale-independent code point order', () => {
    const files = buildDeepSeekHarnessFiles({
      providerId: 'gateway',
      displayName: 'Gateway',
      baseUrl: 'https://gateway.example/v1',
      apiKeyEnv: 'GATEWAY_API_KEY',
      apiKey: 'sk-gw-test',
      api: 'openai-responses',
      defaultModel: 'beta',
      models: [
        { canonical_name: 'zebra', model_type: 'text', enabled: true },
        { canonical_name: 'Álpha', model_type: 'text', enabled: true },
        { canonical_name: 'beta', model_type: 'text', enabled: true },
      ],
    })

    expect(files.settingsYaml.indexOf('- id: beta')).toBeLessThan(files.settingsYaml.indexOf('- id: zebra'))
    expect(files.settingsYaml.indexOf('- id: zebra')).toBeLessThan(files.settingsYaml.indexOf('- id: "Álpha"'))
  })
})
