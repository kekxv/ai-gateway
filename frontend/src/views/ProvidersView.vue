<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Edit, Plus, Refresh, Search, Delete } from '@element-plus/icons-vue'
import {
  ElAlert,
  ElButton,
  ElEmpty,
  ElIcon,
  ElInput,
  ElMessageBox,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
  ElTag,
} from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-tag.css'

import { ApiError } from '@/api/client'
import {
  createProvider,
  deleteProvider,
  listProviders,
  syncProviderModels,
  updateProvider,
} from '@/api/providers'
import type {
  Protocol,
  ProviderCreate,
  ProviderResponse,
  ProviderUpdate,
} from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ProviderFormDrawer from '@/components/providers/ProviderFormDrawer.vue'

type NoticeType = 'success' | 'warning' | 'error'
type ProviderOperation = 'edit' | 'sync' | 'delete'

const providers = ref<ProviderResponse[]>([])
const searchText = ref('')
const loading = ref(true)
const loadError = ref('')
const notice = ref<{ type: NoticeType; text: string } | null>(null)
const drawerOpen = ref(false)
const editingProvider = ref<ProviderResponse | null>(null)
const submitting = ref(false)
const providerOperations = ref(new Map<number, ProviderOperation>())
const nonDeletableIds = ref(new Set<number>())
const deletedIds = new Set<number>()
let requestController: AbortController | undefined
let saveController: AbortController | undefined
const operationControllers = new Set<AbortController>()
let mounted = true
let loadGeneration = 0
let stateRevision = 0
let drawerSessionGeneration = 0
let activeSaveToken: symbol | undefined

const protocolLabels: Readonly<Record<Protocol, string>> = {
  openai: 'OpenAI',
  claude: 'Claude',
  gemini: 'Gemini',
}

const filteredProviders = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase('zh-CN')
  if (query === '') return providers.value
  return providers.value.filter((provider) => {
    const searchable = [
      provider.name,
      ...provider.protocols.flatMap((protocol) => [
        protocol.protocol,
        protocolLabels[protocol.protocol],
        protocol.base_url,
        protocol.websocket_url ?? '',
      ]),
    ]
    return searchable.some((value) => value.toLocaleLowerCase('zh-CN').includes(query))
  })
})

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

async function load(): Promise<void> {
  requestController?.abort()
  const controller = new AbortController()
  requestController = controller
  const generation = ++loadGeneration
  const startingRevision = stateRevision
  loading.value = providers.value.length === 0
  try {
    const loadedProviders = await listProviders(controller.signal)
    if (
      !mounted ||
      controller.signal.aborted ||
      generation !== loadGeneration ||
      startingRevision !== stateRevision
    ) {
      return
    }
    providers.value = loadedProviders.filter((provider) => !deletedIds.has(provider.id))
    loadError.value = ''
  } catch (error: unknown) {
    if (!mounted || controller.signal.aborted || generation !== loadGeneration) return
    loadError.value = errorText(error, '供应商列表加载失败')
  } finally {
    if (mounted && generation === loadGeneration) loading.value = false
  }
}

function openCreate(): void {
  if (submitting.value || drawerOpen.value) return
  drawerSessionGeneration += 1
  editingProvider.value = null
  drawerOpen.value = true
}

function openEdit(provider: ProviderResponse): void {
  if (submitting.value || drawerOpen.value || !beginProviderOperation(provider.id, 'edit')) return
  drawerSessionGeneration += 1
  editingProvider.value = provider
  drawerOpen.value = true
}

function setDrawerOpen(open: boolean): void {
  if (open) return
  if (submitting.value) return
  const providerId = editingProvider.value?.id
  drawerSessionGeneration += 1
  drawerOpen.value = false
  editingProvider.value = null
  if (providerId !== undefined) finishProviderOperation(providerId, 'edit')
}

function replaceProvider(updated: ProviderResponse): void {
  stateRevision += 1
  deletedIds.delete(updated.id)
  const index = providers.value.findIndex((provider) => provider.id === updated.id)
  if (index === -1) providers.value.push(updated)
  else providers.value.splice(index, 1, updated)
}

function beginProviderOperation(providerId: number, operation: ProviderOperation): boolean {
  if (providerOperations.value.has(providerId)) return false
  const next = new Map(providerOperations.value)
  next.set(providerId, operation)
  providerOperations.value = next
  return true
}

function finishProviderOperation(providerId: number, operation: ProviderOperation): void {
  if (providerOperations.value.get(providerId) !== operation) return
  const next = new Map(providerOperations.value)
  next.delete(providerId)
  providerOperations.value = next
}

function operationController(): AbortController {
  const controller = new AbortController()
  operationControllers.add(controller)
  return controller
}

function isCurrentSave(
  controller: AbortController,
  token: symbol,
  session: number,
  providerId: number | undefined,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    activeSaveToken === token &&
    drawerOpen.value &&
    drawerSessionGeneration === session &&
    editingProvider.value?.id === providerId
  )
}

