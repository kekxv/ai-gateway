<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Delete, MagicStick, Plus } from '@element-plus/icons-vue'
import {
  ElButton,
  ElCheckbox,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElSwitch,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-checkbox.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-input-number.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-switch.css'

import type {
  BalanceQueryType,
  JsonObject,
  Protocol,
  ProviderBalanceCandidate,
  ProviderBalanceConfigInput,
  ProviderBalanceDetectionResult,
  ProviderCreate,
  ProviderProxyInput,
  ProviderProtocolInput,
  ProviderResponse,
  ProviderUpdate,
} from '@/api/types'

interface ProtocolRow {
  key: number
  id?: number
  protocol: Protocol
  baseUrl: string
  websocketUrl: string
  extraHeadersText: string
  supportsResponses: boolean
  enabled: boolean
  baseUrlError: string
  extraHeadersError: string
}

type AuthScheme = 'protocol-default' | 'bearer' | 'apikey' | 'none'
type AuthHeader = 'protocol-default' | 'authorization' | 'x-api-key' | 'custom'
type ProxyMode = 'inherit' | 'direct' | 'custom'
type ProxyAuthType = 'none' | 'basic' | 'headers'
type BalanceTypeOption = BalanceQueryType | 'none'

const props = defineProps<{
  modelValue: boolean
  provider: ProviderResponse | null
  submitting: boolean
  detecting?: boolean
  detection?: ProviderBalanceDetectionResult | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: ProviderCreate | ProviderUpdate]
  detect: []
}>()

const name = ref('')
const apiKey = ref('')
const advancedCredentialText = ref('')
const authScheme = ref<AuthScheme>('protocol-default')
const authHeader = ref<AuthHeader>('protocol-default')
const customAuthHeader = ref('')
const proxyMode = ref<ProxyMode>('inherit')
const proxyUrl = ref('')
const proxyAuthType = ref<ProxyAuthType>('none')
const proxyUsername = ref('')
const proxyPassword = ref('')
const proxyHeadersText = ref('')
const enabled = ref(true)
const autoLoadModels = ref(false)
const syncInterval = ref<number | null>(3600)
const costMultiplier = ref(1.0)
const publicMultiplier = ref(1.0)
const balanceQueryType = ref<BalanceTypeOption>('none')
const balanceAutoSync = ref(false)
const balanceSyncInterval = ref<number | null>(3600)
const balanceBaseUrl = ref('')
const balanceApiKey = ref('')
const balanceUserId = ref('')
const balancePath = ref('')
const balanceMethod = ref<'GET' | 'POST'>('GET')
const balanceAmountPath = ref('')
const balanceUsedPath = ref('')
const balanceAvailablePath = ref('')
const balanceCurrency = ref('')
const balanceDivisor = ref<number | null>(null)
const balanceHeadersText = ref('')
const balanceCandidates = ref<ProviderBalanceCandidate[]>([])
const protocols = ref<ProtocolRow[]>([])
const nameError = ref('')
const advancedCredentialError = ref('')
const authHeaderError = ref('')
const proxyError = ref('')
const syncIntervalError = ref('')
const balanceError = ref('')
const balanceIntervalError = ref('')
const balanceHeadersError = ref('')
const formContent = ref<HTMLElement | null>(null)
let nextProtocolKey = 1

const editing = computed(() => props.provider !== null)
const drawerTitle = computed(() => (editing.value ? '编辑供应商' : '新建供应商'))
const showCustomHeaderInput = computed(
  () => authScheme.value !== 'none' && authHeader.value === 'custom',
)
const balanceConfigured = computed(() => balanceQueryType.value !== 'none')
const balanceClearApiKey = ref(false)
const balanceClearHeaders = ref(false)
const balanceSecretConfigured = computed(
  () => props.provider?.balance?.config.has_api_key === true,
)
const balanceHeadersConfigured = computed(
  () => props.provider?.balance?.config.has_headers === true,
)

const balanceTypeLabels: Readonly<Record<BalanceQueryType, string>> = {
  new_api: 'new-api / one-api',
  deepseek: 'DeepSeek 官方',
  openrouter: 'OpenRouter',
  custom: '自定义接口',
}

const validAuthHeaderName = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/
const disallowedAuthHeaders = new Set([
  'connection',
  'content-length',
  'cookie',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
])

function newProtocolRow(): ProtocolRow {
  return {
    key: nextProtocolKey++,
    protocol: 'openai',
    baseUrl: '',
    websocketUrl: '',
    extraHeadersText: '',
    supportsResponses: true,
    enabled: true,
    baseUrlError: '',
    extraHeadersError: '',
  }
}

