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

import {
  listRequestLogs,
  listUserRequestLogs,
  type RequestLogQuery,
} from '@/api/requestLogs'
import { listApiKeys, listOwnApiKeys } from '@/api/apiKeys'
import { listAvailableModels, listModels } from '@/api/models'
import { listProviders } from '@/api/providers'
import type {
  ApiKeyResponse,
  ModelResponse,
  Protocol,
  ProviderResponse,
  RequestLogSummary,
  RequestStatus,
  UserRequestLogSummary,
  UserResponse,
} from '@/api/types'
import { listUsers } from '@/api/users'
import PageHeader from '@/components/common/PageHeader.vue'
import RequestLogDetailDrawer from '@/components/request-logs/RequestLogDetailDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime, formatDuration, formatMoney } from '@/utils/format'

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

const auth = useAuthStore()

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
const logs = ref<Array<RequestLogSummary | UserRequestLogSummary>>([])
const loading = ref(true)
const loadError = ref('')
const pageSize = ref(50)
const currentCursor = ref<string | null>(null)
const nextCursor = ref<string | null>(null)
const cursorStack = ref<Array<string | null>>([])
const detailOpen = ref(false)
const selectedRequestId = ref<string | null>(null)
const users = ref<UserResponse[]>([])
const apiKeys = ref<ApiKeyResponse[]>([])
const models = ref<ModelResponse[]>([])
const providers = ref<ProviderResponse[]>([])
const filterOptionsLoading = ref(true)

let loadController: AbortController | undefined
let filterOptionsController: AbortController | undefined
let loadGeneration = 0
let mounted = true

const statusLabels: Readonly<Record<RequestStatus, string>> = {
  started: '处理中',
  completed: '已完成',
  failed: '失败',
  client_disconnected: '客户端已断开',
}

const protocolLabels: Readonly<Record<Protocol, string>> = {
  openai: 'OpenAI',
  claude: 'Claude',
  gemini: 'Gemini',
}

function statusTagType(status: RequestStatus): 'success' | 'danger' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
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
  if (auth.isAdmin) {
    const userId = optionalInteger(filters.userId)
    if (userId !== undefined) query.userId = userId
  }
  const apiKeyId = optionalInteger(filters.apiKeyId)
  const modelId = optionalInteger(filters.modelId)
  if (apiKeyId !== undefined) query.apiKeyId = apiKeyId
  if (modelId !== undefined) query.modelId = modelId
  if (auth.isAdmin) {
    const providerId = optionalInteger(filters.providerId)
    if (providerId !== undefined) query.providerId = providerId
  }
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
    const response = auth.isAdmin
      ? await listRequestLogs(currentQuery(currentCursor.value), controller.signal)
      : await listUserRequestLogs(currentQuery(currentCursor.value), controller.signal)
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

