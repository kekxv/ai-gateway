<script setup lang="ts">
import { defineAsyncComponent, computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  Calendar,
  CircleCheck,
  CircleClose,
  Clock,
  Coin,
  Connection,
  Cpu,
  Document,
  Key,
  Odometer,
  Switch as SwitchIcon,
  Tickets,
  Timer,
  View,
  Warning,
} from '@element-plus/icons-vue'
import { ElButton, ElDrawer, ElIcon, ElSkeleton, ElSkeletonItem, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-icon.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-tag.css'

import { getRequestLog, getUserRequestLog } from '@/api/requestLogs'
import type { Protocol, RequestLogDetail, RequestStatus, UserRequestLogDetail } from '@/api/types'
import JsonViewer from '@/components/common/JsonViewer.vue'
import { formatDateTime, formatDuration, formatMoney } from '@/utils/format'

const ChatView = defineAsyncComponent({
  loader: () => import('./ChatView.vue'),
  delay: 120,
})

type DetailView = 'chat' | 'json'

const props = withDefaults(defineProps<{
  modelValue: boolean
  requestId: string | null
  hideSensitive?: boolean
}>(), {
  hideSensitive: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const detail = ref<RequestLogDetail | UserRequestLogDetail | null>(null)
const loading = ref(false)
const error = ref('')
const detailView = ref<DetailView>('json')
let requestController: AbortController | undefined
let requestGeneration = 0
let mounted = true

const statusLabels: Readonly<Record<RequestStatus, string>> = {
  started: '处理中',
  completed: '已完成',
  failed: '失败',
  client_disconnected: '客户端已断开',
}

function statusTagType(status: RequestStatus): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'client_disconnected') return 'warning'
  return 'info'
}

function httpStatusKind(status: number | null): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === null) return 'neutral'
  if (status >= 200 && status < 300) return 'success'
  if (status >= 400 && status < 500) return 'warning'
  if (status >= 500) return 'danger'
  return 'neutral'
}

function usageSourceLabel(source: string | null): string {
  if (source === 'provider') return '供应商'
  if (source === 'estimated') return '估算'
  return '—'
}

function errorText(value: unknown): string {
  return value instanceof Error ? value.message : '请求详情加载失败'
}

function isCurrentRequest(controller: AbortController, generation: number, requestId: string): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    requestController === controller &&
    generation === requestGeneration &&
    props.modelValue &&
    props.requestId === requestId
  )
}

async function load(requestId: string): Promise<void> {
  requestController?.abort()
  const controller = new AbortController()
  requestController = controller
  const generation = ++requestGeneration
  detail.value = null
  error.value = ''
  loading.value = true
  detailView.value = 'json'
  try {
    const loaded = props.hideSensitive
      ? await getUserRequestLog(requestId, controller.signal)
      : await getRequestLog(requestId, controller.signal)
    if (!isCurrentRequest(controller, generation, requestId) || loaded.id !== requestId) return
    detail.value = loaded
  } catch (value: unknown) {
    if (isCurrentRequest(controller, generation, requestId)) error.value = errorText(value)
  } finally {
    if (isCurrentRequest(controller, generation, requestId)) loading.value = false
    if (requestController === controller) requestController = undefined
  }
}

function clearDetail(): void {
  requestGeneration += 1
  requestController?.abort()
  requestController = undefined
  detail.value = null
  error.value = ''
  loading.value = false
}

function setOpen(open: boolean): void {
  if (!open) clearDetail()
  emit('update:modelValue', open)
}

watch(
  () => [props.modelValue, props.requestId] as const,
  ([open, requestId]) => {
    if (open && requestId !== null) void load(requestId)
    else clearDetail()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  mounted = false
  clearDetail()
})

function isRequestLogDetail(value: RequestLogDetail | UserRequestLogDetail): value is RequestLogDetail {
  return 'request_detail' in value
}

const canShowChatView = computed(() => {
  return !props.hideSensitive && detail.value !== null && isRequestLogDetail(detail.value)
})

