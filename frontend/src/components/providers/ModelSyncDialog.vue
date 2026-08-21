<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ElButton,
  ElCheckbox,
  ElDialog,
  ElEmpty,
  ElInput,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-checkbox.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'

import { discoverProviderModels } from '@/api/providers'

const props = defineProps<{
  modelValue: boolean
  providerId: number | null
  providerName: string
  submitting: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [models: string[]]
}>()

const loading = ref(false)
const error = ref('')
const modelsByProtocol = ref<Record<string, string[]>>({})
const selectedModels = ref<Set<string>>(new Set())
const filterQuery = ref('')
let discoverController: AbortController | undefined

const allModels = computed(() => {
  const all: string[] = []
  for (const models of Object.values(modelsByProtocol.value)) {
    all.push(...models)
  }
  return [...new Set(all)].sort()
})

const totalModels = computed(() => allModels.value.length)
const visibleModelsByProtocol = computed(() => {
  const query = filterQuery.value.trim().toLocaleLowerCase('en-US')
  if (query === '') return modelsByProtocol.value
  return Object.entries(modelsByProtocol.value).reduce<Record<string, string[]>>(
    (visible, [protocol, models]) => {
      const matchingModels = models.filter((model) =>
        model.toLocaleLowerCase('en-US').includes(query),
      )
      if (matchingModels.length > 0) visible[protocol] = matchingModels
      return visible
    },
    {},
  )
})
const busy = computed(() => loading.value || props.submitting)
const selectedCount = computed(() => selectedModels.value.size)
const allSelected = computed(
  () => totalModels.value > 0 && selectedModels.value.size === totalModels.value,
)
const someSelected = computed(
  () => selectedModels.value.size > 0 && selectedModels.value.size < totalModels.value,
)

async function loadModels(): Promise<void> {
  if (props.providerId === null) return
  loading.value = true
  error.value = ''
  filterQuery.value = ''
  modelsByProtocol.value = {}
  selectedModels.value = new Set()

  discoverController?.abort()
  const controller = new AbortController()
  discoverController = controller

  try {
    const result = await discoverProviderModels(props.providerId, controller.signal)
    if (controller.signal.aborted) return
    modelsByProtocol.value = result
    // Select all by default
    const all = new Set<string>()
    for (const models of Object.values(result)) {
      for (const model of models) all.add(model)
    }
    selectedModels.value = all
  } catch (err: unknown) {
    if (controller.signal.aborted) return
    error.value = err instanceof Error ? err.message : '模型发现失败'
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

function toggleModel(model: string): void {
  const next = new Set(selectedModels.value)
  if (next.has(model)) {
    next.delete(model)
  } else {
    next.add(model)
  }
  selectedModels.value = next
}

function toggleAll(): void {
  if (allSelected.value) {
    selectedModels.value = new Set()
  } else {
    selectedModels.value = new Set(allModels.value)
  }
}

function handleConfirm(): void {
  if (busy.value) return
  emit('confirm', [...selectedModels.value])
}

function requestClose(): void {
  if (busy.value) return
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value && busy.value) return
  emit('update:modelValue', value)
}

watch(
  () => [props.modelValue, props.providerId] as const,
  ([open]) => {
    if (open) void loadModels()
    else {
      discoverController?.abort()
      discoverController = undefined
    }
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(() => {
  discoverController?.abort()
})
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="`选择同步的模型 — ${providerName}`"
    width="min(90vw, 40rem)"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    destroy-on-close
    @update:model-value="handleModelValueUpdate"
  >
    <div v-if="loading" class="dialog-loading" aria-label="正在发现模型">
      <ElSkeleton v-for="index in 5" :key="index" animated>
        <template #template>
          <ElSkeletonItem variant="rect" class="skeleton-item" />
        </template>
      </ElSkeleton>
    </div>

    <ElResult v-else-if="error" icon="error" title="模型发现失败" :sub-title="error" />

    <ElEmpty v-else-if="allModels.length === 0" description="没有发现可用的模型" />

    <div v-else class="model-list-container">
      <div class="model-list-toolbar">
        <ElInput
          v-model="filterQuery"
          data-test="model-sync-filter"
          clearable
          placeholder="筛选模型名称"
          :disabled="submitting"
          aria-label="筛选模型名称"
        />
        <ElCheckbox
          :model-value="allSelected"
          :indeterminate="someSelected"
          :disabled="submitting"
          @change="toggleAll"
        >
          全选 ({{ selectedCount }}/{{ totalModels }})
        </ElCheckbox>
      </div>

      <div
        v-for="(models, protocol) in visibleModelsByProtocol"
        :key="protocol"
        class="protocol-group"
      >
        <h4 class="protocol-group__title">{{ protocol }}</h4>
        <div class="model-checkboxes">
          <ElCheckbox
            v-for="model in models"
            :key="model"
            :model-value="selectedModels.has(model)"
            :disabled="submitting"
            @change="toggleModel(model)"
          >
            <code>{{ model }}</code>
          </ElCheckbox>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-actions">
        <ElButton :disabled="busy" @click="requestClose">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="submitting"
          :disabled="busy || selectedCount === 0 || error !== ''"
          @click="handleConfirm"
        >
          同步选中的模型 ({{ selectedCount }})
        </ElButton>
      </div>
    </template>
  </ElDialog>
</template>

<style scoped>
.dialog-loading {
  display: grid;
  gap: 0.5rem;
  padding: 1rem 0;
}

.skeleton-item {
  height: 2rem;
}

.model-list-container {
  max-height: 60vh;
  overflow-y: auto;
}

.model-list-toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: grid;
  gap: 0.75rem;
  padding: 0.75rem 0.5rem;
  background: var(--gateway-panel);
  border-bottom: 1px solid var(--gateway-border);
  margin-bottom: 1rem;
  box-shadow: 0 2px 4px rgb(0 0 0 / 0.05);
}

.protocol-group {
  margin-bottom: 1.25rem;
}

.protocol-group__title {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--gateway-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.model-checkboxes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 0.25rem;
}

.model-checkboxes code {
  font-size: 0.85rem;
  color: var(--gateway-text);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