function resetForm(): void {
  const provider = props.provider
  name.value = provider?.name ?? ''
  apiKey.value = ''
  advancedCredentialText.value = ''
  authScheme.value = 'protocol-default'
  authHeader.value = 'protocol-default'
  customAuthHeader.value = ''
  proxyMode.value = provider?.proxy.mode ?? 'inherit'
  proxyUrl.value = provider?.proxy.url ?? ''
  proxyAuthType.value = provider?.proxy.auth_type ?? 'none'
  proxyUsername.value = ''
  proxyPassword.value = ''
  proxyHeadersText.value = ''
  enabled.value = provider?.enabled ?? true
  autoLoadModels.value = provider?.auto_load_models ?? false
  syncInterval.value = provider?.model_sync_interval_seconds ?? 3600
  costMultiplier.value = typeof provider?.cost_multiplier === 'string'
    ? parseFloat(provider.cost_multiplier)
    : (provider?.cost_multiplier ?? 1.0)
  publicMultiplier.value = typeof provider?.public_multiplier === 'string'
    ? parseFloat(provider.public_multiplier)
    : (provider?.public_multiplier ?? 1.0)
  const balance = provider?.balance ?? null
  balanceQueryType.value = balance?.query_type ?? 'none'
  balanceAutoSync.value = balance?.auto_sync ?? false
  balanceSyncInterval.value = balance?.sync_interval_seconds ?? 3600
  balanceBaseUrl.value = balance?.config.base_url ?? ''
  balanceApiKey.value = ''
  balanceClearApiKey.value = false
  balanceClearHeaders.value = false
  balanceUserId.value = balance?.config.user_id ?? ''
  balancePath.value = balance?.config.path ?? ''
  balanceMethod.value = balance?.config.method === 'POST' ? 'POST' : 'GET'
  balanceAmountPath.value = balance?.config.amount_path ?? ''
  balanceUsedPath.value = balance?.config.used_path ?? ''
  balanceAvailablePath.value = balance?.config.available_path ?? ''
  balanceCurrency.value = balance?.config.currency ?? ''
  balanceDivisor.value =
    balance?.config.divisor == null ? null : Number.parseFloat(balance.config.divisor)
  balanceHeadersText.value = ''
  balanceCandidates.value = []
  protocols.value =
    provider === null
      ? [newProtocolRow()]
      : provider.protocols.map((protocol) => ({
          key: nextProtocolKey++,
          id: protocol.id,
          protocol: protocol.protocol,
          baseUrl: protocol.base_url,
          websocketUrl: protocol.websocket_url ?? '',
          extraHeadersText: '',
          supportsResponses: protocol.supports_responses,
          enabled: protocol.enabled,
          baseUrlError: '',
          extraHeadersError: '',
        }))
  nameError.value = ''
  advancedCredentialError.value = ''
  authHeaderError.value = ''
  proxyError.value = ''
  syncIntervalError.value = ''
  balanceError.value = ''
  balanceIntervalError.value = ''
  balanceHeadersError.value = ''
}

function clearSensitiveState(): void {
  apiKey.value = ''
  advancedCredentialText.value = ''
  proxyUsername.value = ''
  proxyPassword.value = ''
  proxyHeadersText.value = ''
  balanceApiKey.value = ''
  balanceHeadersText.value = ''
  for (const row of protocols.value) row.extraHeadersText = ''
}

watch(
  () => [props.modelValue, props.provider] as const,
  ([open]) => {
    if (open) resetForm()
    else clearSensitiveState()
  },
  { immediate: true, flush: 'sync' },
)

watch(
  () => props.detection,
  (detection) => {
    if (detection === null || detection === undefined) {
      balanceCandidates.value = []
      return
    }
    balanceCandidates.value = detection.candidates
    if (detection.applied !== null) balanceQueryType.value = detection.applied
  },
  { immediate: true },
)

onBeforeUnmount(clearSensitiveState)

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseExtraHeaders(row: ProtocolRow): JsonObject | undefined {
  if (row.extraHeadersText.trim() === '') return undefined
  try {
    const value: unknown = JSON.parse(row.extraHeadersText)
    if (!isJsonObject(value)) {
      row.extraHeadersError = '必须是 JSON 对象，不能使用数组或单个值'
      return undefined
    }
    return value
  } catch {
    row.extraHeadersError = 'JSON 格式不正确'
    return undefined
  }
}

function parseAdvancedCredential(): JsonObject | undefined {
  if (advancedCredentialText.value.trim() === '') return undefined
  try {
    const value: unknown = JSON.parse(advancedCredentialText.value)
    if (!isJsonObject(value)) {
      advancedCredentialError.value = '必须是 JSON 对象，不能使用数组或单个值'
      return undefined
    }
    return value
  } catch {
    advancedCredentialError.value = 'JSON 格式不正确'
    return undefined
  }
}

function buildCredential(): JsonObject | undefined {
  const advancedCredential = parseAdvancedCredential()
  if (advancedCredentialError.value !== '') return undefined
  const key = apiKey.value.trim()
  if (advancedCredential === undefined && key === '') return undefined
  const credential: JsonObject = { ...(advancedCredential ?? {}) }

  if (key !== '') credential.api_key = key
  if (typeof credential.api_key !== 'string' || credential.api_key.trim() === '') return credential

  if (authScheme.value === 'protocol-default') delete credential.auth_scheme
  else {
    credential.auth_scheme =
      authScheme.value === 'none'
        ? 'none'
        : authScheme.value === 'bearer'
          ? 'Bearer'
          : 'ApiKey'
  }
  if (authScheme.value === 'none') {
    delete credential.auth_header
    return credential
  }

  if (authHeader.value === 'protocol-default') delete credential.auth_header
  else if (authHeader.value === 'authorization') credential.auth_header = 'Authorization'
  else if (authHeader.value === 'x-api-key') credential.auth_header = 'x-api-key'
  else {
    const header = customAuthHeader.value.trim()
    if (
      !validAuthHeaderName.test(header) ||
      header.length > 128 ||
      disallowedAuthHeaders.has(header.toLocaleLowerCase('en-US'))
    ) {
      authHeaderError.value = '授权头名称格式不正确'
      return undefined
    }
    credential.auth_header = header
  }

  return credential
}