const inboundProtocol = computed<Protocol>(() => {
  if (detail.value !== null && isRequestLogDetail(detail.value)) {
    return detail.value.inbound_protocol
  }
  return 'openai'
})

function apiKeyLabel(name: string | null): string {
  return name ?? '无密钥'
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(96vw, 72rem)"
    class="request-detail-drawer"
    destroy-on-close
    @update:model-value="setOpen"
  >
    <template #header>
      <div v-if="detail !== null" class="drawer-header">
        <div class="header-identity">
          <div class="header-icon" :class="`status-${detail.status}`">
            <ElIcon :size="22">
              <CircleCheck v-if="detail.status === 'completed'" />
              <CircleClose v-else-if="detail.status === 'failed'" />
              <Warning v-else-if="detail.status === 'client_disconnected'" />
              <Clock v-else />
            </ElIcon>
          </div>
          <div class="header-text">
            <div class="header-title-row">
              <h2 class="drawer-heading">请求详情</h2>
              <ElTag
                :type="statusTagType(detail.status)"
                effect="light"
                round
                size="small"
              >
                {{ statusLabels[detail.status] }}
              </ElTag>
              <ElTag
                v-if="detail.http_status != null"
                :type="httpStatusKind(detail.http_status) === 'success' ? 'success' : httpStatusKind(detail.http_status) === 'danger' ? 'danger' : httpStatusKind(detail.http_status) === 'warning' ? 'warning' : 'info'"
                effect="plain"
                round
                size="small"
                class="http-tag"
              >
                HTTP {{ detail.http_status }}
              </ElTag>
            </div>
            <p class="drawer-description">
              <span class="request-id" :title="detail.id">{{ detail.id }}</span>
              <span v-if="!hideSensitive" class="description-sep">·</span>
              <span v-if="!hideSensitive" class="description-meta">
                {{ (detail as RequestLogDetail).user_email ?? '—' }}
              </span>
              <span v-if="!hideSensitive" class="description-sep">·</span>
              <span v-if="!hideSensitive" class="description-muted">敏感字段已由服务端脱敏</span>
            </p>
          </div>
        </div>
      </div>
      <div v-else>
        <h2 class="drawer-heading">请求详情</h2>
        <p v-if="hideSensitive" class="drawer-description">{{ requestId }}</p>
        <p v-else class="drawer-description">{{ requestId }} · 敏感字段已由服务端脱敏</p>
      </div>
    </template>

    <div v-if="error !== ''" class="error-banner">
      <ElIcon><Warning /></ElIcon>
      <span>{{ error }}</span>
    </div>
    <ElSkeleton v-else-if="loading" animated :rows="10">
      <template #template><ElSkeletonItem variant="rect" class="detail-skeleton" /></template>
    </ElSkeleton>
    <div v-else-if="detail !== null" class="detail-content">

      <!-- Hero cards: Model + Key Metrics -->
      <section class="hero-section">
        <div class="hero-card hero-model">
          <div class="hero-label">
            <ElIcon><Cpu /></ElIcon>
            模型
          </div>
          <div class="hero-value hero-model-name">{{ detail.model_name ?? '已删除模型' }}</div>
          <div class="hero-model-identities">
            <span>调用：{{ detail.requested_model ?? '—' }}</span>
            <span>实际：{{ detail.resolved_model ?? '—' }}</span>
          </div>
          <div v-if="!hideSensitive" class="hero-sub">
            <span>{{ (detail as RequestLogDetail).provider_name ?? '已删除供应商' }}</span>
            <span class="hero-sep">·</span>
            <span>{{ (detail as RequestLogDetail).route_upstream_model ?? '已删除路由' }}</span>
          </div>
        </div>

        <div class="metric-card" title="首个令牌响应时间">
          <div class="metric-icon metric-latency">
            <ElIcon><Timer /></ElIcon>
          </div>
          <div class="metric-body">
            <div class="metric-label">首个令牌</div>
            <div class="metric-value">{{ formatDuration(detail.first_token_ms) }}</div>
          </div>
        </div>

        <div class="metric-card" title="请求总延迟">
          <div class="metric-icon metric-total">
            <ElIcon><Odometer /></ElIcon>
          </div>
          <div class="metric-body">
            <div class="metric-label">总延迟</div>
            <div class="metric-value">{{ formatDuration(detail.latency_ms) }}</div>
          </div>
        </div>

        <div class="metric-card" title="用户侧费用">
          <div class="metric-icon metric-cost">
            <ElIcon><Coin /></ElIcon>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ hideSensitive ? '费用' : '用户费用' }}</div>
            <div class="metric-value metric-money">{{ formatMoney(detail.cost) }}</div>
          </div>
        </div>
      </section>

      <!-- Tokens & Cache -->
      <section class="info-section">
        <div class="section-header">
          <ElIcon><Tickets /></ElIcon>
          <h3>令牌用量</h3>
        </div>
        <div class="token-grid">
          <div class="token-card">
            <div class="token-row">
              <span class="token-label">输入令牌</span>
              <span class="token-value">{{ detail.prompt_tokens }}</span>
            </div>
            <div class="token-row">
              <span class="token-label">输出令牌</span>
              <span class="token-value">{{ detail.completion_tokens }}</span>
            </div>
          </div>
          <div class="token-card">
            <div class="token-row">
              <span class="token-label">缓存读取</span>
              <span class="token-value">{{ detail.cache_read_tokens }}</span>
            </div>
            <div class="token-row">
              <span class="token-label">缓存写入</span>
              <span class="token-value">{{ detail.cache_write_tokens }}</span>
            </div>
          </div>
          <div class="token-card token-summary">
            <div class="token-row">
              <span class="token-label">用量来源</span>
              <span class="token-value">{{ usageSourceLabel(detail.usage_source) }}</span>
            </div>
            <div v-if="!hideSensitive" class="token-row">
              <span class="token-label">成本费用</span>
              <span class="token-value token-money">{{ formatMoney((detail as RequestLogDetail).cost_amount ?? '0') }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Routing / Protocol -->
      <section class="info-section">
        <div class="section-header">
          <ElIcon><Connection /></ElIcon>
          <h3>路由与协议</h3>
        </div>
        <dl class="kv-grid">
          <div class="kv-item">
            <dt>入站协议</dt>
            <dd><ElTag size="small" effect="plain" round>{{ detail.inbound_protocol }}</ElTag></dd>
          </div>
          <div class="kv-item">
            <dt>出站协议</dt>
            <dd>
              <ElTag v-if="detail.outbound_protocol" size="small" effect="plain" round>{{ detail.outbound_protocol }}</ElTag>
              <span v-else class="muted-value">无</span>
            </dd>
          </div>
          <div class="kv-item">
            <dt>传输方式</dt>
            <dd>{{ detail.transport }}</dd>
          </div>
          <div class="kv-item">
            <dt>流式响应</dt>
            <dd>
              <ElTag :type="detail.stream ? 'success' : 'info'" size="small" effect="light" round>
                {{ detail.stream ? '是' : '否' }}
              </ElTag>
            </dd>
          </div>
          <div class="kv-item">
            <dt>错误代码</dt>
            <dd>
              <ElTag v-if="detail.error_code" type="danger" size="small" effect="plain" round>
                {{ detail.error_code }}
              </ElTag>
              <span v-else class="muted-value">—</span>
            </dd>
          </div>
          <div class="kv-item">
            <dt>密钥</dt>
            <dd>
              <ElIcon class="kv-icon"><Key /></ElIcon>
              {{ apiKeyLabel(detail.api_key_name) }}
            </dd>
          </div>
        </dl>
      </section>

      <!-- Timestamps -->
      <section class="info-section">
        <div class="section-header">
          <ElIcon><Calendar /></ElIcon>
          <h3>时间</h3>
        </div>
        <div class="time-row">
          <div class="time-item">
            <div class="time-label">创建时间</div>
            <div class="time-value">{{ formatDateTime(detail.created_at) }}</div>
          </div>
          <div class="time-arrow">
            <ElIcon><SwitchIcon /></ElIcon>
          </div>
          <div class="time-item">
            <div class="time-label">完成时间</div>
            <div class="time-value">{{ formatDateTime(detail.completed_at) }}</div>
          </div>
        </div>
      </section>

      <!-- Conversation / JSON viewer -->
      <template v-if="canShowChatView">
        <section class="info-section payload-section">
          <div class="section-header">
            <ElIcon><View /></ElIcon>
            <h3>对话内容</h3>
            <div class="view-switcher">
              <button
                type="button"
                :class="['view-btn', { active: detailView === 'chat' }]"
                @click="detailView = 'chat'"
              >
                <ElIcon><Connection /></ElIcon>
                对话视图
              </button>
              <button
                type="button"
                :class="['view-btn', { active: detailView === 'json' }]"
                @click="detailView = 'json'"
              >
                <ElIcon><Document /></ElIcon>
                原始 JSON
              </button>
            </div>
          </div>
          <div class="payload-content">
            <ChatView
              v-if="detailView === 'chat'"
              :request-detail="(detail as RequestLogDetail).request_detail"
              :response-detail="(detail as RequestLogDetail).response_detail"
              :protocol="inboundProtocol"
            />
            <template v-else>
              <JsonViewer data-test="request-json-section" title="请求 JSON" :value="(detail as RequestLogDetail).request_detail" />
              <JsonViewer data-test="response-json-section" title="响应 JSON" :value="(detail as RequestLogDetail).response_detail" />
            </template>
          </div>
        </section>
      </template>
      <template v-else-if="!hideSensitive && isRequestLogDetail(detail)">
        <JsonViewer data-test="request-json-section" title="请求 JSON" :value="detail.request_detail" />
        <JsonViewer data-test="response-json-section" title="响应 JSON" :value="detail.response_detail" />
      </template>
    </div>

    <template #footer>
      <ElButton data-test="close-request-detail" @click="setOpen(false)">关闭</ElButton>
    </template>
  </ElDrawer>
</template>

<style scoped>
/* Header */
.drawer-heading {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--gateway-text);
}

