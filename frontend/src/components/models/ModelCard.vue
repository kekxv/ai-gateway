<script setup lang="ts">
import { computed, ref } from 'vue'
import { Edit, Delete, Plus, CopyDocument, Check } from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElTag } from 'element-plus'
import type {
  ModelResponse,
  ModelRouteResponse,
  Protocol,
  ProviderResponse,
  RouteRuntimeState,
  RouteSource,
} from '@/api/types'
import StatusTag from '@/components/common/StatusTag.vue'
import { formatMoney } from '@/utils/format'

const props = defineProps<{
  model: ModelResponse
  routes: ModelRouteResponse[]
  providers: ProviderResponse[]
  loading?: boolean
  nonDeletable?: boolean
  routesLoading?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  edit: [model: ModelResponse]
  delete: [model: ModelResponse]
  disable: [modelId: number]
  editRoute: [route: ModelRouteResponse]
  deleteRoute: [route: ModelRouteResponse]
  disableRoute: [routeId: number, modelId: number]
  recoverRoute: [routeId: number, modelId: number]
  createRoute: []
}>()

const routesExpanded = ref(false)
const copiedField = ref<string | null>(null)

interface LegacyClipboardDocument {
  execCommand(commandId: string): boolean
}

const protocolLabels: Readonly<Record<Protocol, string>> = {
  openai: 'OpenAI',
  claude: 'Claude',
  gemini: 'Gemini',
}

const sourceLabels: Readonly<Record<RouteSource, string>> = {
  manual: '手动',
  discovered: '自动发现',
}

const runtimeDetails: Readonly<
  Record<RouteRuntimeState, { label: string; type: 'success' | 'warning' | 'danger' }>
> = {
  closed: { label: '健康', type: 'success' },
  half_open: { label: '探测中', type: 'warning' },
  open: { label: '不可用', type: 'danger' },
}

function providerName(providerId: number): string {
  return (
    props.providers.find((provider) => provider.id === providerId)?.name ??
    `#${String(providerId)}`
  )
}

function providerProtocolNames(providerId: number): string {
  const protocols = props.providers
    .find((provider) => provider.id === providerId)
    ?.protocols.filter((protocol) => protocol.enabled)
    .map((protocol) => protocolLabels[protocol.protocol])
  return protocols === undefined || protocols.length === 0
    ? '无启用协议'
    : protocols.join(' / ')
}

function formatDate(value: string | null): string {
  if (value === null) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function tierLabel(maxInputTokens: number | null): string {
  return maxInputTokens === null
    ? '不限长度'
    : `长度 ≤ ${new Intl.NumberFormat('zh-CN').format(maxInputTokens)}`
}

function formatPriceRange(minimum: string, maximum: string): string {
  return minimum === maximum
    ? formatMoney(minimum)
    : `${formatMoney(minimum)} – ${formatMoney(maximum)}`
}

const routeStats = computed(() => {
  const enabled = props.routes.filter((r) => r.enabled).length
  const healthy = props.routes.filter((r) => r.runtime_state === 'closed').length
  return { enabled, healthy, total: props.routes.length }
})

async function copyToClipboard(text: string, field: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    copiedField.value = field
    setTimeout(() => {
      copiedField.value = null
    }, 2000)
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      const legacyDocument = document as unknown as LegacyClipboardDocument
      legacyDocument.execCommand('copy')
      copiedField.value = field
      setTimeout(() => {
        copiedField.value = null
      }, 2000)
    } finally {
      document.body.removeChild(textarea)
    }
  }
}
</script>