function validProxyUrl(value: string): boolean {
  try {
    const parsed = new URL(value)
    return (
      (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      parsed.hostname !== '' &&
      parsed.username === '' &&
      parsed.password === '' &&
      (parsed.pathname === '' || parsed.pathname === '/') &&
      parsed.search === '' &&
      parsed.hash === ''
    )
  } catch {
    return false
  }
}

function parseProxyHeaders(): Record<string, string> | undefined {
  try {
    const value: unknown = JSON.parse(proxyHeadersText.value)
    if (!isJsonObject(value) || Object.keys(value).length === 0) return undefined
    const headers: Record<string, string> = {}
    for (const [name, headerValue] of Object.entries(value)) {
      if (typeof headerValue !== 'string') return undefined
      headers[name] = headerValue
    }
    return headers
  } catch {
    return undefined
  }
}

function buildProxy(protocolPayload: ProviderProtocolInput[]): ProviderProxyInput | null | undefined {
  const provider = props.provider
  const original = provider?.proxy
  if (proxyMode.value === 'inherit') {
    return original !== undefined && original.mode !== 'inherit' ? null : undefined
  }
  if (proxyMode.value === 'direct') {
    return original?.mode === 'direct' ? undefined : { mode: 'direct' }
  }

  const url = proxyUrl.value.trim()
  const originalAuthType = original?.auth_type ?? 'none'
  const secretsUntouched =
    proxyUsername.value === '' && proxyPassword.value === '' && proxyHeadersText.value === ''
  if (
    original?.mode === 'custom' &&
    url === original.url &&
    proxyAuthType.value === originalAuthType &&
    secretsUntouched
  ) {
    return undefined
  }
  if (!validProxyUrl(url)) {
    proxyError.value = '请输入不含路径、查询参数或帐号密码的 HTTP(S) 代理地址'
    return undefined
  }
  if (proxyAuthType.value === 'none') return { mode: 'custom', url }
  if (proxyAuthType.value === 'basic') {
    if (proxyUsername.value === '' || proxyPassword.value === '') {
      proxyError.value = '请完整填写代理帐号和密码'
      return undefined
    }
    return {
      mode: 'custom',
      url,
      auth: {
        type: 'basic',
        username: proxyUsername.value,
        password: proxyPassword.value,
      },
    }
  }
  const headers = parseProxyHeaders()
  if (headers === undefined) {
    proxyError.value = '自定义代理鉴权必须是非空的字符串 Header JSON 对象'
    return undefined
  }
  if (protocolPayload.some((protocol) => protocol.websocket_url !== null)) {
    proxyError.value = '自定义代理鉴权请求头不支持 WebSocket 入口'
    return undefined
  }
  return { mode: 'custom', url, auth: { type: 'headers', headers } }
}

function parseBalanceHeaders(): Record<string, string> | undefined {
  if (balanceHeadersText.value.trim() === '') return undefined
  try {
    const value: unknown = JSON.parse(balanceHeadersText.value)
    if (!isJsonObject(value) || Object.keys(value).length === 0) {
      balanceHeadersError.value = '必须是字符串键值的 JSON 对象'
      return undefined
    }
    const headers: Record<string, string> = {}
    for (const [name, headerValue] of Object.entries(value)) {
      if (typeof headerValue !== 'string') {
        balanceHeadersError.value = '余额查询请求头的值必须是字符串'
        return undefined
      }
      headers[name] = headerValue
    }
    return headers
  } catch {
    balanceHeadersError.value = 'JSON 格式不正确'
    return undefined
  }
}

function buildBalanceConfig(): ProviderBalanceConfigInput | null | undefined {
  balanceError.value = ''
  balanceHeadersError.value = ''
  if (!balanceConfigured.value) return null
  if (
    balanceDivisor.value !== null &&
    (!Number.isFinite(balanceDivisor.value) || balanceDivisor.value <= 0)
  ) {
    balanceError.value = '余额除数必须大于 0'
    return undefined
  }
  // Non-secret fields are always submitted, as null when empty, so clearing a field
  // restores the built-in default instead of silently keeping the stored value.
  const config: ProviderBalanceConfigInput = {
    base_url: balanceBaseUrl.value.trim() || null,
    user_id: balanceUserId.value.trim() || null,
    currency: balanceCurrency.value.trim() || null,
    divisor: balanceDivisor.value,
  }
  if (balanceApiKey.value.trim() !== '') {
    config.api_key = balanceApiKey.value.trim()
  } else if (balanceClearApiKey.value) {
    config.api_key = null
  }
  if (balanceQueryType.value === 'custom') {
    if (balancePath.value.trim() === '') {
      balanceError.value = '自定义接口需要填写请求路径'
      return undefined
    }
    if (balanceAmountPath.value.trim() === '') {
      balanceError.value = '自定义接口需要填写余额字段路径'
      return undefined
    }
    config.path = balancePath.value.trim()
    config.method = balanceMethod.value
    config.amount_path = balanceAmountPath.value.trim()
    config.used_path = balanceUsedPath.value.trim() || null
    config.available_path = balanceAvailablePath.value.trim() || null
  }
  const headers = parseBalanceHeaders()
  if (balanceHeadersError.value !== '') return undefined
  if (headers !== undefined) {
    config.headers = headers
  } else if (balanceClearHeaders.value) {
    config.headers = null
  }
  return config
}

function balanceIntervalSeconds(): number {
  return balanceSyncInterval.value ?? 3600
}

function nextBalanceType(): BalanceQueryType | null {
  return balanceConfigured.value && balanceQueryType.value !== 'none' ? balanceQueryType.value : null
}

function balanceSectionChanged(): boolean {
  const snapshot = props.provider?.balance
  const nextType = nextBalanceType()
  if (snapshot === undefined) return nextType !== null
  if (nextType !== snapshot.query_type) return true
  if (nextType === null) return false
  if (balanceAutoSync.value !== snapshot.auto_sync) return true
  if (balanceIntervalSeconds() !== snapshot.sync_interval_seconds) return true
  const storedDivisor =
    snapshot.config.divisor === null ? null : Number.parseFloat(snapshot.config.divisor)
  if ((balanceBaseUrl.value.trim() || null) !== snapshot.config.base_url) return true
  if ((balanceUserId.value.trim() || null) !== snapshot.config.user_id) return true
  if ((balanceCurrency.value.trim() || null) !== snapshot.config.currency) return true
  if ((balanceDivisor.value ?? null) !== storedDivisor) return true
  if (balanceApiKey.value.trim() !== '' || balanceClearApiKey.value) return true
  if (balanceHeadersText.value.trim() !== '' || balanceClearHeaders.value) return true
  if (nextType === 'custom') {
    if (balancePath.value.trim() !== (snapshot.config.path ?? '')) return true
    if (balanceMethod.value !== snapshot.config.method) return true
    if (balanceAmountPath.value.trim() !== (snapshot.config.amount_path ?? '')) return true
    if ((balanceUsedPath.value.trim() || null) !== snapshot.config.used_path) return true
    if ((balanceAvailablePath.value.trim() || null) !== snapshot.config.available_path) return true
  }
  return false
}

function addProtocol(): void {
  protocols.value.push(newProtocolRow())
}
function removeProtocol(index: number): void {
  protocols.value.splice(index, 1)
}

function requestClose(): void {
  if (props.submitting) return
  clearSensitiveState()
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value) {
    if (props.submitting) return
    clearSensitiveState()
  }
  emit('update:modelValue', value)
}

