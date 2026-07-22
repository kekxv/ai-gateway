<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Refresh, Search, View } from '@element-plus/icons-vue'
import {
  ElAlert,
  ElButton,
  ElEmpty,
  ElIcon,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
  ElTag,
} from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-tag.css'

import { listRequestLogs, type RequestLogQuery } from '@/api/requestLogs'
import type { Protocol, RequestLogSummary, RequestStatus } from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import RequestLogDetailDrawer from '@/components/request-logs/RequestLogDetailDrawer.vue'
import { formatDateTime, formatDuration } from '@/utils/format'

interface FilterDraft {
  requestId: string
  userId: string | number
  apiKeyId: string | number
  modelId: string | number
  providerId: string | number
  status: '' | RequestStatus
  protocol: '' | Protocol
  createdFrom: string
  createdTo: string
}

const filters = reactive<FilterDraft>({
  requestId: '',
  userId: '',
  apiKeyId: '',
  modelId: '',
  providerId: '',
  status: '',
  protocol: '',
  createdFrom: '',
  createdTo: '',
})
const logs = ref<RequestLogSummary[]>([])
const loading = ref(true)
const loadError = ref('')
const pageSize = ref(50)
const currentCursor = ref<string | null>(null)
const nextCursor = ref<string | null>(null)
const cursorStack = ref<Array<string | null>>([])
const detailOpen = ref(false)
const selectedRequestId = ref<string | null>(null)

let loadController: AbortController | undefined
let loadGeneration = 0
let mounted = true

const statusLabels: Readonly<Record<RequestStatus, string>> = {
  started: '处理中',
  completed: '已完成',
  failed: '失败',
  client_disconnected: '客户端已断开',
}

function optionalInteger(value: string | number): number | undefined {
  const normalized = String(value).trim()
  return normalized === '' ? undefined : Number(normalized)
}

function currentQuery(cursor: string | null): RequestLogQuery {
  const query: RequestLogQuery = {
    requestId: filters.requestId,
    createdFrom: filters.createdFrom,
    createdTo: filters.createdTo,
    pageSize: pageSize.value,
  }
  const userId = optionalInteger(filters.userId)
  const apiKeyId = optionalInteger(filters.apiKeyId)
  const modelId = optionalInteger(filters.modelId)
  const providerId = optionalInteger(filters.providerId)
  if (userId !== undefined) query.userId = userId
  if (apiKeyId !== undefined) query.apiKeyId = apiKeyId
  if (modelId !== undefined) query.modelId = modelId
  if (providerId !== undefined) query.providerId = providerId
  if (filters.status !== '') query.status = filters.status
  if (filters.protocol !== '') query.protocol = filters.protocol
  if (cursor !== null) query.cursor = cursor
  return query
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '请求日志加载失败'
}

function isCurrentLoad(controller: AbortController, generation: number): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    loadController === controller &&
    generation === loadGeneration
  )
}

async function load(): Promise<void> {
  loadController?.abort()
  const controller = new AbortController()
  loadController = controller
  const generation = ++loadGeneration
  loading.value = true
  loadError.value = ''
  try {
    const response = await listRequestLogs(currentQuery(currentCursor.value), controller.signal)
    if (!isCurrentLoad(controller, generation)) return
    logs.value = response.items
    nextCursor.value = response.next_cursor
  } catch (error: unknown) {
    if (isCurrentLoad(controller, generation)) {
      loadError.value = errorText(error)
      logs.value = []
      nextCursor.value = null
    }
  } finally {
    if (isCurrentLoad(controller, generation)) loading.value = false
    if (loadController === controller) loadController = undefined
  }
}

function applyFilters(): void {
  cursorStack.value = []
  currentCursor.value = null
  nextCursor.value = null
  void load()
}

function clearFilters(): void {
  filters.requestId = ''
  filters.userId = ''
  filters.apiKeyId = ''
  filters.modelId = ''
  filters.providerId = ''
  filters.status = ''
  filters.protocol = ''
  filters.createdFrom = ''
  filters.createdTo = ''
  applyFilters()
}

function nextPage(): void {
  if (loading.value || nextCursor.value === null) return
  cursorStack.value.push(currentCursor.value)
  currentCursor.value = nextCursor.value
  nextCursor.value = null
  void load()
}

function previousPage(): void {
  if (loading.value || cursorStack.value.length === 0) return
  currentCursor.value = cursorStack.value.pop() ?? null
  nextCursor.value = null
  void load()
}

function inspect(requestId: string): void {
  selectedRequestId.value = requestId
  detailOpen.value = true
}

function setDetailOpen(open: boolean): void {
  detailOpen.value = open
  if (!open) selectedRequestId.value = null
}

function entityLabel(kind: string, id: number | null): string {
  return id === null ? `无${kind}` : `${kind} #${String(id)}`
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  loadController?.abort()
  loadController = undefined
})
</script>