async function saveProvider(payload: ProviderCreate | ProviderUpdate): Promise<void> {
  if (submitting.value || !drawerOpen.value) return
  const provider = editingProvider.value
  const providerId = provider?.id
  const isCreate = provider === null
  const session = drawerSessionGeneration
  const token = Symbol('provider-save')
  const controller = new AbortController()
  saveController?.abort()
  saveController = controller
  activeSaveToken = token
  submitting.value = true
  try {
    const updated =
      providerId === undefined
        ? await createProvider(payload as ProviderCreate, controller.signal)
        : await updateProvider(providerId, payload, controller.signal)
    if (!isCurrentSave(controller, token, session, providerId)) return
    replaceProvider(updated)
    drawerSessionGeneration += 1
    drawerOpen.value = false
    editingProvider.value = null
    if (providerId !== undefined) finishProviderOperation(providerId, 'edit')
    notice.value = {
      type: 'success',
      text: isCreate ? '供应商已创建' : '供应商设置已保存',
    }
  } catch (error: unknown) {
    if (
      mounted &&
      !controller.signal.aborted &&
      activeSaveToken === token &&
      drawerSessionGeneration === session
    ) {
      notice.value = { type: 'error', text: errorText(error, '供应商保存失败') }
    }
  } finally {
    if (activeSaveToken === token) {
      activeSaveToken = undefined
      saveController = undefined
      if (mounted) submitting.value = false
    }
  }
}

