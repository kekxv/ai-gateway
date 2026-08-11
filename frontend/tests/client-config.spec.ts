import { describe, expect, it } from 'vitest'

import { buildClientConfig } from '@/utils/clientConfig'

const input = {
  apiKey: 'sk-gw-example',
  baseUrl: 'https://gateway.example/',
  modelId: 'gateway-model',
}

describe('客户端配置文件生成器', () => {
  it('为 Claude Code 生成可直接使用的完整 settings.json', () => {
    const file = buildClientConfig('claude', {
      ...input,
      claudeModels: {
        primary: 'claude-primary',
        opus: 'claude-opus',
        sonnet: 'claude-sonnet',
        haiku: 'claude-haiku',
        subagent: 'claude-subagent',
      },
    })

    expect(file.filename).toBe('settings.json')
    expect(file.location).toBe('~/.claude/settings.json')
    expect(JSON.parse(file.content)).toEqual({
      env: {
        NAME: 'AI Gateway',
        ANTHROPIC_AUTH_TOKEN: 'sk-gw-example',
        ANTHROPIC_BASE_URL: 'https://gateway.example',
        ANTHROPIC_MODEL: 'claude-primary',
        ANTHROPIC_DEFAULT_OPUS_MODEL: 'claude-opus',
        ANTHROPIC_DEFAULT_SONNET_MODEL: 'claude-sonnet',
        ANTHROPIC_DEFAULT_HAIKU_MODEL: 'claude-haiku',
        CLAUDE_CODE_SUBAGENT_MODEL: 'claude-subagent',
      },
      effortLevel: 'medium',
      skipWorkflowUsageWarning: true,
      theme: 'light-daltonized',
      hasCompletedOnboarding: true,
    })
  })

  it('为 Codex 的主模型、审查模型和子代理模型生成独立配置', () => {
    const file = buildClientConfig('codex', {
      ...input,
      codexModels: {
        primary: 'codex-primary',
        review: 'codex-review',
        subagent: 'codex-subagent',
      },
    })

    expect(file).toEqual({
      filename: 'config.toml',
      location: '~/.codex/config.toml',
      content: `model = "codex-primary"
review_model = "codex-review"
model_provider = "gateway"

[agents]
default_subagent_model = "codex-subagent"

[model_providers.gateway]
name = "AI Gateway"
base_url = "https://gateway.example/v1"
experimental_bearer_token = "sk-gw-example"
wire_api = "responses"
`,
    })
  })

  it('为 OpenCode 的默认、规划、构建和审查角色生成独立模型配置', () => {
    const file = buildClientConfig('opencode', {
      ...input,
      openCodeModels: {
        primary: 'opencode-primary',
        plan: 'opencode-plan',
        build: 'opencode-build',
        review: 'opencode-review',
      },
    })

    expect(file.filename).toBe('opencode.json')
    expect(file.location).toBe('./opencode.json')
    expect(JSON.parse(file.content)).toEqual({
      $schema: 'https://opencode.ai/config.json',
      model: 'gateway/opencode-primary',
      agent: {
        plan: { model: 'gateway/opencode-plan' },
        build: { model: 'gateway/opencode-build' },
        review: {
          description: 'Reviews code for best practices and potential issues',
          mode: 'subagent',
          model: 'gateway/opencode-review',
          prompt: 'You are a code reviewer. Focus on security, performance, and maintainability.',
          permission: { edit: 'deny' },
        },
      },
      provider: {
        gateway: {
          npm: '@ai-sdk/openai-compatible',
          name: 'AI Gateway',
          options: {
            baseURL: 'https://gateway.example/v1',
            apiKey: 'sk-gw-example',
          },
          models: {
            'opencode-primary': { name: 'opencode-primary' },
            'opencode-plan': { name: 'opencode-plan' },
            'opencode-build': { name: 'opencode-build' },
            'opencode-review': { name: 'opencode-review' },
          },
        },
      },
    })
  })

  it('为 Pi 生成可在客户端内切换的多个选定模型', () => {
    const file = buildClientConfig('pi', {
      ...input,
      piModelIds: ['pi-fast', 'pi-deep'],
    })

    expect(file.filename).toBe('models.json')
    expect(file.location).toBe('~/.pi/agent/models.json')
    expect(JSON.parse(file.content)).toEqual({
      providers: {
        gateway: {
          baseUrl: 'https://gateway.example/v1',
          api: 'openai-completions',
          apiKey: 'sk-gw-example',
          models: [
            { id: 'pi-fast', name: 'pi-fast' },
            { id: 'pi-deep', name: 'pi-deep' },
          ],
        },
      },
    })
  })

  it('Pi 未传入选定模型时回退到默认模型 ID', () => {
    const file = buildClientConfig('pi', { ...input, piModelIds: [] })

    expect(JSON.parse(file.content)).toMatchObject({
      providers: {
        gateway: {
          models: [{ id: 'gateway-model', name: 'gateway-model' }],
        },
      },
    })
  })

  it('为 Pi 生成 OpenAI Responses API 配置', () => {
    const file = buildClientConfig('pi', {
      ...input,
      piApi: 'openai-responses',
    })

    expect(JSON.parse(file.content)).toMatchObject({
      providers: {
        gateway: {
          api: 'openai-responses',
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