async function loadFilterOptions(): Promise<void> {
  filterOptionsController?.abort()
  const controller = new AbortController()
  filterOptionsController = controller
  filterOptionsLoading.value = true
  try {
    if (auth.isAdmin) {
      const [loadedUsers, loadedApiKeys, loadedModels, loadedProviders] = await Promise.all([
        listUsers(controller.signal),
        listApiKeys(undefined, controller.signal),
        listModels(controller.signal),
        listProviders(controller.signal),
      ])
      if (!mounted || controller.signal.aborted || filterOptionsController !== controller) return
      users.value = loadedUsers
      apiKeys.value = loadedApiKeys
      models.value = loadedModels
      providers.value = loadedProviders
    } else {
      const [loadedApiKeys, loadedModels] = await Promise.all([
        listOwnApiKeys(controller.signal),
        listAvailableModels(controller.signal),
      ])
      if (!mounted || controller.signal.aborted || filterOptionsController !== controller) return
      apiKeys.value = loadedApiKeys
      models.value = loadedModels
    }
  } catch {
    // The log query remains usable even when optional filter catalogs fail to load.
  } finally {
    if (mounted && filterOptionsController === controller) filterOptionsLoading.value = false
    if (filterOptionsController === controller) filterOptionsController = undefined
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

function apiKeyLabel(name: string | null): string {
  return name ?? '无密钥'
}

function apiKeyOptionLabel(apiKey: ApiKeyResponse): string {
  if (!auth.isAdmin) return apiKey.name
  const owner = users.value.find((user) => user.id === apiKey.user_id)
  return owner === undefined ? apiKey.name : `${apiKey.name} · ${owner.email}`
}

onMounted(() => {
  void load()
  void loadFilterOptions()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  loadController?.abort()
  loadController = undefined
  filterOptionsController?.abort()
  filterOptionsController = undefined
})
</script>

<template>
  <div class="route-page">
    <PageHeader
      title="请求日志"
      :description="auth.isAdmin ? '按审计字段搜索网关请求，并检查服务端已脱敏的请求与响应详情。' : '查看你的网关请求记录与元数据。'"
    >
      <template #actions>
        <ElButton :loading="loading" aria-label="刷新请求日志" @click="load">
          <ElIcon><Refresh /></ElIcon>
          刷新
        </ElButton>
      </template>
    </PageHeader>

    <section class="filter-panel" aria-labelledby="request-log-filter-title">
      <div class="filter-heading">
        <h2 id="request-log-filter-title">筛选</h2>
        <div class="filter-actions">
          <ElButton size="small" @click="clearFilters">清空</ElButton>
          <ElButton size="small" type="primary" @click="applyFilters">
            <ElIcon><Search /></ElIcon>
            查询
          </ElButton>
        </div>
      </div>

      <div class="filter-grid" :class="{ 'filter-grid--compact': !auth.isAdmin }">
        <label>
          <span>请求 ID</span>
          <input v-model="filters.requestId" data-test="log-request-id" type="search" placeholder="输入完整请求 ID" @change="applyFilters">
        </label>
        <label v-if="auth.isAdmin">
          <span>用户</span>
          <select v-model="filters.userId" data-test="log-user-id" :disabled="filterOptionsLoading" @change="applyFilters">
            <option value="">全部用户</option>
            <option v-for="user in users" :key="user.id" :value="user.id">{{ user.email }}</option>
          </select>
        </label>
        <label>
          <span>密钥</span>
          <select v-model="filters.apiKeyId" data-test="log-api-key-id" :disabled="filterOptionsLoading" @change="applyFilters">
            <option value="">全部密钥</option>
            <option v-for="apiKey in apiKeys" :key="apiKey.id" :value="apiKey.id">{{ apiKeyOptionLabel(apiKey) }}</option>
          </select>
        </label>
        <label>
          <span>模型</span>
          <select v-model="filters.modelId" data-test="log-model-id" :disabled="filterOptionsLoading" @change="applyFilters">
            <option value="">全部模型</option>
            <option v-for="model in models" :key="model.id" :value="model.id">{{ model.display_name }}</option>
          </select>
        </label>
        <label v-if="auth.isAdmin">
          <span>供应商</span>
          <select v-model="filters.providerId" data-test="log-provider-id" :disabled="filterOptionsLoading" @change="applyFilters">
            <option value="">全部供应商</option>
            <option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name }}</option>
          </select>
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
              <th v-if="auth.isAdmin">用户 / 密钥</th>
              <th v-else>密钥</th>
              <th v-if="auth.isAdmin">模型 / 供应商 / 上游模型</th>
              <th v-else>模型</th>
              <th>请求信息</th>
              <th>令牌</th>
              <th>{{ auth.isAdmin ? '用户费用 / 成本费用' : '费用' }}</th>
              <th>延迟 / 首个令牌</th>
              <th>错误代码</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" :data-test="`request-log-${log.id}`">
              <td v-if="auth.isAdmin">
                <div class="entity-cell">
                  <strong>{{ (log as RequestLogSummary).user_email }}</strong>
                  <small>{{ apiKeyLabel(log.api_key_name) }}</small>
                </div>
              </td>
              <td v-else>{{ apiKeyLabel(log.api_key_name) }}</td>
              <td>
                <div class="entity-cell">
                  <strong>{{ log.model_name ?? '已删除模型' }}</strong>
                  <template v-if="auth.isAdmin">
                    <span>{{ (log as RequestLogSummary).provider_name ?? '已删除供应商' }}</span>
                    <small>上游：{{ (log as RequestLogSummary).route_upstream_model ?? '已删除路由' }}</small>
                  </template>
                </div>
              </td>
              <td>
                <div class="request-info-tags">
                  <ElTag size="small" effect="plain">
                    {{ protocolLabels[log.inbound_protocol] }} → {{ log.outbound_protocol === null ? '无出站协议' : protocolLabels[log.outbound_protocol] }}
                  </ElTag>
                  <ElTag size="small" effect="plain">{{ log.transport.toUpperCase() }}</ElTag>
                  <ElTag size="small" effect="plain" :type="log.stream ? 'primary' : 'info'">
                    {{ log.stream ? '流式' : '非流式' }}
                  </ElTag>
                  <ElTag size="small" effect="light" :type="statusTagType(log.status)">
                    {{ statusLabels[log.status] }}
                  </ElTag>
                  <ElTag v-if="log.http_status !== null" size="small" effect="plain" :type="log.http_status >= 400 ? 'danger' : 'success'">
                    HTTP {{ log.http_status }}
                  </ElTag>
                </div>
              </td>
              <td>
                <div>{{ log.prompt_tokens }} / {{ log.completion_tokens }}</div>
                <small>缓存 {{ log.cache_read_tokens }} / {{ log.cache_write_tokens }}</small>
              </td>
              <td class="exact-value">
                <div>{{ formatMoney(log.cost) }}</div>
                <small v-if="auth.isAdmin">成本 {{ formatMoney((log as RequestLogSummary).cost_amount ?? '0') }}</small>
              </td>
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
      :hide-sensitive="!auth.isAdmin"
      @update:model-value="setDetailOpen"
    />
  </div>
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
  padding: 0.7rem 0.85rem 0.8rem;
}

.filter-heading,
.list-heading {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.filter-heading h2,
.list-heading h2,
.list-heading p {
  margin: 0;
}

.filter-heading h2,
.list-heading h2 {
  font-size: 1.05rem;
}

.list-heading p {
  margin-top: 0.2rem;
  color: var(--gateway-muted);
  font-size: 0.8rem;
}

.filter-actions,
.pagination {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.5rem 0.65rem;
  margin-top: 0.6rem;
}

.filter-grid--compact {
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
}

.filter-grid label {
  display: grid;
  gap: 0.2rem;
  color: var(--gateway-muted);
  font-size: 0.72rem;
}

.filter-grid input,
.filter-grid select {
  width: 100%;
  min-height: 2rem;
  padding: 0.3rem 0.5rem;
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
  min-width: 94rem;
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

.exact-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.entity-cell {
  display: grid;
  gap: 0.2rem;
}

.entity-cell small {
  color: var(--gateway-muted);
}

.request-info-tags {
  display: flex;
  max-width: 18rem;
  flex-wrap: wrap;
  gap: 0.3rem;
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