.drawer-description {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.85rem;
  overflow-wrap: anywhere;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.description-sep {
  color: var(--gateway-border);
}

.description-meta {
  color: var(--gateway-muted);
}

.description-muted {
  color: var(--gateway-muted);
  font-style: italic;
}

.request-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  color: var(--gateway-muted);
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
}

.header-identity {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  min-width: 0;
  flex: 1;
}

.header-icon {
  flex-shrink: 0;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #64748b, #475569);
  box-shadow: 0 2px 6px rgb(0 0 0 / 0.12);
}

.header-icon.status-completed {
  background: linear-gradient(135deg, #10b981, #059669);
}

.header-icon.status-failed {
  background: linear-gradient(135deg, #ef4444, #dc2626);
}

.header-icon.status-started {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.header-icon.status-client_disconnected {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.header-text {
  min-width: 0;
  flex: 1;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.http-tag {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* Skeleton */
.detail-skeleton {
  height: 30rem;
}

/* Main content */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.8rem 1rem;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.6rem;
  font-size: 0.9rem;
}

/* Hero section */
.hero-section {
  display: grid;
  grid-template-columns: minmax(0, 2fr) repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
}

.hero-card {
  padding: 1.1rem 1.25rem;
  border-radius: 0.9rem;
  border: 1px solid var(--gateway-border);
  background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
}

.hero-model {
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
  border-color: #dbeafe;
}

.hero-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--gateway-muted);
  font-size: 0.78rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.6rem;
}

.hero-value {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--gateway-text);
  overflow-wrap: anywhere;
}

.hero-model-name {
  font-size: 1.25rem;
  background: linear-gradient(135deg, #1d4ed8, #1e40af);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-model-identities {
  display: grid;
  gap: 0.2rem;
  margin-top: 0.4rem;
  color: var(--gateway-muted);
  font-size: 0.82rem;
}

.hero-sub {
  margin-top: 0.4rem;
  color: var(--gateway-muted);
  font-size: 0.82rem;
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.hero-sep {
  color: var(--gateway-border);
}

/* Metric cards */
.metric-card {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 1rem 1.1rem;
  border-radius: 0.9rem;
  border: 1px solid var(--gateway-border);
  background: #ffffff;
  transition: transform 150ms ease, box-shadow 150ms ease;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--gateway-shadow-md);
}

.metric-icon {
  flex-shrink: 0;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.65rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.15rem;
}

.metric-latency {
  background: #fef3c7;
  color: #b45309;
}

.metric-total {
  background: #ede9fe;
  color: #7c3aed;
}

.metric-cost {
  background: #dcfce7;
  color: #15803d;
}

.metric-body {
  min-width: 0;
  flex: 1;
}

.metric-label {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  font-weight: 500;
}

.metric-value {
  margin-top: 0.2rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--gateway-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}

.metric-money {
  color: #15803d;
}

/* Info sections */
.info-section {
  padding: 1.1rem 1.25rem;
  border-radius: 0.9rem;
  border: 1px solid var(--gateway-border);
  background: #ffffff;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.9rem;
  color: var(--gateway-text);
}

.section-header h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  flex: 1;
}

.section-header > .el-icon {
  color: var(--gateway-brand);
  font-size: 1.05rem;
}

/* Token grid */
.token-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.token-card {
  padding: 0.85rem 1rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 0.7rem;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.token-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.token-label {
  color: var(--gateway-muted);
  font-size: 0.82rem;
}

.token-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 600;
  color: var(--gateway-text);
  font-size: 0.95rem;
}

.token-money {
  color: #15803d;
}

/* KV grid */
.kv-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
  margin: 0;
}

.kv-item {
  padding: 0.65rem 0.85rem;
  background: #f8fafc;
  border-radius: 0.6rem;
  min-width: 0;
}

.kv-item dt {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  font-weight: 500;
  margin-bottom: 0.3rem;
}

.kv-item dd {
  margin: 0;
  color: var(--gateway-text);
  font-size: 0.9rem;
  overflow-wrap: anywhere;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.kv-icon {
  color: var(--gateway-muted);
  font-size: 0.9rem;
}

.muted-value {
  color: var(--gateway-muted);
}

/* Time row */
.time-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 1rem;
  align-items: center;
}

.time-item {
  padding: 0.85rem 1rem;
  background: #f8fafc;
  border-radius: 0.7rem;
}

.time-label {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  font-weight: 500;
  margin-bottom: 0.3rem;
}

.time-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.88rem;
  color: var(--gateway-text);
  overflow-wrap: anywhere;
}

