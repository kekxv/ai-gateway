<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ElButton,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElInput,
  ElSwitch,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-switch.css'

import type {
  ApiKeyCreate,
  ApiKeyResponse,
  ApiKeyScope,
  ApiKeyUpdate,
  ModelResponse,
  ProviderResponse,
  UserResponse,
} from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  apiKey: ApiKeyResponse | null
  users: UserResponse[]
  providers: ProviderResponse[]
  models: ModelResponse[]
  submitting: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: ApiKeyCreate | ApiKeyUpdate]
}>()

const ownerId = ref<number | null>(null)
const name = ref('')
const scope = ref<ApiKeyScope>('all')
const isActive = ref(true)
const expiry = ref('')
const expiryDirty = ref(false)
const providerIds = ref<number[]>([])
const modelIds = ref<number[]>([])
const nameError = ref('')
const ownerError = ref('')
const providerError = ref('')
const modelError = ref('')
const expiryError = ref('')

const editing = computed(() => props.apiKey !== null)
const title = computed(() => (editing.value ? '编辑接口密钥' : '新建接口密钥'))
const needsProviders = computed(
  () => scope.value === 'providers' || scope.value === 'providers_and_models',
)
const needsModels = computed(
  () => scope.value === 'models' || scope.value === 'providers_and_models',
)