async function syncModels(provider: ProviderResponse): Promise<void> {
  if (!beginProviderOperation(provider.id, 'sync')) return
  const controller = operationController()
  try {
    const result = await syncProviderModels(provider.id, controller.signal)
    if (!mounted || controller.signal.aborted) return
    notice.value = {
      type: 'success',
      text: `供应商“${provider.name}”同步完成：发现 ${String(result.discovered_models)} 个，新增模型 ${String(result.created_models)} 个，新增路由 ${String(result.created_routes)} 条，更新路由 ${String(result.updated_routes)} 条，停用路由 ${String(result.disabled_routes)} 条`,
    }
    await load()
  } catch (error: unknown) {
    if (mounted && !controller.signal.aborted) {
      notice.value = { type: 'error', text: errorText(error, '模型同步失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (mounted) finishProviderOperation(provider.id, 'sync')
  }
}

async function removeProvider(provider: ProviderResponse): Promise<void> {
  if (nonDeletableIds.value.has(provider.id)) return
  if (!beginProviderOperation(provider.id, 'delete')) return
  try {
    await ElMessageBox.confirm(
      `确定删除供应商“${provider.name}”吗？此操作无法撤销。`,
      '删除供应商',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    finishProviderOperation(provider.id, 'delete')
    return
  }

  const controller = operationController()
  try {
    await deleteProvider(provider.id, controller.signal)
    if (!mounted || controller.signal.aborted) return
    stateRevision += 1
    deletedIds.add(provider.id)
    providers.value = providers.value.filter((item) => item.id !== provider.id)
    notice.value = { type: 'success', text: `供应商“${provider.name}”已删除` }
  } catch (error: unknown) {
    if (!mounted || controller.signal.aborted) return
    if (error instanceof ApiError && error.code === 'provider_has_history') {
      const next = new Set(nonDeletableIds.value)
      next.add(provider.id)
      nonDeletableIds.value = next
      notice.value = { type: 'warning', text: `${error.message}；请改为停用该供应商。` }
    } else {
      notice.value = { type: 'error', text: errorText(error, '供应商删除失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (mounted) finishProviderOperation(provider.id, 'delete')
  }
}

function formatSyncTime(value: string | null): string {
  if (value === null) return '从未同步'
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

function formatInterval(seconds: number): string {
  if (seconds % 3600 === 0) return `${String(seconds / 3600)} 小时`
  if (seconds % 60 === 0) return `${String(seconds / 60)} 分钟`
  return `${String(seconds)} 秒`
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  drawerSessionGeneration += 1
  requestController?.abort()
  saveController?.abort()
  for (const controller of operationControllers) controller.abort()
  operationControllers.clear()
})
</script>

<template>
  <PageHeader title="供应商管理" description="管理上游服务、协议入口与模型自动同步。">
    <template #actions>
      <ElButton data-test="create-provider" type="primary" @click="openCreate">
        <ElIcon><Plus /></ElIcon>
        新建供应商
      </ElButton>
    </template>
  </PageHeader>

  <ElAlert
    v-if="notice"
    data-test="provider-notice"
    class="notice"
    :type="notice.type"
    :title="notice.text"
    show-icon
    closable
    @close="notice = null"
  />

  <section class="provider-panel page-card" aria-labelledby="provider-list-heading">
    <div class="provider-toolbar">
      <div>
        <h2 id="provider-list-heading">供应商列表</h2>
        <p>共 {{ providers.length }} 个供应商</p>
      </div>
      <ElInput
        v-model="searchText"
        data-test="provider-search"
        class="provider-search"
        clearable
        placeholder="搜索名称、协议或基础地址"
        aria-label="搜索供应商"
      >
        <template #prefix><ElIcon><Search /></ElIcon></template>
      </ElInput>
    </div>

    <div v-if="loading" class="provider-loading" aria-label="正在加载供应商">
      <ElSkeleton v-for="index in 3" :key="index" animated>
        <template #template>
          <ElSkeletonItem variant="rect" class="provider-skeleton" />
        </template>
      </ElSkeleton>
    </div>

    <ElResult
      v-else-if="loadError"
      icon="error"
      title="供应商列表加载失败"
      :sub-title="loadError"
    >
      <template #extra>
        <ElButton type="primary" @click="load">重新加载</ElButton>
      </template>
    </ElResult>

    <div v-else-if="filteredProviders.length > 0" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">状态</th>
            <th scope="col">协议</th>
            <th scope="col">模型同步</th>
            <th scope="col">上次同步</th>
            <th scope="col">同步间隔</th>
            <th scope="col" class="actions-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="provider in filteredProviders" :key="provider.id">
            <td>
              <strong>{{ provider.name }}</strong>
            </td>
            <td>
              <StatusTag :status="provider.enabled ? 'enabled' : 'disabled'" />
            </td>
            <td>
              <div class="protocol-list">
                <ElTag
                  v-for="protocol in provider.protocols"
                  :key="protocol.id"
                  :type="protocol.enabled ? 'primary' : 'info'"
                  effect="plain"
                  :title="protocol.base_url"
                >
                  {{ protocolLabels[protocol.protocol] }}
                </ElTag>
                <span v-if="provider.protocols.length === 0" class="muted">未配置</span>
              </div>
            </td>
            <td>
              <StatusTag
                :status="provider.auto_load_models ? 'healthy' : 'disabled'"
                :label="provider.auto_load_models ? '自动同步' : '手动同步'"
              />
            </td>
            <td>{{ formatSyncTime(provider.last_model_sync_at) }}</td>
            <td>{{ formatInterval(provider.model_sync_interval_seconds) }}</td>
            <td>
              <div class="row-actions">
                <ElButton
                  :data-test="`sync-provider-${String(provider.id)}`"
                  text
                  type="primary"
                  :loading="providerOperations.get(provider.id) === 'sync'"
                  :disabled="providerOperations.has(provider.id)"
                  @click="syncModels(provider)"
                >
                  <ElIcon><Refresh /></ElIcon>
                  同步
                </ElButton>
                <ElButton
                  :data-test="`edit-provider-${String(provider.id)}`"
                  text
                  :disabled="providerOperations.has(provider.id) || drawerOpen"
                  @click="openEdit(provider)"
                >
                  <ElIcon><Edit /></ElIcon>
                  编辑
                </ElButton>
                <ElButton
                  :data-test="`delete-provider-${String(provider.id)}`"
                  text
                  type="danger"
                  :loading="providerOperations.get(provider.id) === 'delete'"
                  :disabled="providerOperations.has(provider.id) || nonDeletableIds.has(provider.id)"
                  :title="
                    nonDeletableIds.has(provider.id)
                      ? '该供应商已有请求历史，请改为停用'
                      : undefined
                  "
                  @click="removeProvider(provider)"
                >
                  <ElIcon><Delete /></ElIcon>
                  删除
                </ElButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ElEmpty
      v-else
      :description="searchText.trim() === '' ? '暂无供应商' : '没有匹配的供应商'"
    />
  </section>

  <ProviderFormDrawer
    :model-value="drawerOpen"
    :provider="editingProvider"
    :submitting="submitting"
    @update:model-value="setDrawerOpen"
    @submit="saveProvider"
  />
</template>

<style scoped>
.notice {
  margin-bottom: 1rem;
}

.provider-panel {
  overflow: hidden;
}

.provider-toolbar {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--gateway-border);
}

.provider-toolbar h2,
.provider-toolbar p {
  margin: 0;
}

.provider-toolbar h2 {
  font-size: 1.1rem;
}

.provider-toolbar p,
.muted {
  margin-top: 0.25rem;
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.provider-search {
  width: min(100%, 24rem);
}

.provider-loading {
  display: grid;
  gap: 0.75rem;
  padding: 1.25rem;
}

.provider-skeleton {
  height: 3.5rem;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 70rem;
  border-collapse: collapse;
}

th,
td {
  padding: 0.95rem 1rem;
  text-align: left;
  vertical-align: middle;
  border-bottom: 1px solid var(--gateway-border);
}

th {
  color: var(--gateway-muted);
  font-size: 0.8rem;
  font-weight: 600;
  background: #f8fafc;
}

tbody tr:last-child td {
  border-bottom: 0;
}

tbody tr:hover {
  background: #f8fafc;
}

.actions-column {
  width: 16rem;
}

.protocol-list,
.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}

.row-actions {
  flex-wrap: nowrap;
}

.row-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

@media (max-width: 640px) {
  .provider-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .provider-search {
    width: 100%;
  }
}
</style>