.time-arrow {
  color: var(--gateway-muted);
  font-size: 1.1rem;
}

/* Payload / view switcher */
.payload-section {
  padding: 0;
  overflow: hidden;
}

.payload-section .section-header {
  padding: 1rem 1.25rem;
  margin-bottom: 0;
  border-bottom: 1px solid var(--gateway-border);
}

.view-switcher {
  display: flex;
  background: #f1f5f9;
  border-radius: 0.5rem;
  padding: 0.2rem;
  gap: 0.2rem;
}

.view-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  border: none;
  background: transparent;
  color: var(--gateway-muted);
  font-size: 0.82rem;
  font-weight: 500;
  border-radius: 0.35rem;
  cursor: pointer;
  transition: all 150ms ease;
}

.view-btn:hover {
  color: var(--gateway-text);
}

.view-btn.active {
  background: #ffffff;
  color: var(--gateway-brand);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.06);
}

.payload-content {
  padding: 1rem 1.25rem;
}

.payload-content :deep(.json-section) {
  border: none;
  margin-bottom: 0.75rem;
}

.payload-content :deep(.json-section:last-child) {
  margin-bottom: 0;
}

/* Responsive */
@media (max-width: 900px) {
  .hero-section {
    grid-template-columns: 1fr 1fr;
  }

  .hero-model {
    grid-column: 1 / -1;
  }

  .token-grid,
  .kv-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .hero-section {
    grid-template-columns: 1fr;
  }

  .time-row {
    grid-template-columns: 1fr;
  }

  .time-arrow {
    transform: rotate(90deg);
    justify-self: center;
  }

  .header-icon {
    width: 2.25rem;
    height: 2.25rem;
  }
}
</style>