<template>
  <PageHeader title="请求日志" description="按审计字段搜索网关请求，并检查服务端已脱敏的请求与响应详情。">
    <template #actions>
      <ElButton :loading="loading" aria-label="刷新请求日志" @click="load">
        <ElIcon><Refresh /></ElIcon>
        刷新
      </ElButton>
    </template>
  </PageHeader>

  <section class="filter-panel" aria-labelledby="request-log-filter-title">
    <div class="filter-heading">
      <div>
        <h2 id="request-log-filter-title">搜索条件</h2>
        <p>条件变化后从第一页重新查询。</p>
      </div>
      <div class="filter-actions">
        <ElButton @click="clearFilters">清空条件</ElButton>
        <ElButton type="primary" @click="applyFilters">
          <ElIcon><Search /></ElIcon>
          查询
        </ElButton>
      </div>
    </div>

    <div class="filter-grid">
      <label>
        <span>请求 ID</span>
        <input v-model="filters.requestId" data-test="log-request-id" type="search" placeholder="输入完整请求 ID" @change="applyFilters">
      </label>
      <label>
        <span>用户 ID</span>
        <input v-model="filters.userId" data-test="log-user-id" type="number" min="1" placeholder="例如 2" @change="applyFilters">
      </label>
      <label>
        <span>密钥 ID</span>
        <input v-model="filters.apiKeyId" data-test="log-api-key-id" type="number" min="1" placeholder="例如 31" @change="applyFilters">
      </label>
      <label>
        <span>模型 ID</span>
        <input v-model="filters.modelId" data-test="log-model-id" type="number" min="1" placeholder="例如 21" @change="applyFilters">
      </label>
      <label>
        <span>供应商 ID</span>
        <input v-model="filters.providerId" data-test="log-provider-id" type="number" min="1" placeholder="例如 11" @change="applyFilters">
      </label>
      <label>
        <span>状态</span>
        <select v-model="filters.status" data-test="log-status" @change="applyFilters">
          <option value="">全部状态</option>
          <option value="started">处理中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="client_disconnected">客户端已断开</option>
        </select>
      </label>
      <label>
        <span>协议</span>
        <select v-model="filters.protocol" data-test="log-protocol" @change="applyFilters">
          <option value="">全部协议</option>
          <option value="openai">OpenAI</option>
          <option value="claude">Claude</option>
          <option value="gemini">Gemini</option>
        </select>
      </label>
      <label>
        <span>开始时间</span>
        <input v-model="filters.createdFrom" data-test="log-created-from" type="datetime-local" @change="applyFilters">
      </label>
      <label>
        <span>结束时间</span>
        <input v-model="filters.createdTo" data-test="log-created-to" type="datetime-local" @change="applyFilters">
      </label>
      <label>
        <span>每页条数</span>
        <select v-model.number="pageSize" data-test="log-page-size" @change="applyFilters">
          <option :value="25">25 条</option>
          <option :value="50">50 条</option>
          <option :value="100">100 条</option>
          <option :value="200">200 条</option>
        </select>
      </label>
    </div>
  </section>

  <ElAlert
    v-if="loadError !== ''"
    class="load-alert"
    :title="loadError"
    type="error"
    :closable="false"
    show-icon
  />

  <section class="log-panel" aria-labelledby="request-log-list-title">
    <div class="list-heading">
      <div>
        <h2 id="request-log-list-title">日志列表</h2>
        <p>当前页 {{ logs.length }} 条；列表接口不提供总数。</p>
      </div>
      <div class="pagination" aria-label="请求日志分页">
        <ElButton data-test="logs-previous" :disabled="loading || cursorStack.length === 0" @click="previousPage">上一页</ElButton>
        <span>第 {{ cursorStack.length + 1 }} 页</span>
        <ElButton data-test="logs-next" :disabled="loading || nextCursor === null" @click="nextPage">下一页</ElButton>
      </div>
    </div>

    <ElResult v-if="loadError !== ''" icon="error" title="请求日志加载失败" :sub-title="loadError">
      <template #extra><ElButton type="primary" @click="load">重新加载</ElButton></template>
    </ElResult>
    <ElSkeleton v-else-if="loading" animated>
      <template #template><ElSkeletonItem variant="rect" class="table-skeleton" /></template>
    </ElSkeleton>
    <ElEmpty v-else-if="logs.length === 0" description="暂无匹配的请求日志" />
    <div v-else class="table-scroll">
      <table class="log-table">
        <thead>
          <tr>
            <th>请求 ID</th>
            <th>用户 / 密钥</th>
            <th>模型 / 供应商 / 路由</th>
            <th>入站 → 出站协议</th>
            <th>传输 / 流式</th>
            <th>状态 / HTTP</th>
            <th>令牌</th>
            <th>精确费用</th>
            <th>延迟 / 首个令牌</th>
            <th>错误代码</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id" :data-test="`request-log-${log.id}`">
            <td class="id-cell"><strong>{{ log.id }}</strong></td>
            <td>{{ entityLabel('用户', log.user_id) }} / {{ entityLabel('密钥', log.api_key_id) }}</td>
            <td>{{ entityLabel('模型', log.model_id) }} / {{ entityLabel('供应商', log.provider_id) }} / {{ entityLabel('路由', log.model_route_id) }}</td>
            <td>{{ log.inbound_protocol }} → {{ log.outbound_protocol ?? '无出站协议' }}</td>
            <td>{{ log.transport }} / {{ log.stream ? '是' : '否' }}</td>
            <td>
              <div class="status-cell">
                <ElTag effect="light" :type="log.status === 'completed' ? 'success' : log.status === 'failed' ? 'danger' : 'info'">
                  {{ statusLabels[log.status] }}
                </ElTag>
                <span>{{ log.http_status ?? '—' }}</span>
              </div>
            </td>
            <td>{{ log.prompt_tokens }} / {{ log.completion_tokens }}</td>
            <td class="exact-value">{{ log.cost }}</td>
            <td>{{ formatDuration(log.latency_ms) }} / {{ formatDuration(log.first_token_ms) }}</td>
            <td>{{ log.error_code ?? '—' }}</td>
            <td>{{ formatDateTime(log.created_at) }}</td>
            <td>
              <ElButton :data-test="`inspect-log-${log.id}`" size="small" @click="inspect(log.id)">
                <ElIcon><View /></ElIcon>
                检查详情
              </ElButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination pagination--footer" aria-label="请求日志底部分页">
      <ElButton :disabled="loading || cursorStack.length === 0" @click="previousPage">上一页</ElButton>
      <span>第 {{ cursorStack.length + 1 }} 页</span>
      <ElButton :disabled="loading || nextCursor === null" @click="nextPage">下一页</ElButton>
    </div>
  </section>

  <RequestLogDetailDrawer
    :model-value="detailOpen"
    :request-id="selectedRequestId"
    @update:model-value="setDetailOpen"
  />
