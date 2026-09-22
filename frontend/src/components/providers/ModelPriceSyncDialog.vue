<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElButton, ElDialog, ElSkeleton, ElSkeletonItem, ElTable, ElTableColumn } from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-table.css'

import { getProviderUpstreamPricing, syncProviderModelPrices } from '@/api/providers'
import type {
  ModelPriceSyncStatus,
  ProviderModelPriceRow,
  ProviderModelPriceSyncResult,
  ProviderUpstreamPricingPreview,
} from '@/api/types'
import { formatPrice } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  providerId: number | null
  providerName: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  applied: [result: ProviderModelPriceSyncResult]
}>()

const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const preview = ref<ProviderUpstreamPricingPreview | null>(null)
const result = ref<ProviderModelPriceSyncResult | null>(null)
// Empty means "leave the cost multiplier alone", which is the safe default: the account group
// reported by the upstream is not necessarily the group this relay key belongs to.
const selectedGroup = ref('')
let priceController: AbortController | undefined

const busy = computed(() => loading.value || submitting.value)
const groupOptions = computed(() => {
const entries = Object.entries(preview.value?.group_ratios ?? {})
  return entries
    .map(([name, ratio]) => ({ name, label: `${name} · ${formatPrice(ratio)}x`, ratio }))
    .sort((left, right) => left.name.localeCompare(right.name))
})
const detectedNote = computed(() => {
  const current = preview.value
  if (current === null) return ''
  if (current.detected_group === null) {
    return '未识别到账号分组（/api/user/self 需要余额查询里配置的访问令牌），成本倍率不会自动更新'
  }
  const ratio = current.detected_group_ratio
  const rendered = ratio === null ? '未列出倍率' : `${formatPrice(ratio)}x`
  return `账号分组 ${current.detected_group} · ${rendered}（来自 /api/user/self，仅供参考：计费用的是令牌分组，可能与账号分组不同）`
})

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
  const applied = result.value
  if (applied === null) return ''
  const group =
    applied.group === null
      ? '未选择上游分组（成本倍率未改动）'
      : `上游分组 ${applied.group} · 倍率 ${formatPrice(applied.group_ratio)}`
  return `${group} · 上游共列出 ${String(applied.upstream_models)} 个模型`
})

const previewStats = computed(() => {
  const current = preview.value
  if (current === null) return []
  return [
    { key: 'fillable', label: '可补齐', value: current.fillable, tone: 'ok' },
    { key: 'priced', label: '已设置', value: current.priced, tone: 'idle' },
    { key: 'fixed', label: '按次计费', value: current.fixed_price, tone: 'idle' },
    { key: 'unlisted', label: '未列出', value: current.unlisted, tone: 'warn' },
  ]
})

const stats = computed(() => {
  const applied = result.value
  if (applied === null) return []
  return [
    { key: 'updated', label: '已更新', value: applied.updated, tone: 'ok' },
    { key: 'priced', label: '已设置', value: applied.priced, tone: 'idle' },
    { key: 'fixed', label: '按次计费', value: applied.fixed_price, tone: 'idle' },
    { key: 'unlisted', label: '未列出', value: applied.unlisted, tone: 'warn' },
  ]
})