function localDateTime(iso: string | null): string {
  if (iso === null) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

function clearDraft(): void {
  ownerId.value = null
  name.value = ''
  scope.value = 'all'
  isActive.value = true
  expiry.value = ''
  expiryDirty.value = false
  providerIds.value = []
  modelIds.value = []
  clearErrors()
}

function clearErrors(): void {
  nameError.value = ''
  ownerError.value = ''
  providerError.value = ''
  modelError.value = ''
  expiryError.value = ''
}

function resetForm(): void {
  const apiKey = props.apiKey
  ownerId.value = apiKey?.user_id ?? null
  name.value = apiKey?.name ?? ''
  scope.value = apiKey?.scope ?? 'all'
  isActive.value = apiKey?.is_active ?? true
  expiry.value = localDateTime(apiKey?.expires_at ?? null)
  expiryDirty.value = false
  providerIds.value = [...(apiKey?.provider_ids ?? [])]
  modelIds.value = [...(apiKey?.model_ids ?? [])]
  normalizeSelections()
  clearErrors()
}

function normalizeSelections(): void {
  if (!needsProviders.value) providerIds.value = []
  if (!needsModels.value) modelIds.value = []
}

watch(scope, () => {
  normalizeSelections()
  providerError.value = ''
  modelError.value = ''
})

watch(
  () => [props.modelValue, props.apiKey] as const,
  ([open]) => {
    if (open) resetForm()
    else clearDraft()
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(clearDraft)

function requestClose(): void {
  if (props.submitting) return
  clearDraft()
  emit('update:modelValue', false)
}

function handleBeforeClose(done: () => void): void {
  if (props.submitting) return
  clearDraft()
  done()
}

function handleModelValueUpdate(value: boolean): void {
  if (!value && props.submitting) return
  if (!value) clearDraft()
  emit('update:modelValue', value)
}

function toggleProvider(id: number): void {
  const index = providerIds.value.indexOf(id)
  if (index === -1) {
    providerIds.value.push(id)
  } else {
    providerIds.value.splice(index, 1)
  }
}

function toggleModel(id: number): void {
  const index = modelIds.value.indexOf(id)
  if (index === -1) {
    modelIds.value.push(id)
  } else {
    modelIds.value.splice(index, 1)
  }
}

function normalizedExpiry(): string | null | undefined {
  if (expiry.value === '') return null
  const date = new Date(expiry.value)
  if (Number.isNaN(date.getTime())) return undefined
  return date.toISOString()
}

function sameExpiry(left: string | null, right: string | null): boolean {
  if (left === null || right === null) return left === right
  const leftTime = new Date(left).getTime()
  const rightTime = new Date(right).getTime()
  if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) return left === right
  return leftTime === rightTime
}

function validate(): string | null {
  clearErrors()
  if (!editing.value && ownerId.value === null) ownerError.value = '请选择密钥所有者'
  if (name.value.trim() === '') nameError.value = '请输入密钥名称'
  if (needsProviders.value && providerIds.value.length === 0) {
    providerError.value = '至少选择一个供应商'
  }
  if (needsModels.value && modelIds.value.length === 0) {
    modelError.value = '至少选择一个模型'
  }
  const expiresAt = normalizedExpiry()
  if (expiresAt === undefined) expiryError.value = '请输入有效的过期时间'
  return expiresAt ?? null
}

function submitForm(): void {
  if (props.submitting) return
  const expiresAt = validate()
  if (
    ownerError.value !== '' ||
    nameError.value !== '' ||
    providerError.value !== '' ||
    modelError.value !== '' ||
    expiryError.value !== ''
  ) return

  const normalizedProviders = needsProviders.value ? [...providerIds.value] : []
  const normalizedModels = needsModels.value ? [...modelIds.value] : []
  const apiKey = props.apiKey
  if (apiKey === null) {
    if (ownerId.value === null) return
    emit('submit', {
      user_id: ownerId.value,
      name: name.value.trim(),
      scope: scope.value,
      is_active: isActive.value,
      expires_at: expiresAt,
      provider_ids: normalizedProviders,
      model_ids: normalizedModels,
    })
    return
  }

  const payload: ApiKeyUpdate = {}
  if (name.value.trim() !== apiKey.name) payload.name = name.value.trim()
  if (scope.value !== apiKey.scope) payload.scope = scope.value
  if (isActive.value !== apiKey.is_active) payload.is_active = isActive.value
  if (expiryDirty.value && !sameExpiry(expiresAt, apiKey.expires_at)) {
    payload.expires_at = expiresAt
  }
  if (
    scope.value !== apiKey.scope ||
    normalizedProviders.join(',') !== apiKey.provider_ids.join(',')
  ) {
    payload.provider_ids = normalizedProviders
  }
  if (
    scope.value !== apiKey.scope ||
    normalizedModels.join(',') !== apiKey.model_ids.join(',')
  ) {
    payload.model_ids = normalizedModels
  }
  emit('submit', payload)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(94vw, 34rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleBeforeClose"
    destroy-on-close
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">{{ title }}</h2>
        <p class="drawer-description">作用域决定此密钥可以访问的供应商与模型。</p>
      </div>
    </template>

    <ElForm :disabled="submitting" label-position="top" @submit.prevent="submitForm">
      <ElFormItem label="所有者" for="api-key-owner" :error="ownerError" required>
        <select
          id="api-key-owner"
          v-model="ownerId"
          data-test="api-key-owner"
          class="field-select"
          :disabled="submitting || editing"
        >
          <option :value="null" disabled>请选择用户</option>
          <option v-for="user in users" :key="user.id" :value="user.id">{{ user.email }}</option>
        </select>
      </ElFormItem>

      <ElFormItem label="名称" :error="nameError">
        <ElInput v-model="name" data-test="api-key-name" maxlength="255" autocomplete="off" />
      </ElFormItem>

      <ElFormItem label="作用域">
        <select v-model="scope" data-test="api-key-scope" class="field-select" :disabled="submitting">
          <option value="all">全部供应商与模型</option>
          <option value="providers">指定供应商</option>
          <option value="models">指定模型</option>
          <option value="providers_and_models">指定供应商和模型</option>
        </select>
      </ElFormItem>

      <ElFormItem v-if="needsProviders" label="选择供应商" :error="providerError">
        <div class="checkbox-list">
          <label v-for="provider in providers" :key="provider.id" class="checkbox-item">
            <input
              type="checkbox"
              :value="provider.id"
              :checked="providerIds.includes(provider.id)"
              :data-test="`api-key-provider-${String(provider.id)}`"
              :disabled="submitting"
              @change="toggleProvider(provider.id)"
            />
            <span>{{ provider.name }}</span>
          </label>
          <p v-if="providers.length === 0" class="empty-hint">暂无可用供应商</p>
        </div>
      </ElFormItem>

      <ElFormItem v-if="needsModels" label="选择模型" :error="modelError">
        <div class="checkbox-list">
          <label v-for="model in models" :key="model.id" class="checkbox-item">
            <input
              type="checkbox"
              :value="model.id"
              :checked="modelIds.includes(model.id)"
              :data-test="`api-key-model-${String(model.id)}`"
              :disabled="submitting"
              @change="toggleModel(model.id)"
            />
            <span>{{ model.display_name }}（{{ model.canonical_name }}）</span>
          </label>
          <p v-if="models.length === 0" class="empty-hint">暂无可用模型</p>
        </div>
      </ElFormItem>

      <ElFormItem label="过期时间（可选）" :error="expiryError">
        <input
          v-model="expiry"
          data-test="api-key-expiry"
          class="field-input"
          type="datetime-local"
          :disabled="submitting"
          @input="expiryDirty = true"
        />
      </ElFormItem>

      <ElFormItem label="密钥状态">
        <ElSwitch v-model="isActive" active-text="启用" inactive-text="停用" />
      </ElFormItem>
    </ElForm>

    <template #footer>
      <div class="drawer-actions">
        <ElButton :disabled="submitting" @click="requestClose">取消</ElButton>
        <ElButton
          data-test="api-key-submit"
          type="primary"
          :loading="submitting"
          @click="submitForm"
        >
          {{ editing ? '保存修改' : '创建密钥' }}
        </ElButton>
      </div>
    </template>
  </ElDrawer>
</template>

<style scoped>
.drawer-heading {
  margin: 0;
  color: var(--gateway-text);
  font-size: 1.25rem;
}

.drawer-description {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.field-select,
.field-input {
  box-sizing: border-box;
  width: 100%;
  min-height: 2.5rem;
  padding: 0 0.75rem;
  color: var(--gateway-text);
  background: #fff;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.field-select:focus,
.field-input:focus {
  border-color: var(--el-color-primary);
  outline: 0;
}

.field-select:disabled,
.field-input:disabled {
  cursor: not-allowed;
  background: var(--el-disabled-bg-color);
}

.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 12rem;
  padding: 0.75rem;
  overflow-y: auto;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 8px;
}

.checkbox-item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  cursor: pointer;
  padding: 0.25rem 0;
}

.checkbox-item input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
}

.checkbox-item span {
  font-size: 0.9rem;
  color: var(--gateway-text);
}

.empty-hint {
  margin: 0;
  color: var(--gateway-muted);
  font-size: 0.85rem;
  text-align: center;
  padding: 0.5rem;
}
</style>