<template>
  <div class="model-card" :class="{ 'is-disabled': !model.enabled }">
    <div class="card-header">
      <div class="model-info">
        <h3 class="model-name" :title="model.display_name">{{ model.display_name }}</h3>
        <StatusTag
          :data-test="`model-status-${String(model.id)}`"
          :status="model.enabled ? 'enabled' : 'disabled'"
        />
      </div>
      <div v-if="readonly !== true" class="card-actions">
        <ElButton
          :data-test="`edit-model-${String(model.id)}`"
          size="small"
          :disabled="loading === true"
          @click="emit('edit', model)"
        >
          <ElIcon><Edit /></ElIcon>
          编辑
        </ElButton>
        <ElButton
          size="small"
          type="danger"
          :data-test="`delete-model-${String(model.id)}`"
          :disabled="loading === true || nonDeletable === true"
          :title="nonDeletable ? '该模型已有请求历史，请改为停用' : undefined"
          @click="emit('delete', model)"
        >
          <ElIcon><Delete /></ElIcon>
          删除
        </ElButton>
      </div>
    </div>

    <div class="card-body">
      <div v-if="(model.price_tiers?.length ?? 0) > 0 || (model.public_price_tiers?.length ?? 0) > 0" class="info-item">
        <span class="label">规范名称：</span>
        <code>{{ model.canonical_name }}</code>
      </div>
      <div v-if="readonly === true && (model.public_price_tiers?.length ?? 0) > 0" class="price-tiers">
        <div class="section-title">公开价格（每百万令牌）</div>
        <div
          v-for="(tier, index) in model.public_price_tiers"
          :key="String(tier.max_input_tokens)"
          class="price-tier"
          :data-test="`public-model-price-tier-${String(index)}`"
        >
          <div class="price-tier__header">
            <ElTag size="small" type="primary" effect="plain">{{ tierLabel(tier.max_input_tokens) }}</ElTag>
          </div>
          <dl class="price-tier__prices">
            <div class="price-metric">
              <dt class="price-metric__label">输入</dt>
              <dd class="price-metric__value">{{ formatPriceRange(tier.input_price_per_million_min, tier.input_price_per_million_max) }}</dd>
            </div>
            <div class="price-metric">
              <dt class="price-metric__label">输出</dt>
              <dd class="price-metric__value">{{ formatPriceRange(tier.output_price_per_million_min, tier.output_price_per_million_max) }}</dd>
            </div>
            <div class="price-metric">
              <dt class="price-metric__label">缓存读取</dt>
              <dd class="price-metric__value">{{ formatPriceRange(tier.cache_read_price_per_million_min, tier.cache_read_price_per_million_max) }}</dd>
            </div>
            <div class="price-metric">
              <dt class="price-metric__label">缓存写入</dt>
              <dd class="price-metric__value">{{ formatPriceRange(tier.cache_write_price_per_million_min, tier.cache_write_price_per_million_max) }}</dd>
            </div>
          </dl>
        </div>
      </div>
      <div v-else-if="(model.price_tiers?.length ?? 0) > 0" class="price-tiers">
        <div class="section-title">分段价格（每百万令牌）</div>
        <div
          v-for="tier in model.price_tiers"
          :key="tier.id"
          class="price-tier"
          :data-test="`model-price-tier-${String(tier.id)}`"
        >
          <div class="price-tier__header">
            <ElTag size="small" type="info" effect="plain">{{ tierLabel(tier.max_input_tokens) }}</ElTag>
          </div>
          <dl class="price-tier__prices">
            <div class="price-metric">
              <dt class="price-metric__label">输入</dt>
              <dd class="price-metric__value">{{ formatMoney(tier.input_price_per_million) }}</dd>
            </div>
            <div class="price-metric">
              <dt class="price-metric__label">输出</dt>
              <dd class="price-metric__value">{{ formatMoney(tier.output_price_per_million) }}</dd>
            </div>
            <div class="price-metric">
              <dt class="price-metric__label">缓存读取</dt>
              <dd class="price-metric__value">{{ formatMoney(tier.cache_read_price_per_million) }}</dd>
            </div>
            <div class="price-metric">
              <dt class="price-metric__label">缓存写入</dt>
              <dd class="price-metric__value">{{ formatMoney(tier.cache_write_price_per_million) }}</dd>
            </div>
          </dl>
        </div>
      </div>
      <div v-else class="basic-info">
        <div class="info-item">
          <span class="label">规范名称：</span>
          <button
            class="copyable-code"
            :class="{ 'is-copied': copiedField === 'canonical' }"
            :title="`点击复制: ${model.canonical_name}`"
            @click="copyToClipboard(model.canonical_name, 'canonical')"
          >
            <code>{{ model.canonical_name }}</code>
            <ElIcon v-if="copiedField === 'canonical'" class="copy-icon"><Check /></ElIcon>
            <ElIcon v-else class="copy-icon"><CopyDocument /></ElIcon>
          </button>
        </div>
        <div class="info-item">
          <span class="label">输入价格：</span>
          <span class="value">{{ formatMoney(model.input_price_per_million) }}</span>
        </div>
        <div class="info-item">
          <span class="label">输出价格：</span>
          <span class="value">{{ formatMoney(model.output_price_per_million) }}</span>
        </div>
        <div class="info-item">
          <span class="label">缓存读取价格：</span>
          <span class="value">{{ formatMoney(model.cache_read_price_per_million) }}</span>
        </div>
        <div class="info-item">
          <span class="label">缓存写入价格：</span>
          <span class="value">{{ formatMoney(model.cache_write_price_per_million) }}</span>
        </div>
      </div>
      <div v-if="readonly !== true && parseFloat(String(model.price_multiplier ?? 1)) !== 1.00" class="model-multiplier">
        <span class="label">模型倍率：</span>
        <ElTag type="warning" size="small">{{ parseFloat(String(model.price_multiplier ?? 1)).toFixed(2) }}x</ElTag>
      </div>

      <div v-if="model.aliases.length > 0" class="aliases-section">
        <div class="section-title">别名</div>
        <div class="aliases-list">
          <ElTag
            v-for="alias in model.aliases"
            :key="alias.id"
            :type="alias.enabled ? 'primary' : 'info'"
            effect="plain"
            size="small"
          >
            {{ alias.alias }}
          </ElTag>
        </div>
      </div>

      <div v-if="readonly !== true" class="routes-section">
        <div class="routes-header">
          <button
            class="routes-toggle"
            :disabled="routesLoading"
            @click="routesExpanded = !routesExpanded"
          >
            <div class="section-title">
              模型路由
              <ElTag size="small" type="info" effect="plain">
                {{ routeStats.enabled }}/<span :data-test="`route-count-${String(model.id)}`">{{ routeStats.total }}</span> 启用
              </ElTag>
              <ElTag size="small" type="success" effect="plain">
                {{ routeStats.healthy }}/{{ routeStats.total }} 健康
              </ElTag>
            </div>
            <span class="expand-indicator">{{ routesExpanded ? '收起' : '展开' }}</span>
          </button>
          <ElButton
            size="small"
            type="primary"
            plain
            :data-test="`create-route-${String(model.id)}`"
            :disabled="loading === true || routesLoading === true"
            @click="emit('createRoute')"
          >
            <ElIcon><Plus /></ElIcon>
            添加路由
          </ElButton>
        </div>

        <div v-if="routesLoading" class="routes-loading">
          <div class="loading-text">加载中...</div>
        </div>
        <div v-else-if="routes.length === 0" class="routes-empty">
          <div class="empty-text">暂无路由配置</div>
        </div>
        <div v-else-if="routesExpanded" class="routes-grid">
          <div
            v-for="route in routes"
            :key="route.id"
            class="route-item"
            :class="{
              'is-disabled': !route.enabled,
              'is-unhealthy': route.runtime_state === 'open',
            }"
          >
            <div class="route-header">
              <div class="route-provider">
                <ElTag size="small" effect="plain">
                  {{ providerProtocolNames(route.provider_id) }}
                </ElTag>
                <span class="provider-name">{{ providerName(route.provider_id) }}</span>
              </div>
              <div class="route-actions">
                <ElButton
                  v-if="route.enabled && route.runtime_state !== 'closed'"
                  :data-test="`recover-route-${String(route.id)}`"
                  size="small"
                  text
                  type="success"
                  :disabled="loading === true"
                  @click="emit('recoverRoute', route.id, route.model_id)"
                >
                  恢复
                </ElButton>
                <ElButton
                  :data-test="`edit-route-${String(route.id)}`"
                  :aria-label="`编辑路由 ${route.upstream_model}`"
                  size="small"
                  text
                  :disabled="loading === true"
                  @click="emit('editRoute', route)"
                >
                  <ElIcon><Edit /></ElIcon>
                </ElButton>
                <ElButton
                  :data-test="`delete-route-${String(route.id)}`"
                  :aria-label="`删除路由 ${route.upstream_model}`"
                  size="small"
                  text
                  type="danger"
                  :disabled="loading === true"
                  @click="emit('deleteRoute', route)"
                >
                  <ElIcon><Delete /></ElIcon>
                </ElButton>
                <ElButton
                  :data-test="`disable-route-${String(route.id)}`"
                  size="small"
                  text
                  type="warning"
                  :disabled="loading === true || !route.enabled"
                  @click="emit('disableRoute', route.id, route.model_id)"
                >
                  停用
                </ElButton>
              </div>
            </div>
            <div class="route-model">{{ route.upstream_model }}</div>
            <div class="route-stats">
              <span class="stat">权重: {{ route.weight }}</span>
              <StatusTag
                :data-test="`route-status-${String(route.id)}`"
                :status="route.enabled ? 'enabled' : 'disabled'"
              />
              <ElTag :type="runtimeDetails[route.runtime_state].type" size="small" effect="light">
                {{ runtimeDetails[route.runtime_state].label }}
              </ElTag>
              <ElTag :type="route.source === 'discovered' ? 'primary' : 'info'" size="small">
                {{ sourceLabels[route.source] }}
              </ElTag>
            </div>
            <div v-if="route.consecutive_failures > 0" class="route-failures">
              连续失败: {{ route.consecutive_failures }}
              <span v-if="route.disabled_until" class="disabled-until">
                (至 {{ formatDate(route.disabled_until) }})
              </span>
            </div>
            <div v-if="route.last_error_code" class="route-error">
              错误: {{ route.last_error_code }}
            </div>
          </div>
        </div>
        <div v-else class="routes-collapsed">
          <div class="collapsed-routes">
            <div
              v-for="route in routes.slice(0, 3)"
              :key="route.id"
              class="collapsed-route-tag"
            >
              <ElTag
                size="small"
                :type="route.enabled ? (route.runtime_state === 'closed' ? 'success' : route.runtime_state === 'open' ? 'danger' : 'warning') : 'info'"
                effect="light"
              >
                {{ providerName(route.provider_id) }} · {{ route.upstream_model }}
              </ElTag>
            </div>
            <div v-if="routes.length > 3" class="more-routes">
              <ElTag size="small" type="info" effect="plain">
                +{{ routes.length - 3 }} 更多
              </ElTag>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-card {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid var(--gateway-border);
  border-radius: 16px;
  padding: 1.5rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.05);
}

