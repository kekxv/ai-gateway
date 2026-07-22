<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
  enabled: boolean
  baseUrlError: string
  extraHeadersError: string
}

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
const credentialText = ref('')
const enabled = ref(true)
const autoLoadModels = ref(false)
const syncInterval = ref(3600)
const protocols = ref<ProtocolRow[]>([])
const nameError = ref('')
const credentialError = ref('')
let nextProtocolKey = 1

const editing = computed(() => props.provider !== null)
const drawerTitle = computed(() => (editing.value ? '编辑供应商' : '新建供应商'))

function newProtocolRow(): ProtocolRow {
  return {
    key: nextProtocolKey++,
    protocol: 'openai',
    baseUrl: '',
    websocketUrl: '',
    extraHeadersText: '',
    enabled: true,
    baseUrlError: '',
    extraHeadersError: '',
  }
}

function resetForm(): void {
  const provider = props.provider
  name.value = provider?.name ?? ''
  credentialText.value = ''
  enabled.value = provider?.enabled ?? true
  autoLoadModels.value = provider?.auto_load_models ?? false
  syncInterval.value = provider?.model_sync_interval_seconds ?? 3600
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
          enabled: protocol.enabled,
          baseUrlError: '',
          extraHeadersError: '',
        }))
  nameError.value = ''
  credentialError.value = ''
}

watch(
  () => [props.modelValue, props.provider] as const,
  ([open]) => {
    if (open) resetForm()
  },
  { immediate: true },
)

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseObject(text: string, emptyMessage: string): JsonObject | undefined {
  if (text.trim() === '') {
    credentialError.value = emptyMessage
    return undefined
  }
  try {
    const value: unknown = JSON.parse(text)
    if (!isJsonObject(value)) {
      credentialError.value = '必须是 JSON 对象，不能使用数组或单个值'
      return undefined
    }
    return value
  } catch {
    credentialError.value = 'JSON 格式不正确'
    return undefined
  }
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

function addProtocol(): void {
  protocols.value.push(newProtocolRow())
}

function removeProtocol(index: number): void {
  protocols.value.splice(index, 1)
}

function normalizedProtocol(row: ProtocolRow): ProviderProtocolInput {
  const protocol: ProviderProtocolInput = {
    protocol: row.protocol,
    base_url: row.baseUrl.trim(),
    websocket_url: row.websocketUrl.trim() || null,
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
  nameError.value = ''
  credentialError.value = ''
  if (name.value.trim() === '') nameError.value = '请输入供应商名称'

  const protocolPayload = buildProtocols()
  let credential: JsonObject | undefined
  if (!editing.value || credentialText.value.trim() !== '') {
    credential = parseObject(credentialText.value, '请输入凭据 JSON')
  }
  if (nameError.value !== '' || credentialError.value !== '' || protocolPayload === undefined) {
    return
  }

  if (!editing.value) {
    if (credential === undefined) return
    emit('submit', {
      name: name.value.trim(),
      credential,
      enabled: enabled.value,
      auto_load_models: autoLoadModels.value,
      model_sync_interval_seconds: syncInterval.value,
      protocols: protocolPayload,
    })
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
  if (syncInterval.value !== provider.model_sync_interval_seconds) {
    payload.model_sync_interval_seconds = syncInterval.value
  }
  if (protocolsChanged()) payload.protocols = protocolPayload
  emit('submit', payload)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(94vw, 52rem)"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">{{ drawerTitle }}</h2>
        <p class="drawer-description">配置供应商连接信息与一个或多个协议入口。</p>
      </div>
    </template>

    <ElForm label-position="top" @submit.prevent="submitForm">
      <div class="form-grid">
        <ElFormItem label="供应商名称" :error="nameError">
          <ElInput v-model="name" data-test="provider-name" maxlength="255" />
        </ElFormItem>
        <ElFormItem label="模型同步间隔（秒）">
          <ElInputNumber
            v-model="syncInterval"
            data-test="provider-sync-interval"
            :min="1"
            :step="60"
            controls-position="right"
          />
        </ElFormItem>
      </div>

      <ElFormItem
        :label="editing ? '替换凭据 JSON（留空则保持原值）' : '凭据 JSON'"
        :error="credentialError"
      >
        <ElInput
          v-model="credentialText"
          data-test="provider-credential"
          type="textarea"
          :rows="4"
          spellcheck="false"
          placeholder='例如：{"api_key":"..."}'
        />
        <p v-if="credentialError" data-test="credential-error" class="field-error">
          {{ credentialError }}
        </p>
      </ElFormItem>

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
          <ElButton data-test="add-protocol" plain @click="addProtocol">
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
              :disabled="protocols.length === 1"
              :aria-label="`移除协议 ${String(index + 1)}`"
              @click="removeProtocol(index)"
            >
              <ElIcon><Delete /></ElIcon>
              移除
            </ElButton>
          </div>

          <div class="protocol-grid">
            <ElFormItem label="协议类型">
              <select v-model="row.protocol" :data-test="`protocol-type-${String(index)}`">
                <option value="openai">OpenAI 兼容协议</option>
                <option value="claude">Claude 兼容协议</option>
                <option value="gemini">Gemini 兼容协议</option>
              </select>
            </ElFormItem>
            <ElFormItem label="启用此协议">
              <ElSwitch v-model="row.enabled" :data-test="`protocol-enabled-${String(index)}`" />
            </ElFormItem>
          </div>

          <ElFormItem label="HTTP 基础地址" :error="row.baseUrlError">
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
            <p
              v-if="row.extraHeadersError"
              :data-test="`protocol-extra-error-${String(index)}`"
              class="field-error"
            >
              {{ row.extraHeadersError }}
            </p>
          </ElFormItem>
        </div>
      </section>
    </ElForm>

    <template #footer>
      <div class="drawer-actions">
        <ElButton @click="emit('update:modelValue', false)">取消</ElButton>
        <ElButton
          data-test="provider-submit"
          type="primary"
          :loading="submitting"
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
.protocol-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(12rem, 0.45fr);
  gap: 1rem;
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
