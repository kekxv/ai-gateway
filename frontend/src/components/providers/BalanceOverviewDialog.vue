<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElEmpty,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/el-tag.css'

import { syncAllProviderBalances } from '@/api/providers'
import type { ProviderBalanceBatchEntry, BalanceQueryType } from '@/api/types'
import { formatBalanceAmount } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  refreshed: []
}>()

const loading = ref(false)
const error = ref('')
const entries = ref<ProviderBalanceBatchEntry[]>([])
const skipped = ref(0)
let requestController: AbortController | undefined

const balanceTypeLabels: Readonly<Record<BalanceQueryType, string>> = {
  new_api: 'new-api / one-api',
  deepseek: 'DeepSeek 官方',
  openrouter: 'OpenRouter',
  custom: '自定义接口',
}

function typeLabel(queryType: BalanceQueryType): string {
  return balanceTypeLabels[queryType]
}

const syncedCount = computed(() => entries.value.filter((entry) => entry.status === 'synced').length)
const failedCount = computed(() => entries.value.length - syncedCount.value)
const summary = computed(() => {
  const parts = [`成功 ${String(syncedCount.value)}`, `失败 ${String(failedCount.value)}`]
  if (skipped.value > 0) parts.push(`未配置 ${String(skipped.value)}`)
  return parts.join(' · ')
})

function formatTime(value: string | null): string {
  if (value === null) return '—'
  const parsed = new Date(value.endsWith('Z') ? value : `${value}Z`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN')
}

async function loadBalances(): Promise<void> {
  loading.value = true
  error.value = ''
  entries.value = []
  skipped.value = 0

  requestController?.abort()
  const controller = new AbortController()
  requestController = controller

  try {
    const result = await syncAllProviderBalances(controller.signal)
    if (controller.signal.aborted) return
    entries.value = result.results
    skipped.value = result.skipped
    emit('refreshed')
  } catch (err: unknown) {
    if (controller.signal.aborted) return
    error.value = err instanceof Error ? err.message : '批量查询余额失败'
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

function requestClose(): void {
  if (loading.value) return
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value && loading.value) return
  emit('update:modelValue', value)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void loadBalances()
    else {
      requestController?.abort()
      requestController = undefined
    }
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(() => {
  requestController?.abort()
})
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    title="上游余额批量查询"
    width="min(94vw, 60rem)"
    :close-on-click-modal="!loading"
    :close-on-press-escape="!loading"
    :show-close="!loading"
    destroy-on-close
    @update:model-value="handleModelValueUpdate"
  >
    <div v-if="loading" class="dialog-loading" aria-label="正在查询上游余额">
      <ElSkeleton v-for="index in 4" :key="index" animated>
        <template #template>
          <ElSkeletonItem variant="rect" class="skeleton-item" />
        </template>
      </ElSkeleton>
    </div>

    <ElResult v-else-if="error" icon="error" title="批量查询余额失败" :sub-title="error" />

    <ElEmpty v-else-if="entries.length === 0" description="没有已配置余额查询的供应商" />

    <template v-else>
      <ElAlert
        data-test="balance-batch-summary"
        class="batch-summary"
        :type="failedCount === 0 ? 'success' : 'warning'"
        :title="summary"
        :description="`共查询 ${String(entries.length)} 个已配置余额查询的供应商`"
        show-icon
      />
      <ElTable
        :data="entries"
        data-test="balance-batch-table"
        stripe
        max-height="26rem"
        style="width: 100%"
      >
        <ElTableColumn label="供应商" min-width="180">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <ElTag v-if="!row.enabled" size="small" type="info" class="provider-state">已停用</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="上游类型" min-width="150">
          <template #default="{ row }">{{ typeLabel(row.query_type) }}</template>
        </ElTableColumn>
        <ElTableColumn label="结果" width="90">
          <template #default="{ row }">
            <ElTag :type="row.status === 'synced' ? 'success' : 'danger'" size="small">
              {{ row.status === 'synced' ? '成功' : '失败' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="余额" min-width="130">
          <template #default="{ row }">
            {{ formatBalanceAmount(row.amount, row.currency) }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="已用" min-width="120">
          <template #default="{ row }">
            {{ formatBalanceAmount(row.used, row.currency) }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="同步时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.synced_at) }}</template>
        </ElTableColumn>
        <ElTableColumn label="失败原因" min-width="220">
          <template #default="{ row }">
            <span v-if="row.error === null">—</span>
            <code v-else class="batch-error">{{ row.error }}</code>
          </template>
        </ElTableColumn>
      </ElTable>
    </template>

    <template #footer>
      <div class="dialog-actions">
        <ElButton :disabled="loading" data-test="balance-batch-close" @click="requestClose">
          关闭
        </ElButton>
        <ElButton
          type="primary"
          :loading="loading"
          data-test="balance-batch-refresh"
          @click="loadBalances"
        >
          重新查询
        </ElButton>
      </div>
    </template>
  </ElDialog>
</template>

<style scoped>
.dialog-loading {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.skeleton-item {
  height: 2.2rem;
  border-radius: 0.4rem;
}

.batch-summary {
  margin-bottom: 0.75rem;
}

.provider-state {
  margin-left: 0.4rem;
}

.batch-error {
  color: var(--el-color-danger);
  white-space: pre-wrap;
  word-break: break-word;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
