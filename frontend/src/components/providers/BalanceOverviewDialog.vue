<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
  ElTable,
  ElTableColumn,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-table.css'

import { syncAllProviderBalances } from '@/api/providers'
import type { BalanceQueryType, ProviderBalanceBatchEntry } from '@/api/types'
import { formatBalanceAmount, formatDateTimeShort } from '@/utils/format'

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
const stats = computed(() => [
  { key: 'synced', label: '成功', value: syncedCount.value, tone: 'ok' },
  { key: 'failed', label: '失败', value: failedCount.value, tone: 'fail' },
  { key: 'skipped', label: '未配置', value: skipped.value, tone: 'idle' },
])
const subtitle = computed(() => {
  if (loading.value) return '正在查询上游余额…'
  if (error.value !== '') return '查询未完成'
  if (entries.value.length === 0) return '没有供应商配置余额查询'
  return `已查询 ${String(entries.value.length)} 个供应商`
})

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
    width="min(94vw, 56rem)"
    :close-on-click-modal="!loading"
    :close-on-press-escape="!loading"
    :show-close="!loading"
    destroy-on-close
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div class="dialog-heading">
        <h3>上游余额批量查询</h3>
        <p>{{ subtitle }}</p>
      </div>
    </template>

    <div class="balance-body">
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
        <div class="stats" data-test="balance-batch-summary">
          <span v-for="stat in stats" :key="stat.key" class="stat">
            <i class="stat__dot" :class="`stat__dot--${stat.tone}`" aria-hidden="true"></i>
            {{ stat.label }}
            <strong>{{ stat.value }}</strong>
          </span>
        </div>

        <ElTable
          :data="entries"
          data-test="balance-batch-table"
          class="balance-table"
          max-height="24rem"
          style="width: 100%"
        >
          <ElTableColumn label="供应商" min-width="180">
            <template #default="{ row }">
              <div class="provider">
                <span class="provider__name">{{ row.name }}</span>
                <span v-if="!row.enabled" class="chip">已停用</span>
              </div>
              <span class="provider__type">{{ typeLabel(row.query_type) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="92">
            <template #default="{ row }">
              <span class="status" :class="`status--${row.status === 'synced' ? 'ok' : 'fail'}`">
                <i class="status__dot" aria-hidden="true"></i>
                {{ row.status === 'synced' ? '成功' : '失败' }}
              </span>
              <span v-if="row.is_available === false" class="status__note">余额不可用</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="余额" min-width="120" align="right">
            <template #default="{ row }">
              <span class="amount">{{ formatBalanceAmount(row.amount, row.currency) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="已用" min-width="132" align="right">
            <template #default="{ row }">
              <span class="muted">{{ formatBalanceAmount(row.used, row.currency) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="同步时间" width="118" align="right">
            <template #default="{ row }">
              <span class="muted" :title="row.synced_at ?? undefined">
                {{ formatDateTimeShort(row.synced_at) }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="失败原因" min-width="220">
            <template #default="{ row }">
              <span v-if="row.error === null" class="muted">—</span>
              <span v-else class="reason" :title="row.error">{{ row.error }}</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </template>
    </div>

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
.dialog-heading h3 {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--gateway-text);
}

.dialog-heading p {
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  color: var(--gateway-muted);
}

.dialog-loading {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.skeleton-item {
  height: 2.4rem;
  border-radius: 8px;
}

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding-bottom: 0.85rem;
  margin-bottom: 0.15rem;
  font-size: 0.8125rem;
  color: var(--gateway-muted);
  border-bottom: 1px solid var(--gateway-border);
}

.stat {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}

.stat strong {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--gateway-text);
  font-variant-numeric: tabular-nums;
}

.stat__dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
}

.stat__dot--ok {
  background: #16a34a;
}

.stat__dot--fail {
  background: #dc2626;
}

.stat__dot--idle {
  background: #cbd5e1;
}

.balance-body :deep(.el-table) {
  --el-table-border-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-header-text-color: var(--gateway-muted);
  --el-table-row-hover-bg-color: #f8fafc;
  --el-table-text-color: var(--gateway-text);
  font-size: 0.8125rem;
}

.balance-body :deep(th.el-table__cell) {
  padding: 0.55rem 0;
  font-size: 0.75rem;
  font-weight: 600;
  background: transparent;
}

.balance-body :deep(td.el-table__cell) {
  padding: 0.65rem 0;
  border-bottom: 1px solid #f1f5f9;
}

.balance-body :deep(.el-table .cell) {
  white-space: nowrap;
}

.balance-body :deep(.el-table__row:last-child td.el-table__cell) {
  border-bottom: none;
}

.balance-body :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.provider {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}

.provider__name {
  font-weight: 500;
  color: var(--gateway-text);
}

.provider__type {
  font-size: 0.75rem;
  color: var(--gateway-muted);
}

.chip {
  padding: 0.05rem 0.4rem;
  font-size: 0.6875rem;
  color: var(--gateway-muted);
  background: #f1f5f9;
  border-radius: 999px;
}

.status {
  display: inline-flex;
  gap: 0.35rem;
  align-items: center;
  font-weight: 500;
}

.status__dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentcolor;
}

.status--ok {
  color: #15803d;
}

.status--fail {
  color: #b91c1c;
}

.status__note {
  display: block;
  margin-top: 0.15rem;
  font-size: 0.6875rem;
  color: #b45309;
}

.amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.muted {
  color: var(--gateway-muted);
  font-variant-numeric: tabular-nums;
}

.reason {
  display: -webkit-box;
  overflow: hidden;
  font-size: 0.75rem;
  color: #b91c1c;
  white-space: normal;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
