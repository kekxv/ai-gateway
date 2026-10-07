export type ClientConfigTarget = 'claude' | 'codex' | 'opencode' | 'pi'

export interface ClientConfigInput {
  apiKey: string
  baseUrl: string
  modelId: string
  thinkingEnabled?: boolean
  claudeModels?: Partial<ClaudeModelSelection>
  codexModels?: Partial<CodexModelSelection>
  openCodeModels?: Partial<OpenCodeModelSelection>
  piModelIds?: string[]
  piModels?: PiModelSelection[]
  piApi?: PiApi
  claudeThinking?: { enabled?: boolean; effort?: ClaudeThinkingEffort }
  codexReasoning?: { effort?: CodexReasoningEffort; subagentEffort?: CodexReasoningEffort }
  openCodeReasoningEffort?: OpenCodeReasoningEffort
}

export type PiApi = 'openai-completions' | 'openai-responses'
export type ClaudeThinkingEffort = 'low' | 'medium' | 'high' | 'xhigh'
export type CodexReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max' | 'ultra'
export type OpenCodeReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max'

export interface PiModelSelection {
  id: string
  modelTypes?: string[]
  contextWindow?: number | null
  maxTokens?: number | null
  reasoning?: boolean | null
  inputPricePerMillion?: number
  outputPricePerMillion?: number
  cacheReadPricePerMillion?: number
  cacheWritePricePerMillion?: number
}

interface PiModelConfig {
  id: string
  name: string
  contextWindow?: number
  maxTokens?: number
  input?: string[]
  reasoning?: boolean
  cost: {
    input: number
    output: number
    cacheRead: number
    cacheWrite: number
  }
}

const piSupportedInputs = new Set(['text', 'image', 'audio'])

export interface ClaudeModelSelection {
  primary: string
  opus: string
  sonnet: string
  haiku: string
  subagent: string
}

export interface CodexModelSelection {
  primary: string
  review: string
  subagent: string
}

export interface OpenCodeModelSelection {
  primary: string
  plan: string
  build: string
  review: string
}

export interface ClientConfigFile {
  filename: string
  location: string
  content: string
  additionalFiles?: ClientConfigFile[]
}

function thinkingEffort<T extends string>(enabled: boolean | undefined, effort: T | undefined, off: T, fallback: T): T | undefined {
  if (enabled === false) return off
  if (enabled === true && (effort === undefined || effort === off)) return fallback
  return effort
}

function required(value: string, label: string): string {
  const normalized = value.trim()
  if (normalized === '') throw new Error(`${label} is required`)
  return normalized
}

function gatewayOrigin(value: string): string {
  const origin = required(value, 'base URL').replace(/\/+$/, '')
  try {
    new URL(origin)
  } catch {
    throw new Error('base URL must be a valid URL')
  }
  return origin
}

