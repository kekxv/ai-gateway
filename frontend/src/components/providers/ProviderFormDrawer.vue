<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import {
  ElButton,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElSwitch,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-input-number.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-switch.css'

import type {
  JsonObject,
  Protocol,
  ProviderCreate,
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

const props = defineProps<{
  modelValue: boolean
  provider: ProviderResponse | null
  submitting: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: ProviderCreate | ProviderUpdate]
}>()

const name = ref('')
const apiKey = ref('')
const advancedCredentialText = ref('')
const authScheme = ref<AuthScheme>('protocol-default')
const authHeader = ref<AuthHeader>('protocol-default')
const customAuthHeader = ref('')
const enabled = ref(true)
const autoLoadModels = ref(false)
const syncInterval = ref<number | null>(3600)
const priceMultiplier = ref(1.0)
const protocols = ref<ProtocolRow[]>([])
const nameError = ref('')
const advancedCredentialError = ref('')
const authHeaderError = ref('')
const syncIntervalError = ref('')
const formContent = ref<HTMLElement | null>(null)
let nextProtocolKey = 1

const editing = computed(() => props.provider !== null)
const drawerTitle = computed(() => (editing.value ? '编辑供应商' : '新建供应商'))
const showCustomHeaderInput = computed(
  () => authScheme.value !== 'none' && authHeader.value === 'custom',
)

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
  enabled.value = provider?.enabled ?? true
  autoLoadModels.value = provider?.auto_load_models ?? false
  syncInterval.value = provider?.model_sync_interval_seconds ?? 3600
  priceMultiplier.value = provider?.price_multiplier ?? 1.0
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
  syncIntervalError.value = ''
}

function clearSensitiveState(): void {
  apiKey.value = ''
  advancedCredentialText.value = ''
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
  syncIntervalError.value = ''
  if (name.value.trim() === '') nameError.value = '请输入供应商名称'
  const interval = syncInterval.value
  if (typeof interval !== 'number' || !Number.isInteger(interval) || interval < 1) {
    syncIntervalError.value = '请输入大于等于 1 的整数'
  }

  const protocolPayload = buildProtocols()
  const credential = buildCredential()
  if (
    nameError.value !== '' ||
    advancedCredentialError.value !== '' ||
    authHeaderError.value !== '' ||
    syncIntervalError.value !== '' ||
    protocolPayload === undefined
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
      advancedCredentialError.value === ''
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

  if (!editing.value) {
    const payload: ProviderCreate = {
      name: name.value.trim(),
      enabled: enabled.value,
      auto_load_models: autoLoadModels.value,
      model_sync_interval_seconds: interval,
      protocols: protocolPayload,
      price_multiplier: priceMultiplier.value,
    }
    if (credential !== undefined) payload.credential = credential
    emit('submit', payload)
    return
  }

  const provider = props.provider
  if (provider === null) return
  const payload: ProviderUpdate = {}
  if (name.value.trim() !== provider.name) payload.name = name.value.trim()
  if (credential !== undefined) payload.credential = credential
  if (enabled.value !== provider.enabled) payload.enabled = enabled.value
  if (autoLoadModels.value !== provider.auto_load_models) {
    payload.auto_load_models = autoLoadModels.value
  }
  if (interval !== provider.model_sync_interval_seconds) {
    payload.model_sync_interval_seconds = interval
  }
  if (protocolsChanged()) payload.protocols = protocolPayload
  if (priceMultiplier.value !== provider.price_multiplier) {
    payload.price_multiplier = priceMultiplier.value
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
            data-test="price-multiplier-field"
            data-validation="price-multiplier"
            label="价格倍率"
          >
            <ElInputNumber
              v-model="priceMultiplier"
              data-test="provider-price-multiplier"
              :min="0.10"
              :max="10.00"
              :step="0.1"
              :precision="2"
              controls-position="right"
            />
            <div class="form-help">
              应用于该供应商所有模型的价格倍率（0.10 ~ 10.00）
            </div>
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
