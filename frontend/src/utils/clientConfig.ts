export type ClientConfigTarget = 'claude' | 'codex' | 'opencode' | 'pi'

export interface ClientConfigInput {
  apiKey: string
  baseUrl: string
  modelId: string
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

export function buildClientConfig(
  target: ClientConfigTarget,
  input: ClientConfigInput,
): ClientConfigFile {
  const apiKey = required(input.apiKey, 'API key')
  const baseUrl = gatewayOrigin(input.baseUrl)
  const modelId = required(input.modelId, 'model ID')
  const openAiBaseUrl = `${baseUrl}/v1`

  if (target === 'claude') {
    return {
      filename: 'settings.json',
      location: '~/.claude/settings.json',
      content: `${JSON.stringify({
        env: {
          NAME: 'AI Gateway',
          ANTHROPIC_AUTH_TOKEN: apiKey,
          ANTHROPIC_BASE_URL: baseUrl,
          ANTHROPIC_MODEL: modelId,
          ANTHROPIC_DEFAULT_OPUS_MODEL: modelId,
          ANTHROPIC_DEFAULT_SONNET_MODEL: modelId,
          ANTHROPIC_DEFAULT_HAIKU_MODEL: modelId,
          CLAUDE_CODE_SUBAGENT_MODEL: modelId,
        },
        effortLevel: 'medium',
        skipWorkflowUsageWarning: true,
        theme: 'light-daltonized',
        hasCompletedOnboarding: true,
      }, null, 2)}\n`,
    }
  }

  if (target === 'codex') {
    return {
      filename: 'config.toml',
      location: '~/.codex/config.toml',
      content: `model = "${tomlString(modelId)}"
model_provider = "gateway"

[model_providers.gateway]
name = "AI Gateway"
base_url = "${tomlString(openAiBaseUrl)}"
experimental_bearer_token = "${tomlString(apiKey)}"
wire_api = "responses"
`,
    }
  }

  if (target === 'opencode') {
    return {
      filename: 'opencode.json',
      location: './opencode.json',
      content: `${JSON.stringify({
        $schema: 'https://opencode.ai/config.json',
        model: `gateway/${modelId}`,
        provider: {
          gateway: {
            npm: '@ai-sdk/openai-compatible',
            name: 'AI Gateway',
            options: { baseURL: openAiBaseUrl, apiKey },
            models: { [modelId]: { name: modelId } },
          },
        },
      }, null, 2)}\n`,
    }
  }

  return {
    filename: 'models.json',
    location: '~/.pi/agent/models.json',
    content: `${JSON.stringify({
      providers: {
        gateway: {
          baseUrl: openAiBaseUrl,
          api: 'openai-completions',
          apiKey,
          models: [{ id: modelId, name: modelId }],
        },
      },
    }, null, 2)}\n`,
  }
}
