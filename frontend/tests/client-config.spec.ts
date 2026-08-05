import { describe, expect, it } from 'vitest'

import { buildClientConfig } from '@/utils/clientConfig'

const input = {
  apiKey: 'sk-gw-example',
  baseUrl: 'https://gateway.example/',
  modelId: 'gateway-model',
}

describe('客户端配置文件生成器', () => {
  it('为 Claude Code 生成可直接使用的完整 settings.json', () => {
    const file = buildClientConfig('claude', input)

    expect(file.filename).toBe('settings.json')
    expect(file.location).toBe('~/.claude/settings.json')
    expect(JSON.parse(file.content)).toEqual({
      env: {
        NAME: 'AI Gateway',
        ANTHROPIC_AUTH_TOKEN: 'sk-gw-example',
        ANTHROPIC_BASE_URL: 'https://gateway.example',
        ANTHROPIC_MODEL: 'gateway-model',
        ANTHROPIC_DEFAULT_OPUS_MODEL: 'gateway-model',
        ANTHROPIC_DEFAULT_SONNET_MODEL: 'gateway-model',
        ANTHROPIC_DEFAULT_HAIKU_MODEL: 'gateway-model',
        CLAUDE_CODE_SUBAGENT_MODEL: 'gateway-model',
      },
      effortLevel: 'medium',
      skipWorkflowUsageWarning: true,
      theme: 'light-daltonized',
      hasCompletedOnboarding: true,
    })
  })

  it('为 Codex 生成使用环境变量认证的 Responses 配置', () => {
    const file = buildClientConfig('codex', input)

    expect(file).toEqual({
      filename: 'config.toml',
      location: '~/.codex/config.toml',
      content: `model = "gateway-model"
model_provider = "gateway"

[model_providers.gateway]
name = "AI Gateway"
base_url = "https://gateway.example/v1"
experimental_bearer_token = "sk-gw-example"
wire_api = "responses"
`,
    })
  })

  it('为 OpenCode 生成 OpenAI 兼容提供商配置', () => {
    const file = buildClientConfig('opencode', input)

    expect(file.filename).toBe('opencode.json')
    expect(file.location).toBe('./opencode.json')
    expect(JSON.parse(file.content)).toEqual({
      $schema: 'https://opencode.ai/config.json',
      model: 'gateway/gateway-model',
      provider: {
        gateway: {
          npm: '@ai-sdk/openai-compatible',
          name: 'AI Gateway',
          options: {
            baseURL: 'https://gateway.example/v1',
            apiKey: 'sk-gw-example',
          },
          models: {
            'gateway-model': { name: 'gateway-model' },
          },
        },
      },
    })
  })

  it('为 Pi 生成包含选定模型的 OpenAI 兼容提供商', () => {
    const file = buildClientConfig('pi', input)

    expect(file.filename).toBe('models.json')
    expect(file.location).toBe('~/.pi/agent/models.json')
    expect(JSON.parse(file.content)).toEqual({
      providers: {
        gateway: {
          baseUrl: 'https://gateway.example/v1',
          api: 'openai-completions',
          apiKey: 'sk-gw-example',
          models: [{ id: 'gateway-model', name: 'gateway-model' }],
        },
      },
    })
  })

  it('拒绝缺失的 API key、网关地址或模型 ID', () => {
    expect(() => buildClientConfig('pi', { ...input, apiKey: ' ' })).toThrow('API key')
    expect(() => buildClientConfig('pi', { ...input, baseUrl: '' })).toThrow('base URL')
    expect(() => buildClientConfig('pi', { ...input, modelId: '' })).toThrow('model ID')
  })
})