function handleBeforeClose(done: () => void): void {
  if (props.submitting) return
  clearSensitiveState()
  done()
}

async function focusInvalidField(selector: string): Promise<void> {
  await nextTick()
  const target = formContent.value?.querySelector<HTMLElement>(selector)
  if (target === undefined || target === null) return
  if (typeof target.scrollIntoView === 'function') {
    target.scrollIntoView({ block: 'center' })
  }
  target.focus()
}

function normalizedProtocol(row: ProtocolRow): ProviderProtocolInput {
  const protocol: ProviderProtocolInput = {
    protocol: row.protocol,
    base_url: row.baseUrl.trim(),
    websocket_url: row.websocketUrl.trim() || null,
    supports_responses: row.protocol === 'openai' ? row.supportsResponses : true,
    enabled: row.enabled,
  }
  if (row.id !== undefined) protocol.id = row.id
  return protocol
}

function protocolsChanged(): boolean {
  const provider = props.provider
  if (provider === null || protocols.value.length !== provider.protocols.length) return true
  return protocols.value.some((row, index) => {
    const original = provider.protocols[index]
    if (original === undefined) return true
    return (
      row.id !== original.id ||
      row.protocol !== original.protocol ||
      row.baseUrl.trim() !== original.base_url ||
      (row.websocketUrl.trim() || null) !== original.websocket_url ||
      (row.protocol === 'openai' ? row.supportsResponses : true) !==
        original.supports_responses ||
      row.enabled !== original.enabled ||
      row.extraHeadersText.trim() !== ''
    )
  })
}

function buildProtocols(): ProviderProtocolInput[] | undefined {
  const payload = protocols.value.map((row) => {
    row.baseUrlError = ''
    row.extraHeadersError = ''
    if (row.baseUrl.trim() === '') {
      row.baseUrlError = '请输入 HTTP 基础地址'
    }
    const item = normalizedProtocol(row)
    const extraHeaders = parseExtraHeaders(row)
    if (extraHeaders !== undefined) item.extra_headers = extraHeaders
    return item
  })
  const hasError = protocols.value.some(
    (row) => row.baseUrlError !== '' || row.extraHeadersError !== '',
  )
  return hasError ? undefined : payload
}

