<script setup lang="ts">
import { computed } from 'vue'
import { ElDialog, ElTable, ElTableColumn, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/el-tag.css'

import type { ModelResponse, ModelRouteResponse, ProviderResponse } from '@/api/types'
import { multiplyDecimals } from '@/utils/decimal'
import { formatMoney } from '@/utils/format'

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
    }))
  }),
)
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
  </ElDialog>
</template>

<style scoped>
.comparison-description {
  margin: 0 0 1rem;
  color: var(--gateway-muted);
  line-height: 1.5;
}

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
</style>
