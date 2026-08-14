export interface DeepSeekHarnessModel {
  canonical_name: string
  model_type: string
  enabled: boolean
}

export interface DeepSeekHarnessOptions {
  providerId: string
  displayName: string
  baseUrl: string
  apiKeyEnv: string
  apiKey: string
  api?: 'openai-responses' | 'openai-completions'
  defaultModel: string
  models: DeepSeekHarnessModel[]
}

export interface DeepSeekHarnessFiles {
  credentialsYaml: string
  settingsYaml: string
}

function quoteYamlScalar(value: string): string {
  const yamlKeywords = /^(?:null|true|false|yes|no|on|off|~)$/i
  const plainScalar = /^[A-Za-z_][A-Za-z0-9_.-]*$/
  return plainScalar.test(value) && !yamlKeywords.test(value) ? value : JSON.stringify(value)
}

export function buildDeepSeekHarnessFiles(options: DeepSeekHarnessOptions): DeepSeekHarnessFiles {
  const models = options.models
    .filter((model) => model.enabled)
    .sort((left, right) => {
      if (left.canonical_name < right.canonical_name) return -1
      if (left.canonical_name > right.canonical_name) return 1
      return 0
    })
  const api = options.api ?? 'openai-responses'

  const credentialsYaml = `${quoteYamlScalar(options.apiKeyEnv)}: ${JSON.stringify(options.apiKey)}\n`
  const modelYaml = models.map((model) => [
    `      - id: ${quoteYamlScalar(model.canonical_name)}`,
    `        name: ${quoteYamlScalar(model.canonical_name)}`,
    `        input: [${model.model_type === 'image' ? 'text, image' : 'text'}]`,
  ].join('\n')).join('\n')

  const settingsYaml = [
    'ui-onboarding:',
    '  welcomeNoticeVersion: "2026-08-13.1"',
    'llm-pi-ai:',
    '  providers:',
    `    ${quoteYamlScalar(options.providerId)}:`,
    `      displayName: ${quoteYamlScalar(options.displayName)}`,
    `      baseURL: ${quoteYamlScalar(options.baseUrl)}`,
    `      apiKeyEnv: ${quoteYamlScalar(options.apiKeyEnv)}`,
    `      api: ${quoteYamlScalar(api)}`,
    '      models:',
    modelYaml,
    'agent-default-model:',
    `  provider: ${quoteYamlScalar(options.providerId)}`,
    `  model: ${quoteYamlScalar(options.defaultModel)}`,
    '',
  ].join('\n')

  return { credentialsYaml, settingsYaml }
}
