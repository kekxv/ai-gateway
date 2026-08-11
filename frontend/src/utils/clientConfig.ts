export type ClientConfigTarget = 'claude' | 'codex' | 'opencode' | 'pi'

export interface ClientConfigInput {
  apiKey: string
  baseUrl: string
  modelId: string
  claudeModels?: Partial<ClaudeModelSelection>
  codexModels?: Partial<CodexModelSelection>
  openCodeModels?: Partial<OpenCodeModelSelection>
  piModelIds?: string[]
  piApi?: PiApi
}

export type PiApi = 'openai-completions' | 'openai-responses'

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
        effortLevel: 'medium',
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
    return {
      filename: 'config.toml',
      location: '~/.codex/config.toml',
      content: `model = "${tomlString(primary)}"
review_model = "${tomlString(review)}"
model_provider = "gateway"

[agents]
default_subagent_model = "${tomlString(subagent)}"

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
    const models = Object.fromEntries(
      [...new Set([primary, plan, build, review])].map((id) => [id, { name: id }]),
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

  const selectedPiModelIds = [...new Set((input.piModelIds ?? []).map((id) => id.trim()).filter(Boolean))]
  const piModelIds = selectedPiModelIds.length > 0 ? selectedPiModelIds : [modelId]
  const piApi = input.piApi ?? 'openai-completions'
  return {
    filename: 'models.json',
    location: '~/.pi/agent/models.json',
    content: `${JSON.stringify({
      providers: {
        gateway: {
          baseUrl: openAiBaseUrl,
          api: piApi,
          apiKey,
          models: piModelIds.map((id) => ({ id, name: id })),
        },
      },
    }, null, 2)}\n`,
  }
}