function tomlString(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function selectedModel(value: string | undefined, fallback: string): string {
  return value?.trim() || fallback
}

function piModelConfig(model: PiModelSelection): PiModelConfig {
  const id = required(model.id, 'Pi model ID')
  const input = (model.modelTypes ?? []).filter((type) => piSupportedInputs.has(type))
  return {
    id,
    name: id,
    ...(model.contextWindow == null ? {} : { contextWindow: model.contextWindow }),
    ...(model.maxTokens == null ? {} : { maxTokens: model.maxTokens }),
    ...(input.length > 0 ? { input: [...new Set(input)] } : {}),
    ...(model.reasoning == null ? {} : { reasoning: model.reasoning }),
    cost: {
      input: model.inputPricePerMillion ?? 0,
      output: model.outputPricePerMillion ?? 0,
      cacheRead: model.cacheReadPricePerMillion ?? 0,
      cacheWrite: model.cacheWritePricePerMillion ?? 0,
    },
  }
}

export function buildClientConfig(
  target: ClientConfigTarget,
  input: ClientConfigInput,
): ClientConfigFile {
  const apiKey = required(input.apiKey, 'API key')
  const baseUrl = gatewayOrigin(input.baseUrl)
  const modelId = required(input.modelId, 'model ID')
  const openAiBaseUrl = `${baseUrl}/v1`

  if (target === 'claude') {
    const claudeModels = input.claudeModels
    const thinkingEnabled = input.thinkingEnabled ?? input.claudeThinking?.enabled
    return {
      filename: 'settings.json',
      location: '~/.claude/settings.json',
      content: `${JSON.stringify({
        env: {
          NAME: 'AI Gateway',
          ANTHROPIC_AUTH_TOKEN: apiKey,
          ANTHROPIC_BASE_URL: baseUrl,
          ANTHROPIC_MODEL: selectedModel(claudeModels?.primary, modelId),
          ANTHROPIC_DEFAULT_OPUS_MODEL: selectedModel(claudeModels?.opus, modelId),
          ANTHROPIC_DEFAULT_SONNET_MODEL: selectedModel(claudeModels?.sonnet, modelId),
          ANTHROPIC_DEFAULT_HAIKU_MODEL: selectedModel(claudeModels?.haiku, modelId),
          CLAUDE_CODE_SUBAGENT_MODEL: selectedModel(claudeModels?.subagent, modelId),
        },
        ...(thinkingEnabled === undefined ? {} : {
          alwaysThinkingEnabled: thinkingEnabled,
        }),
        effortLevel: input.claudeThinking?.effort ?? 'medium',
        skipWorkflowUsageWarning: true,
        theme: 'light-daltonized',
        hasCompletedOnboarding: true,
      }, null, 2)}\n`,
    }
  }

  if (target === 'codex') {
    const codexModels = input.codexModels
    const primary = selectedModel(codexModels?.primary, modelId)
    const review = selectedModel(codexModels?.review, modelId)
    const subagent = selectedModel(codexModels?.subagent, modelId)
    const effort = thinkingEffort(input.thinkingEnabled, input.codexReasoning?.effort, 'none', 'medium')
    const subagentEffort = thinkingEffort(input.thinkingEnabled, input.codexReasoning?.subagentEffort, 'none', 'medium')
    return {
      filename: 'config.toml',
      location: '~/.codex/config.toml',
      content: `model = "${tomlString(primary)}"
review_model = "${tomlString(review)}"
model_provider = "gateway"
${effort === undefined ? '' : `model_reasoning_effort = "${tomlString(effort)}"\n`}
[agents]
default_subagent_model = "${tomlString(subagent)}"
${subagentEffort === undefined ? '' : `default_subagent_reasoning_effort = "${tomlString(subagentEffort)}"\n`}
[model_providers.gateway]
name = "AI Gateway"
base_url = "${tomlString(openAiBaseUrl)}"
experimental_bearer_token = "${tomlString(apiKey)}"
wire_api = "responses"
`,
    }
  }

  if (target === 'opencode') {
    const openCodeModels = input.openCodeModels
    const primary = selectedModel(openCodeModels?.primary, modelId)
    const plan = selectedModel(openCodeModels?.plan, modelId)
    const build = selectedModel(openCodeModels?.build, modelId)
    const review = selectedModel(openCodeModels?.review, modelId)
    const effort = thinkingEffort(input.thinkingEnabled, input.openCodeReasoningEffort, 'none', 'medium')
    const models = Object.fromEntries(
      [...new Set([primary, plan, build, review])].map((id) => [id, {
        name: id,
        ...(effort === undefined ? {} : {
          options: { reasoningEffort: effort },
        }),
      }]),
    )
    return {
      filename: 'opencode.json',
      location: './opencode.json',
      content: `${JSON.stringify({
        $schema: 'https://opencode.ai/config.json',
        model: `gateway/${primary}`,
        agent: {
          plan: { model: `gateway/${plan}` },
          build: { model: `gateway/${build}` },
          review: {
            description: 'Reviews code for best practices and potential issues',
            mode: 'subagent',
            model: `gateway/${review}`,
            prompt: 'You are a code reviewer. Focus on security, performance, and maintainability.',
            permission: { edit: 'deny' },
          },
        },
        provider: {
          gateway: {
            npm: '@ai-sdk/openai-compatible',
            name: 'AI Gateway',
            options: { baseURL: openAiBaseUrl, apiKey },
            models,
          },
        },
      }, null, 2)}\n`,
    }
  }

  const selectedPiModels = (input.piModels ?? input.piModelIds?.map((id) => ({ id })) ?? [])
    .map((model) => ({ ...model, id: model.id.trim() }))
    .filter((model) => model.id !== '')
  const piModels: PiModelSelection[] = [...new Map(selectedPiModels.map((model) => [model.id, model])).values()]
  if (piModels.length === 0) piModels.push({ id: modelId })
  const piApi = input.piApi ?? 'openai-completions'
  return {
    filename: 'models.json',
    location: '~/.pi/agent/models.json',
    ...(input.thinkingEnabled === undefined ? {} : {
      additionalFiles: [{
        filename: 'settings.json',
        location: '~/.pi/agent/settings.json',
        content: `${JSON.stringify({
          defaultThinkingLevel: input.thinkingEnabled ? 'medium' : 'off',
          modelThinkingLevels: Object.fromEntries(piModels.map((model) => [
            `gateway/${model.id}`, input.thinkingEnabled ? 'medium' : 'off',
          ])),
        }, null, 2)}\n`,
      }],
    }),
    content: `${JSON.stringify({
      providers: {
        gateway: {
          baseUrl: openAiBaseUrl,
          api: piApi,
          apiKey,
          models: piModels.map((model) => piModelConfig(input.thinkingEnabled === true
            ? { ...model, reasoning: model.reasoning ?? true }
            : model)),
        },
      },
    }, null, 2)}\n`,
  }
}
