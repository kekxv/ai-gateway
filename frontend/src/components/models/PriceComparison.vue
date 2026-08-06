<script setup lang="ts">
import { computed } from 'vue'
import { ElTag } from 'element-plus'
import type { ModelResponse, ModelRouteResponse, ProviderResponse } from '@/api/types'
import { multiplyDecimals } from '@/utils/decimal'
import { formatMoney } from '@/utils/format'

const props = defineProps<{
  model: ModelResponse
  routes: ModelRouteResponse[]
  providers: ProviderResponse[]
}>()

type PriceTier = {
  id: number | 'base'
  max_input_tokens: number | null
  input_price_per_million: string
  output_price_per_million: string
  cache_read_price_per_million: string
  cache_write_price_per_million: string
}

const tiers = computed<PriceTier[]>(() =>
  props.model.price_tiers?.length
    ? props.model.price_tiers
    : [{
        id: 'base',
        max_input_tokens: null,
        input_price_per_million: props.model.input_price_per_million,
        output_price_per_million: props.model.output_price_per_million,
        cache_read_price_per_million: props.model.cache_read_price_per_million,
        cache_write_price_per_million: props.model.cache_write_price_per_million,
      }],
)

function providerFor(route: ModelRouteResponse): ProviderResponse | undefined {
  return props.providers.find((provider) => provider.id === route.provider_id)
}

function tierLabel(maxInputTokens: number | null): string {
  return maxInputTokens === null
    ? '不限长度'
    : `长度 ≤ ${new Intl.NumberFormat('zh-CN').format(maxInputTokens)}`
}

function formatMultiplier(value: number): string {
  return value.toFixed(2)
}

function prices(tier: PriceTier): Array<{ label: string; value: string }> {
  return [
    { label: '输入', value: tier.input_price_per_million },
    { label: '输出', value: tier.output_price_per_million },
    { label: '缓存读取', value: tier.cache_read_price_per_million },
    { label: '缓存写入', value: tier.cache_write_price_per_million },
  ]
}

function calculatedPrice(base: string, providerMultiplier: number): string {
  return formatMoney(multiplyDecimals(base, props.model.price_multiplier, providerMultiplier))
}
</script>

<template>
  <section class="price-comparison">
    <div class="section-title">按路由价格对比（每百万令牌）</div>
    <div class="price-comparison__routes">
      <template v-for="route in routes" :key="route.id">
        <article
          v-if="providerFor(route)"
          :data-test="`price-comparison-route-${String(route.id)}`"
          class="price-comparison__route"
        >
          <header class="price-comparison__route-header">
            <div>
              <div class="price-comparison__provider">{{ providerFor(route)?.name }}</div>
              <code class="price-comparison__upstream">{{ route.upstream_model }}</code>
            </div>
            <div class="price-comparison__multipliers">
              <ElTag size="small" type="warning" effect="plain">
                成本倍率 {{ formatMultiplier(providerFor(route)?.cost_multiplier ?? 1) }}x
              </ElTag>
              <ElTag size="small" type="success" effect="plain">
                用户倍率 {{ formatMultiplier(providerFor(route)?.public_multiplier ?? 1) }}x
              </ElTag>
            </div>
          </header>
          <div class="price-comparison__tiers">
            <div
              v-for="tier in tiers"
              :key="String(tier.id)"
              :data-test="`price-comparison-tier-${String(route.id)}-${String(tier.id)}`"
              class="price-comparison__tier"
            >
              <ElTag size="small" type="info" effect="plain">{{ tierLabel(tier.max_input_tokens) }}</ElTag>
              <dl class="price-comparison__metrics">
                <div v-for="price in prices(tier)" :key="price.label" class="price-comparison__metric">
                  <dt>{{ price.label }}</dt>
                  <dd>
                    <span>成本 {{ calculatedPrice(price.value, providerFor(route)?.cost_multiplier ?? 1) }}</span>
                    <span>用户价格 {{ calculatedPrice(price.value, providerFor(route)?.public_multiplier ?? 1) }}</span>
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </article>
      </template>
    </div>
  </section>
</template>

<style scoped>
.price-comparison {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.section-title {
  font-size: 0.8125rem;
  font-weight: 700;
  color: #475569;
  letter-spacing: 0.05em;
}

.price-comparison__routes,
.price-comparison__tiers {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.price-comparison__route,
.price-comparison__tier {
  padding: 0.75rem;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.price-comparison__route-header,
.price-comparison__multipliers {
  display: flex;
  gap: 0.5rem;
}

.price-comparison__route-header {
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.75rem;
}

.price-comparison__multipliers {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.price-comparison__provider {
  color: var(--gateway-text);
  font-size: 0.875rem;
  font-weight: 700;
}

.price-comparison__upstream {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  overflow-wrap: anywhere;
}

.price-comparison__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.625rem 0 0;
}

.price-comparison__metric {
  min-width: 0;
  padding: 0.5rem 0.625rem;
  background: #f8fafc;
  border-radius: 6px;
}

.price-comparison__metric dt {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  font-weight: 500;
}

.price-comparison__metric dd {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  margin: 0.2rem 0 0;
  color: var(--gateway-text);
  font-size: 0.8125rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

@media (max-width: 520px) {
  .price-comparison__route-header {
    flex-direction: column;
  }

  .price-comparison__multipliers {
    justify-content: flex-start;
  }

  .price-comparison__metrics {
    grid-template-columns: 1fr;
  }
}
</style>
