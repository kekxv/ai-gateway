<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDrawer, ElSkeleton, ElSkeletonItem, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-tag.css'

import { getRequestLog } from '@/api/requestLogs'
import type { RequestLogDetail, RequestStatus } from '@/api/types'
import JsonViewer from '@/components/common/JsonViewer.vue'
import { formatDateTime, formatDuration } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  requestId: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const detail = ref<RequestLogDetail | null>(null)
const loading = ref(false)
const error = ref('')
let requestController: AbortController | undefined
let requestGeneration = 0
let mounted = true

const statusLabels: Readonly<Record<RequestStatus, string>> = {
  started: '处理中',
  completed: '已完成',
  failed: '失败',
  client_disconnected: '客户端已断开',
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
  try {
    const loaded = await getRequestLog(requestId, controller.signal)
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
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(96vw, 72rem)"
    destroy-on-close
    @update:model-value="setOpen"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">请求详情</h2>
        <p class="drawer-description">{{ requestId }} · 敏感字段已由服务端脱敏</p>
      </div>
    </template>

    <ElAlert
      v-if="error !== ''"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <ElSkeleton v-else-if="loading" animated :rows="8">
      <template #template><ElSkeletonItem variant="rect" class="detail-skeleton" /></template>
    </ElSkeleton>
    <div v-else-if="detail !== null" class="detail-content">
      <section aria-labelledby="request-metadata-title">
        <div class="metadata-heading">
          <h3 id="request-metadata-title">请求元数据</h3>
          <ElTag effect="light" :type="detail.status === 'completed' ? 'success' : detail.status === 'failed' ? 'danger' : 'info'">
            {{ statusLabels[detail.status] }}
          </ElTag>
        </div>
        <dl class="metadata-grid">
          <div><dt>请求 ID</dt><dd>{{ detail.id }}</dd></div>
          <div><dt>用户 / 密钥</dt><dd>用户 #{{ detail.user_id }} / {{ detail.api_key_id === null ? '无密钥' : `密钥 #${String(detail.api_key_id)}` }}</dd></div>
          <div><dt>模型 / 供应商 / 路由</dt><dd>{{ detail.model_id === null ? '无模型' : `模型 #${String(detail.model_id)}` }} / {{ detail.provider_id === null ? '无供应商' : `供应商 #${String(detail.provider_id)}` }} / {{ detail.model_route_id === null ? '无路由' : `路由 #${String(detail.model_route_id)}` }}</dd></div>
          <div><dt>协议</dt><dd>{{ detail.inbound_protocol }} → {{ detail.outbound_protocol ?? '无出站协议' }}</dd></div>
          <div><dt>传输 / 流式</dt><dd>{{ detail.transport }} / {{ detail.stream ? '是' : '否' }}</dd></div>
          <div><dt>HTTP 状态</dt><dd>{{ detail.http_status ?? '—' }}</dd></div>
          <div><dt>输入 / 输出令牌</dt><dd>{{ detail.prompt_tokens }} / {{ detail.completion_tokens }}</dd></div>
          <div><dt>用量来源</dt><dd>{{ detail.usage_source === 'provider' ? '供应商' : detail.usage_source === 'estimated' ? '估算' : '—' }}</dd></div>
          <div><dt>精确费用</dt><dd class="exact-value">{{ detail.cost }}</dd></div>
          <div><dt>延迟 / 首个令牌</dt><dd>{{ formatDuration(detail.latency_ms) }} / {{ formatDuration(detail.first_token_ms) }}</dd></div>
          <div><dt>错误代码</dt><dd>{{ detail.error_code ?? '—' }}</dd></div>
          <div><dt>创建 / 完成时间</dt><dd>{{ formatDateTime(detail.created_at) }} / {{ formatDateTime(detail.completed_at) }}</dd></div>
        </dl>
      </section>

      <JsonViewer data-test="request-json-section" title="请求 JSON" :value="detail.request_detail" />
      <JsonViewer data-test="response-json-section" title="响应 JSON" :value="detail.response_detail" />
    </div>

    <template #footer>
      <ElButton data-test="close-request-detail" @click="setOpen(false)">关闭</ElButton>
    </template>
  </ElDrawer>
</template>

<style scoped>
.drawer-heading,
.metadata-heading h3 {
  margin: 0;
}

.drawer-description {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}

.detail-skeleton {
  height: 30rem;
}

.detail-content {
  display: grid;
  gap: 1rem;
}

.metadata-heading {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
  margin: 1rem 0 0;
}

.metadata-grid div {
  min-width: 0;
  padding: 0.8rem;
  background: var(--gateway-soft, #f8fafc);
  border-radius: 0.6rem;
}

.metadata-grid dt {
  color: var(--gateway-muted);
  font-size: 0.75rem;
}

.metadata-grid dd {
  margin: 0.25rem 0 0;
  overflow-wrap: anywhere;
}

.exact-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

@media (max-width: 767px) {
  .metadata-grid {
    grid-template-columns: 1fr;
  }
}
</style>