.model-card:hover {
  border-color: var(--gateway-brand);
  box-shadow: 0 8px 24px rgb(37 99 235 / 0.12), 0 2px 8px rgb(0 0 0 / 0.08);
  transform: translateY(-2px);
}

.model-card.is-disabled {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.25rem;
  gap: 1rem;
}

.model-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
}

.model-name {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--gateway-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.card-actions :deep(.el-button) {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.basic-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
  padding: 0.875rem;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.price-tiers {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.price-tiers > .section-title {
  margin-bottom: 0.125rem;
}

.price-tier {
  min-width: 0;
  padding: 0.75rem;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.price-tier__header {
  display: flex;
  align-items: center;
  margin-bottom: 0.625rem;
}

.price-tier__prices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0;
}

.price-metric {
  min-width: 0;
  padding: 0.5rem 0.625rem;
  background: #f8fafc;
  border-radius: 6px;
}

.price-metric__label {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.25;
}

.price-metric__value {
  margin: 0.2rem 0 0;
  color: var(--gateway-text);
  font-size: 0.8125rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.model-multiplier {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.info-item .label {
  color: var(--gateway-muted);
  font-size: 0.8125rem;
  font-weight: 500;
}

.info-item .value {
  color: var(--gateway-text);
  font-size: 0.875rem;
  font-weight: 600;
}

.info-item.multiplier {
  grid-column: 1 / -1;
  margin-top: 0.25rem;
  padding-top: 0.5rem;
  border-top: 1px solid #e2e8f0;
}

.info-item.multiplier .label {
  font-weight: 600;
}

.copyable-code {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  background: #e2e8f0;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  font: inherit;
}

.copyable-code:hover {
  border-color: var(--gateway-brand);
  background: #cbd5e1;
}

.copyable-code.is-copied {
  background: #d1fae5;
  border-color: #10b981;
}

.copyable-code code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #334155;
  margin: 0;
  padding: 0;
  background: none;
  border-radius: 0;
}

.copy-icon {
  font-size: 0.75rem;
  color: var(--gateway-muted);
}

.copyable-code.is-copied .copy-icon {
  color: #10b981;
}

.aliases-section {
  border-top: 1px solid var(--gateway-border);
  padding-top: 1rem;
}

.section-title {
  font-size: 0.8125rem;
  font-weight: 700;
  color: #475569;
  margin-bottom: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.aliases-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.routes-section {
  border-top: 1px solid var(--gateway-border);
  padding-top: 1.25rem;
}

.routes-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.routes-toggle {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.routes-toggle .section-title {
  margin-bottom: 0;
}

.expand-indicator {
  font-size: 0.75rem;
  color: var(--gateway-brand);
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
}

.routes-loading,
.routes-empty {
  padding: 2.5rem;
  text-align: center;
  background: #f8fafc;
  border-radius: 10px;
  border: 2px dashed #cbd5e1;
}

.loading-text,
.empty-text {
  color: var(--gateway-muted);
  font-size: 0.875rem;
  font-weight: 500;
}

.routes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 0.875rem;
}

.route-item {
  padding: 1rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s;
}

.route-item:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgb(0 0 0 / 0.05);
  transform: translateY(-1px);
}

.route-item.is-disabled {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.route-item.is-unhealthy {
  border-color: var(--el-color-danger);
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
}

.route-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.625rem;
}

.route-provider {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
}

.provider-name {
  font-size: 0.8125rem;
  color: var(--gateway-text);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-actions {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.route-model {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.8125rem;
  color: var(--gateway-text);
  margin-bottom: 0.625rem;
  word-break: break-all;
  font-weight: 600;
}

.route-stats {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.route-stats .stat {
  font-size: 0.75rem;
  color: var(--gateway-muted);
  font-weight: 500;
}

.route-failures {
  margin-top: 0.625rem;
  padding: 0.5rem 0.625rem;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-radius: 6px;
  font-size: 0.75rem;
  color: #92400e;
  font-weight: 600;
  border: 1px solid #fbbf24;
}

.disabled-until {
  color: var(--gateway-muted);
  font-weight: 500;
}

.route-error {
  margin-top: 0.625rem;
  padding: 0.5rem 0.625rem;
  background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
  border-radius: 6px;
  font-size: 0.75rem;
  color: #991b1b;
  font-weight: 600;
  border: 1px solid #f87171;
}

.routes-collapsed {
  padding: 0.5rem 0;
}

.collapsed-routes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.collapsed-route-tag {
  display: inline-block;
}

.more-routes {
  display: inline-block;
}

@media (max-width: 640px) {
  .card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .card-actions {
    justify-content: flex-end;
  }

  .basic-info {
    grid-template-columns: 1fr;
  }

  .price-tier__prices {
    grid-template-columns: 1fr;
  }

  .routes-grid {
    grid-template-columns: 1fr;
  }

  .routes-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }
}
</style>
