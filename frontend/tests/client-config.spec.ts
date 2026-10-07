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
    expect(JSON.parse(file.content)).toMatchObject({
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

  it('为 Pi 模型序列化完整的客户端元数据', () => {
    const file = buildClientConfig('pi', {
      ...input,
      modelId: 'gpt-4.1',
      piModels: [{
        id: 'gpt-4.1',
        modelTypes: ['text'],
        inputPricePerMillion: 2,
        outputPricePerMillion: 8,
        cacheReadPricePerMillion: 0.5,
        cacheWritePricePerMillion: 2.5,
      }],
    })

    const piConfig = JSON.parse(file.content) as {
      providers: { gateway: { models: Array<Record<string, unknown>> } }
    }

    expect(piConfig.providers.gateway.models[0]).toMatchObject({
      id: 'gpt-4.1', name: 'gpt-4.1', input: ['text'],
      cost: { input: 2, output: 8, cacheRead: 0.5, cacheWrite: 2.5 },
    })
  })

  it('Pi 未配置能力参数时省略对应字段，并保留已配置值', () => {
    const file = buildClientConfig('pi', {
      ...input,
      piModels: [{ id: 'model-a', contextWindow: 64000, maxTokens: 4096, reasoning: true }],
    })
    const model = (JSON.parse(file.content) as { providers: { gateway: { models: Array<Record<string, unknown>> } } }).providers.gateway.models[0]
    expect(model).toMatchObject({ contextWindow: 64000, maxTokens: 4096, reasoning: true })
    expect(model).not.toHaveProperty('input')
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

  it.each([true, false])('Claude 序列化显式思考开关 %s 和强度', (enabled) => {
    const config = JSON.parse(buildClientConfig('claude', {
      ...input, claudeThinking: { enabled, effort: 'high' },
    }).content) as Record<string, unknown>
    expect(config).toMatchObject({ alwaysThinkingEnabled: enabled, effortLevel: 'high' })
  })

  it('Codex 分别设置主模型和子代理的推理强度', () => {
    const config = buildClientConfig('codex', {
      ...input, codexReasoning: { effort: 'xhigh', subagentEffort: 'low' },
    }).content
    expect(config).toContain('model_reasoning_effort = "xhigh"\n')
    expect(config).toContain('[agents]\ndefault_subagent_model = "gateway-model"\ndefault_subagent_reasoning_effort = "low"')
    expect(config.indexOf('model_reasoning_effort')).toBeLessThan(config.indexOf('[agents]'))
  })

  it('OpenCode 为全部角色所用模型写入推理选项', () => {
    const config = JSON.parse(buildClientConfig('opencode', {
      ...input, openCodeModels: { plan: 'planner' }, openCodeReasoningEffort: 'high',
    }).content) as { provider: { gateway: { models: Record<string, unknown> } } }
    expect(config.provider.gateway.models).toEqual({
      'gateway-model': { name: 'gateway-model', options: { reasoningEffort: 'high' } },
      planner: { name: 'planner', options: { reasoningEffort: 'high' } },
    })
  })

  it('Pi 保留关闭的思考能力且不为未配置模型添加该字段', () => {
    const config = JSON.parse(buildClientConfig('pi', {
      ...input, piModels: [{ id: 'disabled', reasoning: false }, { id: 'unset' }],
    }).content) as { providers: { gateway: { models: Array<Record<string, unknown>> } } }
    expect(config.providers.gateway.models[0]).toMatchObject({ reasoning: false })
    expect(config.providers.gateway.models[1]).not.toHaveProperty('reasoning')
  })

  it.each([true, false])('Codex 显式切换思考模式 %s，覆盖主模型与子代理强度', (enabled) => {
    const file = buildClientConfig('codex', {
      ...input, thinkingEnabled: enabled, codexReasoning: { effort: 'high', subagentEffort: 'low' },
    })
    expect(file.content).toContain(`model_reasoning_effort = "${enabled ? 'high' : 'none'}"`)
    expect(file.content).toContain(`default_subagent_reasoning_effort = "${enabled ? 'low' : 'none'}"`)
  })

  it.each([true, false])('OpenCode 显式切换思考模式 %s', (enabled) => {
    const config = JSON.parse(buildClientConfig('opencode', {
      ...input, thinkingEnabled: enabled,
    }).content) as { provider: { gateway: { models: Record<string, { options: { reasoningEffort: string } }> } } }
    expect(config.provider.gateway.models['gateway-model']?.options.reasoningEffort).toBe(enabled ? 'medium' : 'none')
  })

  it.each([true, false])('Pi 通过独立 settings.json 设置思考模式 %s，保留模型能力', (enabled) => {
    const file = buildClientConfig('pi', {
      ...input, thinkingEnabled: enabled, piModels: [{ id: 'gateway-model', reasoning: true }],
    })
    expect(JSON.parse(file.content)).toMatchObject({ providers: { gateway: { models: [{ reasoning: true }] } } })
    expect(file.additionalFiles).toEqual([{
      filename: 'settings.json', location: '~/.pi/agent/settings.json',
      content: JSON.stringify({
        defaultThinkingLevel: enabled ? 'medium' : 'off',
        modelThinkingLevels: { 'gateway/gateway-model': enabled ? 'medium' : 'off' },
      }, null, 2) + '\n',
    }])
  })

  it('Pi 开启思考时为未声明能力的模型补齐能力标记，并保留明确不支持的模型', () => {
    const config = JSON.parse(buildClientConfig('pi', {
      ...input, thinkingEnabled: true,
      piModels: [{ id: 'unknown' }, { id: 'unsupported', reasoning: false }],
    }).content) as { providers: { gateway: { models: Array<Record<string, unknown>> } } }
    expect(config.providers.gateway.models).toMatchObject([
      { id: 'unknown', reasoning: true }, { id: 'unsupported', reasoning: false },
    ])
  })

  it('拒绝缺失的 API key、网关地址或模型 ID', () => {
    expect(() => buildClientConfig('pi', { ...input, apiKey: ' ' })).toThrow('API key')
    expect(() => buildClientConfig('pi', { ...input, baseUrl: '' })).toThrow('base URL')
    expect(() => buildClientConfig('pi', { ...input, modelId: '' })).toThrow('model ID')
  })
})