const multiplierNote = computed(() => {
  const applied = result.value
  if (applied === null || applied.cost_multiplier === null) return ''
  if (applied.cost_multiplier_updated) {
    return `已按上游分组倍率更新供应商成本倍率，当前为 ${formatPrice(applied.cost_multiplier)}`
  }
  return `供应商成本倍率保持 ${formatPrice(applied.cost_multiplier)}`
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

function reset(): void {
  preview.value = null
  result.value = null
  error.value = ''
  selectedGroup.value = ''
}

async function loadPreview(): Promise<void> {
  const providerId = props.providerId
  if (providerId === null) return
  reset()
  loading.value = true
  priceController?.abort()
  const controller = new AbortController()
  priceController = controller
  try {
    preview.value = await getProviderUpstreamPricing(providerId, controller.signal)
  } catch (err: unknown) {
    if (controller.signal.aborted) return
    error.value = err instanceof Error ? err.message : '上游价格读取失败'
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

async function applyPrices(): Promise<void> {
  const providerId = props.providerId
  if (providerId === null || busy.value || preview.value === null) return
  submitting.value = true
  error.value = ''
  priceController?.abort()
  const controller = new AbortController()
  priceController = controller
  try {
    const applied = await syncProviderModelPrices(
      providerId,
      selectedGroup.value === '' ? null : selectedGroup.value,
      controller.signal,
    )
    if (controller.signal.aborted) return
    result.value = applied
    emit('applied', applied)
  } catch (err: unknown) {
    if (controller.signal.aborted) return
    error.value = err instanceof Error ? err.message : '模型价格同步失败'
  } finally {
    if (!controller.signal.aborted) submitting.value = false
  }
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
    if (open) void loadPreview()
    else {
      priceController?.abort()
      priceController = undefined
      reset()
    }
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(() => {
  priceController?.abort()
})
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="result === null ? '同步上游模型价格' : '模型价格同步结果'"
    width="min(94vw, 56rem)"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    destroy-on-close
    data-test="price-sync-dialog"
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div class="dialog-heading">
        <h3>{{ result === null ? '同步上游模型价格' : '模型价格同步结果' }}</h3>
        <p>{{ providerName }}<template v-if="subtitle !== ''"> · {{ subtitle }}</template></p>
      </div>
    </template>

    <div class="price-body">
      <div v-if="loading" class="dialog-loading" aria-label="正在读取上游价格">
        <ElSkeleton v-for="index in 3" :key="index" animated>
          <template #template>
            <ElSkeletonItem variant="rect" class="skeleton-item" />
          </template>
        </ElSkeleton>
      </div>

      <p v-else-if="error !== ''" class="error" data-test="price-sync-error">
        {{ error }}
      </p>

      <template v-else-if="result !== null">
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

      <template v-else-if="preview !== null">
        <div class="stats" data-test="price-sync-summary">
          <span v-for="stat in previewStats" :key="stat.key" class="stat">
            <i class="stat__dot" :class="`stat__dot--${stat.tone}`" aria-hidden="true"></i>
            {{ stat.label }}
            <strong>{{ stat.value }}</strong>
          </span>
        </div>

        <div class="group-picker">
          <label for="price-sync-group">成本倍率分组</label>
          <select
            id="price-sync-group"
            v-model="selectedGroup"
            data-test="price-sync-group"
            :disabled="busy"
          >
            <option value="">不更新成本倍率</option>
            <option v-for="option in groupOptions" :key="option.name" :value="option.name">
              {{ option.label }}
            </option>
          </select>
        </div>

        <p class="note" data-test="price-sync-detected">{{ detectedNote }}</p>
        <p class="hint">
          价格与倍率相互独立：模型价格只补齐从未设置过的空价格（上游共列出
          {{ preview.upstream_models }} 个模型）；成本倍率只在你选定分组后按该分组的倍率覆写，并写入审计日志。
        </p>
      </template>
    </div>

    <template #footer>
      <div class="dialog-actions">
        <template v-if="result === null">
          <ElButton :disabled="busy" @click="requestClose">取消</ElButton>
          <ElButton
            v-if="preview !== null && error === ''"
            type="primary"
            data-test="price-sync-confirm"
            :loading="submitting"
            :disabled="busy"
            @click="applyPrices"
          >
            开始同步
          </ElButton>
        </template>
        <ElButton v-else data-test="price-sync-close" @click="requestClose">关闭</ElButton>
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

.dialog-loading {
  display: grid;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.skeleton-item {
  height: 2.25rem;
}

.error {
  margin: 0;
  padding: 0.75rem 0.9rem;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
}

.group-picker {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-top: 0.9rem;
}

.group-picker label {
  font-size: 0.8125rem;
  color: var(--gateway-muted);
}

.group-picker select {
  min-width: 16rem;
}
</style>