function submitForm(): void {
  if (props.submitting) return
  nameError.value = ''
  advancedCredentialError.value = ''
  authHeaderError.value = ''
  proxyError.value = ''
  syncIntervalError.value = ''
  balanceError.value = ''
  balanceIntervalError.value = ''
  balanceHeadersError.value = ''
  if (name.value.trim() === '') nameError.value = '请输入供应商名称'
  const interval = syncInterval.value
  if (typeof interval !== 'number' || !Number.isInteger(interval) || interval < 1) {
    syncIntervalError.value = '请输入大于等于 1 的整数'
  }
  const balanceInterval = balanceSyncInterval.value
  if (
    balanceConfigured.value &&
    (typeof balanceInterval !== 'number' || !Number.isInteger(balanceInterval) || balanceInterval < 1)
  ) {
    balanceIntervalError.value = '请输入大于等于 1 的整数'
  }

  const protocolPayload = buildProtocols()
  const credential = buildCredential()
  const proxy = protocolPayload === undefined ? undefined : buildProxy(protocolPayload)
  const balanceConfig = buildBalanceConfig()
  if (
    nameError.value !== '' ||
    advancedCredentialError.value !== '' ||
    authHeaderError.value !== '' ||
    proxyError.value !== '' ||
    syncIntervalError.value !== '' ||
    balanceError.value !== '' ||
    balanceIntervalError.value !== '' ||
    balanceHeadersError.value !== '' ||
    protocolPayload === undefined ||
    balanceConfig === undefined
  ) {
    let selector = '[data-validation="name"] input'
    if (nameError.value === '' && syncIntervalError.value !== '') {
      selector = '[data-validation="sync-interval"] input'
    } else if (
      nameError.value === '' &&
      syncIntervalError.value === '' &&
      advancedCredentialError.value !== ''
    ) {
      selector = '[data-validation="credential"] textarea'
    } else if (
      nameError.value === '' &&
      syncIntervalError.value === '' &&
      advancedCredentialError.value === '' &&
      authHeaderError.value !== ''
    ) {
      selector = '[data-validation="auth-header"] input'
    } else if (
      nameError.value === '' &&
      syncIntervalError.value === '' &&
      advancedCredentialError.value === '' &&
      authHeaderError.value === '' &&
      (balanceError.value !== '' || balanceIntervalError.value !== '')
    ) {
      selector =
        balanceError.value !== ''
          ? '[data-validation="balance"] input'
          : '[data-validation="balance-interval"] input'
    } else if (
      nameError.value === '' &&
      syncIntervalError.value === '' &&
      advancedCredentialError.value === '' &&
      authHeaderError.value === '' &&
      balanceError.value === '' &&
      balanceIntervalError.value === '' &&
      balanceHeadersError.value !== ''
    ) {
      selector = '[data-validation="balance-headers"] textarea'
    } else if (
      nameError.value === '' &&
      syncIntervalError.value === '' &&
      advancedCredentialError.value === '' &&
      balanceError.value === '' &&
      balanceIntervalError.value === ''
    ) {
      const invalidIndex = protocols.value.findIndex(
        (row) => row.baseUrlError !== '' || row.extraHeadersError !== '',
      )
      const invalidRow = protocols.value[invalidIndex]
      selector =
        invalidRow?.baseUrlError !== ''
          ? `[data-validation="protocol-base-${String(invalidIndex)}"] input`
          : `[data-validation="protocol-extra-${String(invalidIndex)}"] textarea`
    }
    void focusInvalidField(selector)
    return
  }
  if (interval === null) return

  const balanceType = nextBalanceType()
  const balanceIntervalValue = balanceIntervalSeconds()

  if (!editing.value) {
    const payload: ProviderCreate = {
      name: name.value.trim(),
      enabled: enabled.value,
      auto_load_models: autoLoadModels.value,
      model_sync_interval_seconds: interval,
      protocols: protocolPayload,
      cost_multiplier: costMultiplier.value,
      public_multiplier: publicMultiplier.value,
    }
    if (credential !== undefined) payload.credential = credential
    if (proxy !== undefined && proxy !== null) payload.proxy = proxy
    if (balanceType !== null) {
      payload.balance_query_type = balanceType
      payload.balance_auto_sync = balanceAutoSync.value
      payload.balance_sync_interval_seconds = balanceIntervalValue
      if (balanceConfig !== null) payload.balance_config = balanceConfig
    }
    emit('submit', payload)
    return
  }

  const provider = props.provider
  if (provider === null) return
  const payload: ProviderUpdate = {}
  if (name.value.trim() !== provider.name) payload.name = name.value.trim()
  if (credential !== undefined) payload.credential = credential
  if (proxy !== undefined) payload.proxy = proxy
  if (enabled.value !== provider.enabled) payload.enabled = enabled.value
  if (autoLoadModels.value !== provider.auto_load_models) {
    payload.auto_load_models = autoLoadModels.value
  }
  if (interval !== provider.model_sync_interval_seconds) {
    payload.model_sync_interval_seconds = interval
  }
  if (protocolsChanged()) payload.protocols = protocolPayload
  const providerCostMultiplier = typeof provider.cost_multiplier === 'string'
    ? parseFloat(provider.cost_multiplier)
    : provider.cost_multiplier
  if (costMultiplier.value !== providerCostMultiplier) {
    payload.cost_multiplier = costMultiplier.value
  }
  const providerPublicMultiplier = typeof provider.public_multiplier === 'string'
    ? parseFloat(provider.public_multiplier)
    : provider.public_multiplier
  if (publicMultiplier.value !== providerPublicMultiplier) {
    payload.public_multiplier = publicMultiplier.value
  }
  if (balanceSectionChanged()) {
    payload.balance_query_type = balanceType
    payload.balance_auto_sync = balanceType === null ? false : balanceAutoSync.value
    payload.balance_sync_interval_seconds = balanceIntervalValue
    if (balanceConfig !== null) payload.balance_config = balanceConfig
  }
  emit('submit', payload)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(94vw, 52rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleBeforeClose"
    destroy-on-close
    @closed="clearSensitiveState"
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">{{ drawerTitle }}</h2>
        <p class="drawer-description">配置供应商连接信息与一个或多个协议入口。</p>
      </div>
    </template>

    <ElForm :disabled="submitting" label-position="top" @submit.prevent="submitForm">
      <div ref="formContent">
        <div class="form-grid">
          <ElFormItem data-validation="name" label="供应商名称" :error="nameError">
            <ElInput v-model="name" data-test="provider-name" maxlength="255" />
          </ElFormItem>
          <ElFormItem
            data-test="sync-interval-field"
            data-validation="sync-interval"
            label="模型同步间隔（秒）"
            :error="syncIntervalError"
          >
            <ElInputNumber
              v-model="syncInterval"
              data-test="provider-sync-interval"
              :min="1"
              :step="60"
              controls-position="right"
            />
          </ElFormItem>
          <ElFormItem
            data-test="cost-multiplier-field"
            data-validation="cost-multiplier"
            label="成本倍率"
          >
            <ElInputNumber
              v-model="costMultiplier"
              data-test="provider-cost-multiplier"
              :min="0.10"
              :max="10.00"
              :step="0.1"
              :precision="2"
              controls-position="right"
            />
            <div class="form-help">
              用于计算平台实际成本（0.10 ~ 10.00）
            </div>
          </ElFormItem>
          <ElFormItem
            data-test="public-multiplier-field"
            data-validation="public-multiplier"
            label="公开倍率"
          >
            <ElInputNumber
              v-model="publicMultiplier"
              data-test="provider-public-multiplier"
              :min="0.10"
              :max="10.00"
              :step="0.1"
              :precision="2"
              controls-position="right"
            />
            <div class="form-help">用于用户价格展示与账户扣费（0.10 ~ 10.00）</div>
          </ElFormItem>
        </div>

        <div class="credential-section">
          <h3 class="credential-section__title">
            {{ editing ? '替换 API 密钥（留空则保持原值）' : 'API 密钥' }}
          </h3>
          <ElFormItem data-validation="api-key">
            <ElInput
              v-model="apiKey"
              data-test="provider-api-key"
              type="password"
              show-password
              spellcheck="false"
              placeholder="sk-..."
            />
          </ElFormItem>

          <ElFormItem
            data-validation="credential"
            label="高级凭据 JSON（可选）"
            :error="advancedCredentialError"
          >
            <ElInput
              v-model="advancedCredentialText"
              data-test="provider-credential"
              type="textarea"
              :rows="4"
              spellcheck="false"
              placeholder='例如：{"api_key":"sk-...","organization":"team-a"}'
            />
            <p class="form-help">可添加供应商专用字段；引导填写的 API 密钥和授权设置会优先使用。</p>
          </ElFormItem>

          <div class="credential-options">
            <ElFormItem label="授权方式">
              <select v-model="authScheme" data-test="provider-auth-scheme">
                <option value="protocol-default">按协议默认</option>
                <option value="bearer">Bearer Token</option>
                <option value="apikey">API Key</option>
                <option value="none">无（不添加授权头）</option>
              </select>
            </ElFormItem>

            <ElFormItem label="授权头">
              <select
                v-model="authHeader"
                data-test="provider-auth-header"
                :disabled="authScheme === 'none'"
              >
                <option value="protocol-default">按协议默认</option>
                <option value="authorization">Authorization</option>
                <option value="x-api-key">x-api-key</option>
                <option value="custom">自定义</option>
              </select>
            </ElFormItem>
          </div>

          <ElFormItem
            v-if="showCustomHeaderInput"
            data-validation="auth-header"
            label="自定义授权头名称"
            :error="authHeaderError"
          >
            <ElInput
              v-model="customAuthHeader"
              data-test="provider-custom-header"
              placeholder="例如：X-API-Key"
            />
          </ElFormItem>
        </div>

        <div class="credential-section proxy-section">
          <h3 class="credential-section__title">HTTP(S) 出站代理</h3>
          <div class="credential-options">
            <ElFormItem label="代理模式" :error="proxyError" data-validation="proxy">
              <select v-model="proxyMode" data-test="provider-proxy-mode">
                <option value="inherit">继承全局配置</option>
                <option value="direct">强制直连</option>
                <option value="custom">供应商专用代理</option>
              </select>
            </ElFormItem>
            <ElFormItem v-if="proxyMode === 'custom'" label="代理鉴权">
              <select v-model="proxyAuthType" data-test="provider-proxy-auth-type">
                <option value="none">无</option>
                <option value="basic">帐号密码</option>
                <option value="headers">自定义请求头</option>
              </select>
            </ElFormItem>
          </div>
          <template v-if="proxyMode === 'custom'">
            <ElFormItem label="代理地址">
              <ElInput
                v-model="proxyUrl"
                data-test="provider-proxy-url"
                spellcheck="false"
                placeholder="http://proxy.example.com:8080"
              />
            </ElFormItem>
            <div v-if="proxyAuthType === 'basic'" class="credential-options">
              <ElFormItem :label="editing && props.provider?.proxy.has_auth ? '代理帐号（重新配置时必填）' : '代理帐号'">
                <ElInput
                  v-model="proxyUsername"
                  data-test="provider-proxy-username"
                  autocomplete="off"
                  spellcheck="false"
                />
              </ElFormItem>
              <ElFormItem :label="editing && props.provider?.proxy.has_auth ? '代理密码（重新配置时必填）' : '代理密码'">
                <ElInput
                  v-model="proxyPassword"
                  data-test="provider-proxy-password"
                  type="password"
                  show-password
                  autocomplete="new-password"
                  spellcheck="false"
                />
              </ElFormItem>
            </div>
            <ElFormItem
              v-if="proxyAuthType === 'headers'"
              label="代理鉴权请求头 JSON"
            >
              <ElInput
                v-model="proxyHeadersText"
                data-test="provider-proxy-headers"
                type="textarea"
                :rows="3"
                spellcheck="false"
                placeholder='例如：{"Proxy-Authorization":"Bearer token"}'
              />
              <p class="form-help">自定义请求头不能与 WebSocket 入口同时使用。</p>
            </ElFormItem>
          </template>
          <p v-else-if="proxyMode === 'direct'" class="form-help">忽略全局代理并直接连接该供应商。</p>
          <p v-else class="form-help">沿用服务端全局 HTTP_PROXY、HTTPS_PROXY 与 NO_PROXY。</p>
        </div>

        <div class="credential-section balance-section">
          <div class="balance-heading">
            <h3 class="credential-section__title">上游余额查询</h3>
            <ElButton
              data-test="detect-balance"
              size="small"
              plain
              :loading="detecting === true"
              :disabled="submitting || !editing"
              :title="editing ? undefined : '保存供应商后即可自动检测接口'"
              @click="emit('detect')"
            >
              <ElIcon><MagicStick /></ElIcon>
              自动检测接口
            </ElButton>
          </div>
          <p v-if="!editing" class="form-help">
            保存供应商后可使用“自动检测接口”识别上游类型。
          </p>
          <p class="form-help">
            除查询密钥与请求头外，字段留空即恢复默认值（基础地址取供应商协议地址，new-api
            除数为 500000、其它为 1，币种为 USD）。
          </p>
          <div class="credential-options">
            <ElFormItem label="上游类型" :error="balanceError" data-validation="balance">
              <select v-model="balanceQueryType" data-test="provider-balance-type">
                <option value="none">不查询余额</option>
                <option value="new_api">new-api / one-api</option>
                <option value="deepseek">DeepSeek 官方</option>
                <option value="openrouter">OpenRouter</option>
                <option value="custom">自定义接口</option>
              </select>
            </ElFormItem>
            <ElFormItem label="自动同步余额">
              <ElSwitch
                v-model="balanceAutoSync"
                data-test="provider-balance-auto-sync"
                :disabled="!balanceConfigured"
              />
            </ElFormItem>
            <ElFormItem
              data-validation="balance-interval"
              label="余额同步间隔（秒）"
              :error="balanceIntervalError"
            >
              <ElInputNumber
                v-model="balanceSyncInterval"
                data-test="provider-balance-interval"
                :min="1"
                :step="60"
                :disabled="!balanceConfigured"
                controls-position="right"
              />
            </ElFormItem>
          </div>

          <div
            v-if="balanceCandidates.length > 1"
            class="balance-candidates"
            data-test="provider-balance-candidates"
          >
            <p class="form-help">检测到多个可用接口，请选择要使用的上游类型：</p>
            <label v-for="candidate in balanceCandidates" :key="candidate.query_type">
              <input
                v-model="balanceQueryType"
                type="radio"
                :value="candidate.query_type"
                :data-test="`balance-candidate-${candidate.query_type}`"
              />
              <span>
                {{ balanceTypeLabels[candidate.query_type] }} · 余额
                {{ candidate.amount }} {{ candidate.currency }}
              </span>
            </label>
          </div>

          <template v-if="balanceConfigured">
            <p v-if="balanceQueryType === 'new_api'" class="form-help">
              new-api / one-api 的 /api/user/self 只接受「访问令牌」，不能用 sk- 中转密钥：
              请把上游控制台「个人设置」生成的访问令牌填入「覆盖查询密钥」；仅当上游校验
              New-Api-User 时才需要填写用户 ID。
            </p>
            <ElFormItem label="余额查询基础地址（可选）">
              <ElInput
                v-model="balanceBaseUrl"
                data-test="provider-balance-base-url"
                spellcheck="false"
                placeholder="留空则使用该供应商的协议基础地址"
              />
            </ElFormItem>
            <div class="credential-options">
              <ElFormItem
                :label="
                  balanceSecretConfigured
                    ? '覆盖查询密钥（留空则保持原值）'
                    : '覆盖查询密钥（可选）'
                "
              >
                <ElInput
                  v-model="balanceApiKey"
                  data-test="provider-balance-api-key"
                  type="password"
                  show-password
                  autocomplete="new-password"
                  spellcheck="false"
                  placeholder="new-api 的 access token 等"
                />
                <ElCheckbox
                  v-if="balanceSecretConfigured"
                  v-model="balanceClearApiKey"
                  data-test="provider-balance-clear-api-key"
                >
                  保存后清除已存的查询密钥
                </ElCheckbox>
              </ElFormItem>
              <ElFormItem v-if="balanceQueryType === 'new_api'" label="new-api 用户 ID">
                <ElInput
                  v-model="balanceUserId"
                  data-test="provider-balance-user-id"
                  spellcheck="false"
                  placeholder="New-Api-User 请求头"
                />
              </ElFormItem>
            </div>

            <template v-if="balanceQueryType === 'custom'">
              <div class="credential-options">
                <ElFormItem label="请求方法">
                  <select v-model="balanceMethod" data-test="provider-balance-method">
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                  </select>
                </ElFormItem>
                <ElFormItem label="请求路径">
                  <ElInput
                    v-model="balancePath"
                    data-test="provider-balance-path"
                    spellcheck="false"
                    placeholder="/api/balance"
                  />
                </ElFormItem>
              </div>
              <ElFormItem label="余额字段路径">
                <ElInput
                  v-model="balanceAmountPath"
                  data-test="provider-balance-amount-path"
                  spellcheck="false"
                  placeholder="data.balance_infos[0].total_balance"
                />
                <p class="form-help">使用点号访问嵌套字段，用 [序号] 访问数组元素。</p>
              </ElFormItem>
              <div class="credential-options">
                <ElFormItem label="已用额度字段路径（可选）">
                  <ElInput
                    v-model="balanceUsedPath"
                    data-test="provider-balance-used-path"
                    spellcheck="false"
                    placeholder="data.used_quota"
                  />
                </ElFormItem>
                <ElFormItem label="可用状态字段路径（可选）">
                  <ElInput
                    v-model="balanceAvailablePath"
                    data-test="provider-balance-available-path"
                    spellcheck="false"
                    placeholder="is_available"
                  />
                </ElFormItem>
              </div>
            </template>

            <div class="credential-options">
              <ElFormItem label="币种（可选）">
                <ElInput
                  v-model="balanceCurrency"
                  data-test="provider-balance-currency"
                  spellcheck="false"
                  placeholder="USD"
                />
              </ElFormItem>
              <ElFormItem label="余额除数（可选）">
                <ElInputNumber
                  v-model="balanceDivisor"
                  data-test="provider-balance-divisor"
                  :min="0.00000001"
                  :step="1"
                  :precision="8"
                  :controls="false"
                />
              </ElFormItem>
            </div>

            <ElFormItem
              data-validation="balance-headers"
              :label="
                balanceHeadersConfigured
                  ? '额外请求头 JSON（留空则保持原值）'
                  : '额外请求头 JSON（可选）'
              "
              :error="balanceHeadersError"
            >
              <ElInput
                v-model="balanceHeadersText"
                data-test="provider-balance-headers"
                type="textarea"
                :rows="3"
                spellcheck="false"
                placeholder='例如：{"X-Tenant":"team-a"}'
              />
              <ElCheckbox
                v-if="balanceHeadersConfigured"
                v-model="balanceClearHeaders"
                data-test="provider-balance-clear-headers"
              >
                保存后清除已存的请求头
              </ElCheckbox>
            </ElFormItem>
          </template>
        </div>

        <div class="switch-row">
          <label>
            <span>启用供应商</span>
            <ElSwitch v-model="enabled" data-test="provider-enabled" />
          </label>
          <label>
            <span>自动同步模型</span>
            <ElSwitch v-model="autoLoadModels" data-test="provider-auto-load" />
          </label>
        </div>

        <section class="protocol-section" aria-labelledby="protocol-heading">
        <div class="protocol-heading-row">
          <div>
            <h3 id="protocol-heading">协议入口</h3>
            <p>同一供应商可以配置多个上游协议与地址。</p>
          </div>
          <ElButton data-test="add-protocol" plain :disabled="submitting" @click="addProtocol">
            <ElIcon><Plus /></ElIcon>
            添加协议
          </ElButton>
        </div>

        <div
          v-for="(row, index) in protocols"
          :key="row.key"
          class="protocol-card"
          :aria-label="`协议 ${String(index + 1)}`"
        >
          <div class="protocol-card__header">
            <strong>协议 {{ index + 1 }}</strong>
            <ElButton
              :data-test="`remove-protocol-${String(index)}`"
              text
              type="danger"
              :disabled="submitting"
              :aria-label="`移除协议 ${String(index + 1)}`"
              @click="removeProtocol(index)"
            >
              <ElIcon><Delete /></ElIcon>
              移除
            </ElButton>
          </div>

          <div class="protocol-grid">
            <ElFormItem label="协议类型">
              <select
                v-model="row.protocol"
                :data-test="`protocol-type-${String(index)}`"
                :disabled="submitting"
              >
                <option value="openai">OpenAI 兼容协议</option>
                <option value="claude">Claude 兼容协议</option>
                <option value="gemini">Gemini 兼容协议</option>
              </select>
            </ElFormItem>
            <ElFormItem label="启用此协议">
              <ElSwitch v-model="row.enabled" :data-test="`protocol-enabled-${String(index)}`" />
            </ElFormItem>
            <ElFormItem v-if="row.protocol === 'openai'" label="原生支持 Responses API">
              <ElSwitch
                v-model="row.supportsResponses"
                :data-test="`protocol-supports-responses-${String(index)}`"
              />
            </ElFormItem>
          </div>

          <ElFormItem
            :data-validation="`protocol-base-${String(index)}`"
            label="HTTP 基础地址"
            :error="row.baseUrlError"
          >
            <ElInput
              v-model="row.baseUrl"
              :data-test="`protocol-base-url-${String(index)}`"
              placeholder="https://api.example.com/v1"
            />
          </ElFormItem>
          <ElFormItem label="WebSocket 地址（可选）">
            <ElInput
              v-model="row.websocketUrl"
              :data-test="`protocol-websocket-url-${String(index)}`"
              placeholder="wss://api.example.com/ws"
            />
          </ElFormItem>
          <ElFormItem
            :data-test="`protocol-extra-field-${String(index)}`"
            :data-validation="`protocol-extra-${String(index)}`"
            :label="row.id === undefined ? '额外请求头 JSON（可选）' : '替换额外请求头 JSON（留空则保持原值）'"
            :error="row.extraHeadersError"
          >
            <ElInput
              v-model="row.extraHeadersText"
              :data-test="`protocol-extra-headers-${String(index)}`"
              type="textarea"
              :rows="3"
              spellcheck="false"
              placeholder='例如：{"X-Tenant":"team-a"}'
            />
          </ElFormItem>
        </div>
        </section>
      </div>
    </ElForm>

    <template #footer>
      <div class="drawer-actions">
        <ElButton data-test="provider-cancel" :disabled="submitting" @click="requestClose">
          取消
        </ElButton>
        <ElButton
          data-test="provider-submit"
          type="primary"
          :loading="submitting"
          :disabled="submitting"
          @click="submitForm"
        >
          保存供应商
        </ElButton>
      </div>
    </template>
  </ElDrawer>
</template>

<style scoped>
.drawer-heading,
.protocol-heading-row h3 {
  margin: 0;
  color: var(--gateway-text);
}

.drawer-heading {
  font-size: 1.25rem;
}

.drawer-description,
.protocol-heading-row p {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  line-height: 1.5;
}

.form-grid,
.protocol-grid,
.credential-options {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(12rem, 0.45fr);
  gap: 1rem;
}

.credential-section {
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.credential-section__title {
  margin: 0 0 1rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--gateway-text);
}

.balance-heading {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.balance-heading .credential-section__title {
  margin-bottom: 0;
}

.balance-candidates {
  display: grid;
  gap: 0.5rem;
  margin: 0.75rem 0;
  padding: 0.75rem;
  background: #fff;
  border: 1px solid var(--gateway-border);
  border-radius: 8px;
}

.balance-candidates label {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.85rem;
}

.switch-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.switch-row label {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  font-weight: 500;
}

.protocol-section {
  padding-top: 1.25rem;
  border-top: 1px solid var(--gateway-border);
}

.protocol-heading-row,
.protocol-card__header,
.drawer-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.protocol-card {
  margin-top: 1rem;
  padding: 1rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.protocol-card__header {
  margin-bottom: 0.75rem;
}

.field-error {
  margin: 0.3rem 0 0;
  color: var(--el-color-danger);
  font-size: 0.75rem;
  line-height: 1.2;
}

.form-help {
  margin: 0.25rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.75rem;
  line-height: 1.4;
}

select {
  width: 100%;
  height: 32px;
  padding: 0 2rem 0 0.7rem;
  color: var(--gateway-text);
  background: #fff;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

select:hover {
  border-color: var(--el-border-color-hover);
}

select:focus {
  border-color: var(--el-color-primary);
  outline: 0;
}

.drawer-actions {
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .form-grid,
  .protocol-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .protocol-heading-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
