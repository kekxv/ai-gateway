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

const ownerId = ref('')
const name = ref('')
const scope = ref<ApiKeyScope>('all')
const isActive = ref(true)
const expiry = ref('')
const providerIds = ref<number[]>([])
const modelIds = ref<number[]>([])
const ownerError = ref('')
const nameError = ref('')
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
  ownerId.value = ''
  name.value = ''
  scope.value = 'all'
  isActive.value = true
  expiry.value = ''
  providerIds.value = []
  modelIds.value = []
  clearErrors()
}

function clearErrors(): void {
  ownerError.value = ''
  nameError.value = ''
  providerError.value = ''
  modelError.value = ''
  expiryError.value = ''
}

function resetForm(): void {
  const apiKey = props.apiKey
  ownerId.value = apiKey === null ? '' : String(apiKey.user_id)
  name.value = apiKey?.name ?? ''
  scope.value = apiKey?.scope ?? 'all'
  isActive.value = apiKey?.is_active ?? true
  expiry.value = localDateTime(apiKey?.expires_at ?? null)
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

function updateProviderIds(event: Event): void {
  providerIds.value = selectedIds(event)
}

function updateModelIds(event: Event): void {
  modelIds.value = selectedIds(event)
}

function selectedIds(event: Event): number[] {
  const target = event.target
  if (!(target instanceof HTMLSelectElement)) return []
  return Array.from(target.selectedOptions, (option) => Number(option.value))
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
  if (!editing.value && !props.users.some((user) => user.id === Number(ownerId.value))) {
    ownerError.value = '请选择密钥所有者'
  }
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
    emit('submit', {
      user_id: Number(ownerId.value),
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
  if (!sameExpiry(expiresAt, apiKey.expires_at)) payload.expires_at = expiresAt
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
      <ElFormItem label="所有者" :error="ownerError">
        <select
          v-model="ownerId"
          data-test="api-key-owner"
          class="field-select"
          :disabled="editing || submitting"
        >
          <option value="" disabled>请选择用户</option>
          <option v-for="user in users" :key="user.id" :value="String(user.id)">
            {{ user.email }}
          </option>
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

      <ElFormItem v-if="needsProviders" label="至少选择一个供应商" :error="providerError">
        <select
          data-test="provider-ids"
          class="field-select multi-select"
          multiple
          :value="providerIds.map(String)"
          :disabled="submitting"
          @change="updateProviderIds"
        >
          <option v-for="provider in providers" :key="provider.id" :value="String(provider.id)">
            {{ provider.name }}
          </option>
        </select>
      </ElFormItem>

      <ElFormItem v-if="needsModels" label="至少选择一个模型" :error="modelError">
        <select
          data-test="model-ids"
          class="field-select multi-select"
          multiple
          :value="modelIds.map(String)"
          :disabled="submitting"
          @change="updateModelIds"
        >
          <option v-for="model in models" :key="model.id" :value="String(model.id)">
            {{ model.display_name }}（{{ model.canonical_name }}）
          </option>
        </select>
      </ElFormItem>

      <ElFormItem label="过期时间（可选）" :error="expiryError">
        <input
          v-model="expiry"
          data-test="api-key-expiry"
          class="field-input"
          type="datetime-local"
          :disabled="submitting"
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

.multi-select {
  min-height: 7rem;
  padding: 0.4rem;
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
</style>