</template>

<style scoped>
.filter-panel,
.log-panel {
  overflow: hidden;
  background: var(--gateway-panel);
  border: 1px solid var(--gateway-border);
  border-radius: 0.9rem;
  box-shadow: var(--gateway-shadow);
}

.filter-panel {
  margin-bottom: 1rem;
  padding: 1rem 1.15rem;
}

.filter-heading,
.list-heading {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.filter-heading h2,
.filter-heading p,
.list-heading h2,
.list-heading p {
  margin: 0;
}

.filter-heading h2,
.list-heading h2 {
  font-size: 1.05rem;
}

.filter-heading p,
.list-heading p {
  margin-top: 0.2rem;
  color: var(--gateway-muted);
  font-size: 0.8rem;
}

.filter-actions,
.pagination,
.status-cell {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(9rem, 1fr));
  gap: 0.85rem;
  margin-top: 1rem;
}

.filter-grid label {
  display: grid;
  gap: 0.35rem;
  color: var(--gateway-muted);
  font-size: 0.78rem;
}

.filter-grid input,
.filter-grid select {
  width: 100%;
  min-height: 2.35rem;
  padding: 0.45rem 0.6rem;
  color: var(--gateway-text);
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 0.35rem;
}

.load-alert {
  margin-bottom: 1rem;
}

.list-heading {
  padding: 1rem 1.15rem;
  border-bottom: 1px solid var(--gateway-border);
}

.pagination {
  color: var(--gateway-muted);
  font-size: 0.82rem;
  white-space: nowrap;
}

.pagination--footer {
  justify-content: flex-end;
  padding: 0.85rem 1rem;
  border-top: 1px solid var(--gateway-border);
}

.table-scroll {
  overflow-x: auto;
}

.log-table {
  width: 100%;
  min-width: 138rem;
  border-collapse: collapse;
}

.log-table th,
.log-table td {
  padding: 0.8rem 0.9rem;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--gateway-border);
  white-space: nowrap;
}

.log-table th {
  color: var(--gateway-muted);
  font-size: 0.76rem;
  font-weight: 600;
  background: rgb(248 250 252 / 72%);
}

.log-table tbody tr:last-child td {
  border-bottom: 0;
}

.id-cell,
.exact-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.table-skeleton {
  height: 20rem;
  margin: 1rem;
}

@media (max-width: 1100px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .filter-heading,
  .list-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .filter-actions {
    justify-content: flex-end;
  }

  .filter-grid {
    grid-template-columns: 1fr;
  }

  .pagination {
    justify-content: space-between;
  }
}
</style>
