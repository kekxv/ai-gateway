<script setup lang="ts">
import { computed, ref } from 'vue'
import { Edit, Delete, Plus } from '@element-plus/icons-vue'
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
}>()

const emit = defineEmits<{
  edit: [model: ModelResponse]
  delete: [model: ModelResponse]
  disable: [modelId: number]
  editRoute: [route: ModelRouteResponse]
  deleteRoute: [route: ModelRouteResponse]
  disableRoute: [routeId: number, modelId: number]
  createRoute: []
}>()

const expanded = ref(false)

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

function protocolName(providerId: number, protocolId: number): string {
  const protocol = props.providers
    .find((provider) => provider.id === providerId)
    ?.protocols.find((item) => item.id === protocolId)
  return protocol === undefined ? `#${String(protocolId)}` : protocolLabels[protocol.protocol]
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

const routeStats = computed(() => {
  const enabled = props.routes.filter((r) => r.enabled).length
  const healthy = props.routes.filter((r) => r.runtime_state === 'closed').length
  return { enabled, healthy, total: props.routes.length }
})
</script>

<template>
  <div class="model-card" :class="{ 'is-disabled': !model.enabled, 'is-expanded': expanded }">
    <div class="card-header">
      <div class="model-info">
        <h3 class="model-name">{{ model.display_name }}</h3>
        <StatusTag :status="model.enabled ? 'enabled' : 'disabled'" />
      </div>
      <div class="card-actions">
        <ElButton size="small" @click="emit('edit', model)">
          <ElIcon><Edit /></ElIcon>
          编辑
        </ElButton>
        <ElButton
          size="small"
          type="danger"
          :disabled="nonDeletable"
          :title="nonDeletable ? '该模型已有请求历史，请改为停用' : undefined"
          @click="emit('delete', model)"
        >
          <ElIcon><Delete /></ElIcon>
          删除
        </ElButton>
      </div>
    </div>

    <div class="card-body">
      <div class="basic-info">
        <div class="info-item">
          <span class="label">规范名称：</span>
          <code class="value">{{ model.canonical_name }}</code>
        </div>
        <div class="info-item">
          <span class="label">输入价格：</span>
          <span class="value">{{ formatMoney(model.input_price_per_million) }}</span>
        </div>
        <div class="info-item">
          <span class="label">输出价格：</span>
          <span class="value">{{ formatMoney(model.output_price_per_million) }}</span>
        </div>
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

      <div class="routes-section">
        <div class="routes-header">
          <div class="section-title">
            模型路由
            <ElTag size="small" type="info" effect="plain">
              {{ routeStats.enabled }}/{{ routeStats.total }} 启用
            </ElTag>
            <ElTag size="small" type="success" effect="plain">
              {{ routeStats.healthy }}/{{ routeStats.total }} 健康
            </ElTag>
          </div>
          <ElButton
            size="small"
            type="primary"
            plain
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
        <div v-else class="routes-grid">
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
                  {{ protocolName(route.provider_id, route.provider_protocol_id) }}
                </ElTag>
                <span class="provider-name">{{ providerName(route.provider_id) }}</span>
              </div>
              <div class="route-actions">
                <ElButton size="small" text @click="emit('editRoute', route)">
                  <ElIcon><Edit /></ElIcon>
                </ElButton>
                <ElButton
                  size="small"
                  text
                  type="danger"
                  @click="emit('deleteRoute', route)"
                >
                  <ElIcon><Delete /></ElIcon>
                </ElButton>
              </div>
            </div>
            <div class="route-model">{{ route.upstream_model }}</div>
            <div class="route-stats">
              <span class="stat">权重: {{ route.weight }}</span>
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
  opacity: 0.65;
  background: #f1f5f9;
}

.model-card.is-expanded {
  border-color: var(--gateway-brand);
  box-shadow: 0 8px 24px rgb(37 99 235 / 0.15);
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

code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  background: #e2e8f0;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #334155;
}

.aliases-section {
  border-top: 1px solid var(--gateway-border);
  padding-top: 1rem;
}

.section-title {
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--gateway-text);
  margin-bottom: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.7;
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
  opacity: 0.6;
  background: #f1f5f9;
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

  .routes-grid {
    grid-template-columns: 1fr;
  }
}
</style>
