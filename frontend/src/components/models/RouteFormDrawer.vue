<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  ElButton,
  ElDrawer,
  ElForm,
  ElFormItem,
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
  ModelResponse,
  ModelRouteCreate,
  ModelRouteResponse,
  ModelRouteUpdate,
  ProviderResponse,
} from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  model: ModelResponse | null
  route: ModelRouteResponse | null
  providers: ProviderResponse[]
  submitting: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: ModelRouteCreate | ModelRouteUpdate]
}>()

const providerId = ref<number | null>(null)
const upstreamModel = ref('')
const weight = ref<number | null>(100)
const enabled = ref(true)
const providerError = ref('')
const upstreamModelError = ref('')
const weightError = ref('')
const formContent = ref<HTMLElement | null>(null)

const editing = computed(() => props.route !== null)
const drawerTitle = computed(() => (editing.value ? '编辑模型路由' : '新建模型路由'))
const selectedProvider = computed(
  () => props.providers.find((provider) => provider.id === providerId.value) ?? null,
)

function resetErrors(): void {
  providerError.value = ''
  upstreamModelError.value = ''
  weightError.value = ''
}

function clearDraft(): void {
  providerId.value = null
  upstreamModel.value = ''
  weight.value = 100
  enabled.value = true
  resetErrors()
}

function resetForm(): void {
  const route = props.route
  providerId.value = route?.provider_id ?? props.providers[0]?.id ?? null
  upstreamModel.value = route?.upstream_model ?? ''
  weight.value = route?.weight ?? 100
  enabled.value = route?.enabled ?? true
  resetErrors()
}

watch(
  () => [props.modelValue, props.route?.id, props.model?.id] as const,
  ([open]) => {
    if (props.submitting) return
    if (open) resetForm()
    else clearDraft()
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(() => {
  if (!props.submitting) clearDraft()
})

function requestClose(): void {
  if (props.submitting) return
  clearDraft()
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value) {
    if (props.submitting) return
    clearDraft()
  }
  emit('update:modelValue', value)
}

function handleBeforeClose(done: () => void): void {
  if (props.submitting) return
  clearDraft()
  done()
}

async function focusInvalidField(selector: string): Promise<void> {
  await nextTick()
  const target = formContent.value?.querySelector<HTMLElement>(selector)
  if (target === undefined || target === null) return
  if (typeof target.scrollIntoView === 'function') target.scrollIntoView({ block: 'center' })
  target.focus()
}

function submitForm(): void {
  if (props.submitting) return
  resetErrors()
  const model = props.model
  if (providerId.value === null || selectedProvider.value === null) {
    providerError.value = '请选择供应商'
  }
  if (upstreamModel.value.trim() === '') {
    upstreamModelError.value = '请输入提供商原始模型名'
  }
  if (typeof weight.value !== 'number' || !Number.isInteger(weight.value) || weight.value < 1 || weight.value > 10000) {
    weightError.value = '请输入 1 到 10000 的整数'
  }

  let invalidSelector: string | null = null
  if (providerError.value !== '') invalidSelector = '[data-validation="route-provider"] select'
  else if (upstreamModelError.value !== '') {
    invalidSelector = '[data-validation="route-upstream-model"] input'
  } else if (weightError.value !== '') invalidSelector = '[data-validation="route-weight"] input'
  if (invalidSelector !== null) {
    void focusInvalidField(invalidSelector)
    return
  }
  if (
    model === null ||
    providerId.value === null ||
    weight.value === null
  ) {
    return
  }

  const upstream = upstreamModel.value.trim()
  if (!editing.value) {
    emit('submit', {
      model_id: model.id,
      provider_id: providerId.value,
      upstream_model: upstream,
      weight: weight.value,
      enabled: enabled.value,
    })
    return
  }

  const route = props.route
  if (route === null) return
  const payload: ModelRouteUpdate = {}
  if (providerId.value !== route.provider_id) payload.provider_id = providerId.value
  if (upstream !== route.upstream_model) payload.upstream_model = upstream
  if (weight.value !== route.weight) payload.weight = weight.value
  if (enabled.value !== route.enabled) payload.enabled = enabled.value
  emit('submit', payload)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(94vw, 42rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleBeforeClose"
    destroy-on-close
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">{{ drawerTitle }}</h2>
        <p class="drawer-description">
          为“{{ model?.display_name ?? '未选择模型' }}”配置上游供应商与权重。
        </p>
      </div>
    </template>

    <ElForm :disabled="submitting" label-position="top" @submit.prevent="submitForm">
      <div ref="formContent">
        <ElFormItem
          data-validation="route-provider"
          label="供应商"
          :error="providerError"
        >
          <select
            v-model.number="providerId"
            data-test="route-provider"
            aria-label="供应商"
            :disabled="submitting"
          >
            <option v-for="provider in providers" :key="provider.id" :value="provider.id">
              {{ provider.name }}
            </option>
          </select>
          <p class="field-help">转发时优先使用与客户端一致的供应商协议。</p>
        </ElFormItem>

        <ElFormItem
          data-validation="route-upstream-model"
          label="提供商原始模型名"
          :error="upstreamModelError"
        >
          <ElInput
            v-model="upstreamModel"
            data-test="route-upstream-model"
            maxlength="255"
            placeholder="例如：gpt-4.1-2026-04-14"
          />
          <p class="field-help">别名在转发前会转换为这里填写的模型名。</p>
        </ElFormItem>

        <div class="form-grid">
          <ElFormItem
            data-validation="route-weight"
            label="路由权重"
            :error="weightError"
          >
            <ElInputNumber
              v-model="weight"
              data-test="route-weight"
              :min="1"
              :max="10000"
              :step="1"
              controls-position="right"
            />
          </ElFormItem>
          <ElFormItem label="启用路由">
            <div class="switch-field">
              <ElSwitch v-model="enabled" data-test="route-enabled" />
              <span>{{ enabled ? '参与路由' : '暂停路由' }}</span>
            </div>
          </ElFormItem>
        </div>
      </div>
    </ElForm>

    <template #footer>
      <div class="drawer-actions">
        <ElButton data-test="route-cancel" :disabled="submitting" @click="requestClose">
          取消
        </ElButton>
        <ElButton
          data-test="route-submit"
          type="primary"
          :loading="submitting"
          :disabled="submitting"
          @click="submitForm"
        >
          保存路由
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

.drawer-description,
.field-help {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  line-height: 1.5;
}

.field-help {
  width: 100%;
  font-size: 0.82rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
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

.switch-field,
.drawer-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.switch-field {
  min-height: 32px;
}

.drawer-actions {
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
