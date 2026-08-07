<script setup lang="ts">
import { computed } from 'vue'
import { BarChart, type BarSeriesOption } from 'echarts/charts'
import {
  AriaComponent,
  type AriaComponentOption,
  GridComponent,
  type GridComponentOption,
  TooltipComponent,
  type TooltipComponentOption,
} from 'echarts/components'
import { type ComposeOption, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { ElDialog, ElTable, ElTableColumn, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/el-tag.css'

import type { ModelResponse, ModelRouteResponse, ProviderResponse } from '@/api/types'
import { multiplyDecimals } from '@/utils/decimal'
import { formatMoney } from '@/utils/format'
import VChart from 'vue-echarts'

use([AriaComponent, BarChart, CanvasRenderer, GridComponent, TooltipComponent])

type ChartOption = ComposeOption<
  | AriaComponentOption
  | BarSeriesOption
  | GridComponentOption
  | TooltipComponentOption
>

const props = defineProps<{
  modelValue: boolean
  models: ModelResponse[]
  routes: ModelRouteResponse[]
  providers: ProviderResponse[]
}>()

const emit = defineEmits<{
  'update:modelValue': [open: boolean]
}>()

type PriceTier = {
  id: number | 'base'
  maxInputTokens: number | null
  input: string
  output: string
  cacheRead: string
  cacheWrite: string
}

interface PriceRange {
  cost: string
  user: string
}

interface ComparisonRow {
  key: string
  modelName: string
  canonicalName: string
  tier: string
  eligibleRouteCount: number
  input: PriceRange
  output: PriceRange
  cacheRead: PriceRange
  cacheWrite: PriceRange
  inputUserMinimum: number | null
  outputUserMinimum: number | null
}

function configuredTiers(model: ModelResponse): PriceTier[] {
  if ((model.price_tiers?.length ?? 0) > 0) {
    return (model.price_tiers ?? []).map((tier) => ({
      id: tier.id,
      maxInputTokens: tier.max_input_tokens,
      input: tier.input_price_per_million,
      output: tier.output_price_per_million,
      cacheRead: tier.cache_read_price_per_million,
      cacheWrite: tier.cache_write_price_per_million,
    }))
  }
  return [{
    id: 'base',
    maxInputTokens: null,
    input: model.input_price_per_million,
    output: model.output_price_per_million,
    cacheRead: model.cache_read_price_per_million,
    cacheWrite: model.cache_write_price_per_million,
  }]
}

function eligibleProviders(modelId: number): ProviderResponse[] {
  const providerIds = new Set(
    props.routes
      .filter((route) => route.model_id === modelId && route.enabled && route.weight > 0)
      .map((route) => route.provider_id),
  )
  return props.providers.filter(
    (provider) =>
      providerIds.has(provider.id) &&
      provider.enabled &&
      provider.protocols.some((protocol) => protocol.enabled),
  )
}

function decimalMinorUnits(value: string): bigint {
  return BigInt(value.replace('.', ''))
}

function formatRange(values: string[]): string {
  if (values.length === 0) return '—'
  const ordered = [...values].sort((left, right) => {
    const leftValue = decimalMinorUnits(left)
    const rightValue = decimalMinorUnits(right)
    return leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0
  })
  const minimum = ordered[0]
  const maximum = ordered.at(-1)
  if (minimum === undefined || maximum === undefined) return '—'
  return minimum === maximum
    ? formatMoney(minimum)
    : `${formatMoney(minimum)} – ${formatMoney(maximum)}`
}

function priceRange(
  model: ModelResponse,
  providers: ProviderResponse[],
  base: string,
): PriceRange {
  return {
    cost: formatRange(
      providers.map((provider) =>
        multiplyDecimals(base, model.price_multiplier, provider.cost_multiplier),
      ),
    ),
    user: formatRange(
      providers.map((provider) =>
        multiplyDecimals(base, model.price_multiplier, provider.public_multiplier),
      ),
    ),
  }
}

function publicPrices(
  model: ModelResponse,
  providers: ProviderResponse[],
  base: string,
): string[] {
  return providers.map((provider) =>
    multiplyDecimals(base, model.price_multiplier, provider.public_multiplier),
  )
}

function minimumPrice(values: string[]): number | null {
  if (values.length === 0) return null
  const minimum = values.reduce((current, value) =>
    decimalMinorUnits(value) < decimalMinorUnits(current) ? value : current,
  )
  return Number(minimum)
}

function tierLabel(maxInputTokens: number | null): string {
  if (maxInputTokens === null) return '不限长度'
  if (maxInputTokens % 1000 === 0) return `Length ≤ ${String(maxInputTokens / 1000)}K`
  return `Length ≤ ${new Intl.NumberFormat('zh-CN').format(maxInputTokens)}`
}

const rows = computed<ComparisonRow[]>(() =>
  props.models.flatMap((model) => {
    const providers = eligibleProviders(model.id)
    return configuredTiers(model).map((tier) => ({
      key: `${String(model.id)}-${String(tier.id)}`,
      modelName: model.display_name,
      canonicalName: model.canonical_name,
      tier: tierLabel(tier.maxInputTokens),
      eligibleRouteCount: providers.length,
      input: priceRange(model, providers, tier.input),
      output: priceRange(model, providers, tier.output),
      cacheRead: priceRange(model, providers, tier.cacheRead),
      cacheWrite: priceRange(model, providers, tier.cacheWrite),
      inputUserMinimum: minimumPrice(publicPrices(model, providers, tier.input)),
      outputUserMinimum: minimumPrice(publicPrices(model, providers, tier.output)),
    }))
  }),
)

const chartRows = computed(() =>
  rows.value.filter((row) => row.inputUserMinimum !== null || row.outputUserMinimum !== null),
)

const comparisonChart = computed<ChartOption>(() => ({
  aria: {
    enabled: true,
    description: '比较所选模型每百万 Token 的最低用户输入与输出单价。',
  },
  grid: { left: 58, right: 24, top: 28, bottom: 76 },
  tooltip: {
    trigger: 'axis',
    valueFormatter: (value: unknown) => formatMoney(Number(value).toFixed(8)),
  },
  xAxis: {
    type: 'category',
    data: chartRows.value.map((row) => `${row.modelName} · ${row.tier}`),
    axisLabel: { rotate: 26, interval: 0 },
  },
  yAxis: { type: 'value', name: '¥ / 百万 Tokens' },
  series: [
    {
      name: '输入单价',
      type: 'bar',
      data: chartRows.value.map((row) => row.inputUserMinimum),
      itemStyle: { color: '#2563eb', borderRadius: [5, 5, 0, 0] },
    },
    {
      name: '输出单价',
      type: 'bar',
      data: chartRows.value.map((row) => row.outputUserMinimum),
      itemStyle: { color: '#0f766e', borderRadius: [5, 5, 0, 0] },
    },
  ],
}))

const selectedModelNames = computed(() => props.models.map((model) => model.display_name))
const eligibleProviderCount = computed(() =>
  new Set(
    props.models.flatMap((model) => eligibleProviders(model.id).map((provider) => provider.id)),
  ).size,
)

function cheapestRow(field: 'inputUserMinimum' | 'outputUserMinimum'): ComparisonRow | null {
  return chartRows.value.reduce<ComparisonRow | null>((cheapest, row) => {
    if (row[field] === null) return cheapest
    if (cheapest === null || cheapest[field] === null || row[field] < cheapest[field]) return row
    return cheapest
  }, null)
}

const cheapestInput = computed(() => cheapestRow('inputUserMinimum'))
const cheapestOutput = computed(() => cheapestRow('outputUserMinimum'))

function priceLabel(row: ComparisonRow | null, field: 'inputUserMinimum' | 'outputUserMinimum'): string {
  const value = row?.[field]
  return value === null || value === undefined ? '—' : formatMoney(value.toFixed(8))
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    data-test="model-price-comparison-dialog"
    title="模型价格对比"
    width="min(96vw, 92rem)"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="comparison-description">
      按模型和价格分段比较每百万 Token 成本与用户价格；价格范围来自当前启用的供应商路由。
    </p>
    <section class="comparison-overview">
      <div class="comparison-summary" data-test="model-comparison-summary">
        <div class="summary-card">
          <span>已选模型</span>
          <strong>{{ selectedModelNames.length }}</strong>
          <small>个参与比对</small>
        </div>
        <div class="summary-card">
          <span>可用供应商</span>
          <strong>{{ eligibleProviderCount }}</strong>
          <small>启用且支持协议</small>
        </div>
        <div class="summary-card summary-card--input">
          <span>最低输入单价</span>
          <strong>{{ priceLabel(cheapestInput, 'inputUserMinimum') }}</strong>
          <small>{{ cheapestInput?.modelName ?? '暂无可用路由' }}</small>
        </div>
        <div class="summary-card summary-card--output">
          <span>最低输出单价</span>
          <strong>{{ priceLabel(cheapestOutput, 'outputUserMinimum') }}</strong>
          <small>{{ cheapestOutput?.modelName ?? '暂无可用路由' }}</small>
        </div>
      </div>

      <div class="selected-models" aria-label="已选模型">
        <span>已选模型</span>
        <ElTag v-for="modelName in selectedModelNames" :key="modelName" effect="plain" round>{{ modelName }}</ElTag>
      </div>

      <section class="comparison-chart" data-test="model-comparison-chart">
        <div class="comparison-chart__heading">
          <div>
            <h3>最低用户单价</h3>
            <p>每百万 Tokens；仅统计可用供应商路由。</p>
          </div>
          <div class="chart-legend" aria-label="图例"><span class="legend-swatch legend-swatch--input" />输入 <span class="legend-swatch legend-swatch--output" />输出</div>
        </div>
        <VChart v-if="chartRows.length > 0" :option="comparisonChart" autoresize />
        <p v-else class="chart-empty">所选模型暂无可用供应商路由，无法生成价格图表。</p>
      </section>
    </section>

    <section class="comparison-table-section">
      <div><h3>分段价格明细</h3><p>完整价格范围保留，便于核对成本与用户价格。</p></div>
      <div class="comparison-table-wrap">
        <ElTable :data="rows" row-key="key" border class="comparison-table">
          <ElTableColumn label="模型" min-width="180" fixed>
            <template #default="{ row }">
              <strong>{{ row.modelName }}</strong>
              <code class="canonical-name">{{ row.canonicalName }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn label="价格分段" min-width="145">
            <template #default="{ row }">
              <ElTag effect="plain">{{ row.tier }}</ElTag>
              <small v-if="row.eligibleRouteCount === 0" class="route-warning">暂无启用路由</small>
            </template>
          </ElTableColumn>
          <ElTableColumn label="输入" align="center">
            <ElTableColumn prop="input.cost" label="成本" min-width="190" />
            <ElTableColumn prop="input.user" label="用户价格" min-width="190" />
          </ElTableColumn>
          <ElTableColumn label="输出" align="center">
            <ElTableColumn prop="output.cost" label="成本" min-width="190" />
            <ElTableColumn prop="output.user" label="用户价格" min-width="190" />
          </ElTableColumn>
          <ElTableColumn label="缓存读取" align="center">
            <ElTableColumn prop="cacheRead.cost" label="成本" min-width="190" />
            <ElTableColumn prop="cacheRead.user" label="用户价格" min-width="190" />
          </ElTableColumn>
          <ElTableColumn label="缓存写入" align="center">
            <ElTableColumn prop="cacheWrite.cost" label="成本" min-width="190" />
            <ElTableColumn prop="cacheWrite.user" label="用户价格" min-width="190" />
          </ElTableColumn>
        </ElTable>
      </div>
    </section>
  </ElDialog>
</template>

<style scoped>
.comparison-description {
  margin: 0 0 1rem;
  color: var(--gateway-muted);
  line-height: 1.5;
}

.comparison-overview {
  display: grid;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.comparison-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .75rem;
}

.summary-card {
  display: grid;
  gap: .3rem;
  min-width: 0;
  padding: .85rem 1rem;
  background: linear-gradient(135deg, #eff6ff, #fff);
  border: 1px solid #bfdbfe;
  border-radius: .7rem;
}

.summary-card--input { background: linear-gradient(135deg, #eff6ff, #f8fafc); }
.summary-card--output { background: linear-gradient(135deg, #ecfdf5, #f8fafc); border-color: #a7f3d0; }
.summary-card span, .summary-card small, .selected-models > span, .comparison-chart p, .comparison-table-section p { color: var(--gateway-muted); }
.summary-card strong { overflow-wrap: anywhere; font-size: 1.05rem; }

.selected-models {
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
  align-items: center;
}

.selected-models > span { margin-right: .15rem; font-size: .875rem; }

.comparison-chart,
.comparison-table-section {
  padding: 1rem;
  background: var(--gateway-bg);
  border: 1px solid var(--gateway-border);
  border-radius: .75rem;
}

.comparison-chart__heading {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  justify-content: space-between;
}

.comparison-chart h3,
.comparison-table-section h3 { margin: 0; font-size: 1rem; }
.comparison-chart p,
.comparison-table-section p { margin: .3rem 0 0; font-size: .875rem; }
.comparison-chart :deep(.echarts) { width: 100%; height: 20rem; }
.chart-empty { min-height: 10rem; display: grid; place-items: center; text-align: center; }

.chart-legend { display: flex; gap: .4rem; align-items: center; color: var(--gateway-muted); font-size: .8125rem; white-space: nowrap; }
.legend-swatch { width: .7rem; height: .7rem; border-radius: .2rem; }
.legend-swatch--input { background: #2563eb; }
.legend-swatch--output { background: #0f766e; }

.comparison-table-section { display: grid; gap: 1rem; }
.comparison-table-wrap { overflow-x: auto; }

.comparison-table {
  width: 100%;
}

.canonical-name,
.route-warning {
  display: block;
  margin-top: 0.25rem;
}

.canonical-name {
  color: var(--gateway-muted);
  overflow-wrap: anywhere;
  white-space: normal;
}

.route-warning {
  color: var(--el-color-warning-dark-2);
}

@media (max-width: 760px) {
  .comparison-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .comparison-chart__heading { flex-direction: column; }
  .comparison-chart :deep(.echarts) { height: 17rem; }
}
</style>
