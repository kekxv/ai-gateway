<script setup lang="ts">
import { computed } from 'vue'
import { ElButton, ElDialog, ElTable, ElTableColumn } from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-table.css'

import type { ModelPriceSyncStatus, ProviderModelPriceRow, ProviderModelPriceSyncResult } from '@/api/types'
import { formatPrice } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  providerName: string
  result: ProviderModelPriceSyncResult | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const statusLabels: Readonly<Record<ModelPriceSyncStatus, string>> = {
  updated: '已更新',
  priced: '已设置',
  fixed_price: '按次计费',
  unlisted: '未列出',
}

const statusTones: Readonly<Record<ModelPriceSyncStatus, string>> = {
  updated: 'ok',
  priced: 'idle',
  fixed_price: 'idle',
  unlisted: 'warn',
}

const subtitle = computed(() => {
  const result = props.result
  if (result === null) return '没有可展示的结果'
  return `上游分组 ${result.group} · 倍率 ${formatPrice(result.group_ratio)} · 上游共列出 ${String(result.upstream_models)} 个模型`
})

const stats = computed(() => {
  const result = props.result
  if (result === null) return []
  return [
    { key: 'updated', label: '已更新', value: result.updated, tone: 'ok' },
    { key: 'priced', label: '已设置', value: result.priced, tone: 'idle' },
    { key: 'fixed', label: '按次计费', value: result.fixed_price, tone: 'idle' },
    { key: 'unlisted', label: '未列出', value: result.unlisted, tone: 'warn' },
  ]
})

const multiplierNote = computed(() => {
  const result = props.result
  if (result === null || result.cost_multiplier === null) return ''
  if (result.cost_multiplier_updated) {
    return `已把上游分组倍率写入供应商成本倍率，当前为 ${formatPrice(result.cost_multiplier)}`
  }
  return `供应商成本倍率保持 ${formatPrice(result.cost_multiplier)}`
})

function statusLabel(row: ProviderModelPriceRow): string {
  return statusLabels[row.status]
}

function statusTone(row: ProviderModelPriceRow): string {
  return statusTones[row.status]
}

function ratioNote(row: ProviderModelPriceRow): string {
  if (row.status === 'fixed_price') {
    return row.upstream_fixed_price === null
      ? '按次计费'
      : `按次计费 ${formatPrice(row.upstream_fixed_price)}`
  }
  if (row.status === 'unlisted') return '上游未提供倍率'
  if (row.model_ratio === null) return ''
  const completion = row.completion_ratio === null ? '1' : formatPrice(row.completion_ratio)
  return `倍率 ${formatPrice(row.model_ratio)} × 补全 ${completion}`
}

function upstreamPrices(row: ProviderModelPriceRow): string {
  if (row.upstream_input_price_per_million === null) return '—'
  const input = formatPrice(row.upstream_input_price_per_million)
  const output = formatPrice(row.upstream_output_price_per_million)
  return `${input} / ${output}`
}

function currentPrices(row: ProviderModelPriceRow): string {
  const input = formatPrice(row.current_input_price_per_million)
  const output = formatPrice(row.current_output_price_per_million)
  if (input === '0' && output === '0') return '未设置'
  return `${input} / ${output}`
}

function requestClose(): void {
  emit('update:modelValue', false)
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    title="模型价格同步结果"
    width="min(94vw, 56rem)"
    destroy-on-close
    @update:model-value="requestClose"
  >
    <template #header>
      <div class="dialog-heading">
        <h3>模型价格同步结果</h3>
        <p>{{ providerName }} · {{ subtitle }}</p>
      </div>
    </template>

    <div class="price-body">
      <template v-if="result !== null">
        <div class="stats" data-test="price-sync-summary">
          <span v-for="stat in stats" :key="stat.key" class="stat">
            <i class="stat__dot" :class="`stat__dot--${stat.tone}`" aria-hidden="true"></i>
            {{ stat.label }}
            <strong>{{ stat.value }}</strong>
          </span>
        </div>

        <p v-if="multiplierNote !== ''" class="note" data-test="price-sync-multiplier">
          {{ multiplierNote }}
        </p>
        <p class="hint">
          只补齐从未设置过价格的模型；已设置价格的模型不会被覆盖，需要时请手动修改。上游价格为 new-api
          标价（美元 / 百万 token），写入时不做汇率换算。
        </p>

        <ElTable
          :data="result.rows"
          data-test="price-sync-table"
          class="price-table"
          max-height="24rem"
          style="width: 100%"
        >
          <ElTableColumn label="模型" min-width="200">
            <template #default="{ row }">
              <span class="model__name">{{ row.model_name }}</span>
              <span v-if="row.upstream_model !== row.model_name" class="model__upstream">
                上游 {{ row.upstream_model }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="122">
            <template #default="{ row }">
              <span class="status" :class="`status--${statusTone(row as ProviderModelPriceRow)}`">
                <i class="status__dot" aria-hidden="true"></i>
                {{ statusLabel(row as ProviderModelPriceRow) }}
              </span>
              <span v-if="ratioNote(row as ProviderModelPriceRow) !== ''" class="status__note">{{
                  ratioNote(row as ProviderModelPriceRow)
                }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="上游价格（输入 / 输出）" min-width="170" align="right">
            <template #default="{ row }">
              <span class="price">{{ upstreamPrices(row as ProviderModelPriceRow) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="本地价格（输入 / 输出）" min-width="170" align="right">
            <template #default="{ row }">
              <span class="muted">{{ currentPrices(row as ProviderModelPriceRow) }}</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </template>
    </div>

    <template #footer>
      <div class="dialog-actions">
        <ElButton data-test="price-sync-close" @click="requestClose">关闭</ElButton>
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

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding-bottom: 0.85rem;
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

.stat__dot--idle {
  background: #cbd5e1;
}

.stat__dot--warn {
  background: #d97706;
}

.note {
  margin: 0.75rem 0 0;
  font-size: 0.8125rem;
  color: var(--gateway-text);
}

.hint {
  margin: 0.35rem 0 0.9rem;
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--gateway-muted);
}

.price-body :deep(.el-table) {
  --el-table-border-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-header-text-color: var(--gateway-muted);
  --el-table-row-hover-bg-color: #f8fafc;
  --el-table-text-color: var(--gateway-text);
  font-size: 0.8125rem;
}

.price-body :deep(th.el-table__cell) {
  padding: 0.55rem 0;
  font-size: 0.75rem;
  font-weight: 600;
  background: transparent;
}

.price-body :deep(td.el-table__cell) {
  padding: 0.65rem 0;
  border-bottom: 1px solid #f1f5f9;
}

.price-body :deep(.el-table .cell) {
  white-space: nowrap;
}

.price-body :deep(.el-table__row:last-child td.el-table__cell) {
  border-bottom: none;
}

.price-body :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.model__name {
  font-weight: 500;
  color: var(--gateway-text);
}

.model__upstream {
  display: block;
  font-size: 0.75rem;
  color: var(--gateway-muted);
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

.status--idle {
  color: var(--gateway-muted);
}

.status--warn {
  color: #b45309;
}

.status__note {
  display: block;
  margin-top: 0.15rem;
  font-size: 0.6875rem;
  color: var(--gateway-muted);
}

.price {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.muted {
  color: var(--gateway-muted);
  font-variant-numeric: tabular-nums;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
