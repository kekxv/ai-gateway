<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElEmpty,
  ElIcon,
  ElInput,
  ElMessageBox,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
} from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'

import { ApiError } from '@/api/client'
import { exportCatalog, importCatalog } from '@/api/configuration'
import { listModels } from '@/api/models'
import {
  createProvider,
  deleteProvider,
  getProvider,
  listProviders,
  syncProviderModels,
  updateProvider,
} from '@/api/providers'
import type {
  ModelResponse,
  Protocol,
  ProviderCreate,
  ProviderResponse,
  ProviderUpdate,
} from '@/api/types'
import { buildDeepSeekHarnessFiles } from '@/lib/deepseekHarness'
import PageHeader from '@/components/common/PageHeader.vue'
import ResourceStatusGroup from '@/components/common/ResourceStatusGroup.vue'
import ProviderFormDrawer from '@/components/providers/ProviderFormDrawer.vue'
import ModelSyncDialog from '@/components/providers/ModelSyncDialog.vue'
import ProviderCard from '@/components/providers/ProviderCard.vue'

type NoticeType = 'success' | 'warning' | 'error'
type ProviderOperation = 'edit' | 'sync' | 'delete' | 'toggle'

interface ProviderSyncSession {
  token: symbol
  provider: ProviderResponse
  controller?: AbortController
  submitting: boolean
}

const providers = ref<ProviderResponse[]>([])
const searchText = ref('')
const loading = ref(true)
const loadError = ref('')
const notice = ref<{ type: NoticeType; text: string } | null>(null)
const drawerOpen = ref(false)
const editingProvider = ref<ProviderResponse | null>(null)
const submitting = ref(false)
const catalogExporting = ref(false)
const catalogImporting = ref(false)
const catalogFileInput = ref<HTMLInputElement | null>(null)
const harnessDialogOpen = ref(false)
const harnessProviderId = ref('ai-gateway')
const harnessDisplayName = ref('AI Gateway')
const harnessApi = ref<'openai-responses' | 'openai-completions'>('openai-responses')
const harnessBaseUrl = ref(`${window.location.origin}/v1`)
const harnessApiKeyEnv = ref('AI_GATEWAY_API_KEY')
const harnessApiKey = ref('')
const harnessDefaultModel = ref('')
const harnessModels = ref<ModelResponse[]>([])
const harnessLoadingModels = ref(false)
const harnessModelLoadError = ref('')
const providerOperations = ref(new Map<number, ProviderOperation>())
const nonDeletableIds = ref(new Set<number>())
const deletedIds = new Set<number>()
const syncSession = shallowRef<ProviderSyncSession | null>(null)
const syncDialogOpen = computed(() => syncSession.value !== null)
const syncTargetProvider = computed(() => syncSession.value?.provider ?? null)
const syncSubmitting = computed(() => syncSession.value?.submitting === true)
const catalogOperationActive = computed(() => catalogExporting.value || catalogImporting.value)
const harnessFiles = computed(() => buildDeepSeekHarnessFiles({
  providerId: harnessProviderId.value.trim(),
  displayName: harnessDisplayName.value.trim(),
  api: harnessApi.value,
  baseUrl: harnessBaseUrl.value.trim(),
  apiKeyEnv: harnessApiKeyEnv.value.trim(),
  apiKey: harnessApiKey.value,
  defaultModel: harnessDefaultModel.value.trim(),
  models: harnessModels.value.map((model) => ({
    canonical_name: model.canonical_name,
    enabled: model.enabled,
    ...(model.model_types === undefined ? {} : { model_types: model.model_types }),
    ...(model.model_type === undefined ? {} : { model_type: model.model_type }),
  })),
}))
const harnessEnabledModelNames = computed(() => new Set(
  harnessModels.value
    .filter((model) => model.enabled)
    .map((model) => model.canonical_name),
))
const harnessReady = computed(() => !harnessLoadingModels.value && harnessModelLoadError.value === '' && [
  harnessProviderId.value,
  harnessDisplayName.value,
  harnessBaseUrl.value,
  harnessApiKeyEnv.value,
  harnessApiKey.value,
  harnessDefaultModel.value,
].every((value) => value.trim() !== '') &&
  harnessEnabledModelNames.value.has(harnessDefaultModel.value.trim()))
let requestController: AbortController | undefined
let saveController: AbortController | undefined
const operationControllers = new Set<AbortController>()
let mounted = true
let loadGeneration = 0
let harnessLoadGeneration = 0
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

const enabledProviders = computed(() => filteredProviders.value.filter((provider) => provider.enabled))
const disabledProviders = computed(() =>
  filteredProviders.value.filter((provider) => !provider.enabled),
)

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function downloadCatalog(blob: Blob): void {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = 'ai-gateway-catalog-v1.json'
  anchor.rel = 'noopener'
  document.body.append(anchor)
  try {
    anchor.click()
  } finally {
    anchor.remove()
    URL.revokeObjectURL(objectUrl)
  }
}

async function loadHarnessModels(): Promise<void> {
  const generation = ++harnessLoadGeneration
  const previousDefaultModel = harnessDefaultModel.value
  harnessLoadingModels.value = true
  harnessModelLoadError.value = ''
  harnessModels.value = []
  harnessDefaultModel.value = ''
  try {
    const models = await listModels()
    if (!mounted || generation !== harnessLoadGeneration || !harnessDialogOpen.value) return
    harnessModels.value = models
    if (models.some((model) => model.enabled && model.canonical_name === previousDefaultModel)) {
      harnessDefaultModel.value = previousDefaultModel
    }
  } catch (error: unknown) {
    if (!mounted || generation !== harnessLoadGeneration || !harnessDialogOpen.value) return
    harnessModelLoadError.value = errorText(error, '模型列表加载失败')
  } finally {
    if (mounted && generation === harnessLoadGeneration) harnessLoadingModels.value = false
  }
}

function openHarnessDialog(): void {
  harnessDialogOpen.value = true
  void loadHarnessModels()
}

function closeHarnessDialog(): void {
  harnessLoadGeneration += 1
  harnessApiKey.value = ''
  harnessDefaultModel.value = ''
  harnessModels.value = []
  harnessModelLoadError.value = ''
  harnessLoadingModels.value = false
  harnessDialogOpen.value = false
}

async function copyHarnessFile(content: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(content)
    notice.value = { type: 'success', text: '配置已复制到剪贴板。' }
  } catch {
    notice.value = { type: 'error', text: '复制失败，请手动复制配置内容。' }
  }
}

function downloadHarnessFile(filename: string, content: string): void {
  let objectUrl: string | null = null
  let anchor: HTMLAnchorElement | null = null
  try {
    objectUrl = URL.createObjectURL(new Blob([content], { type: 'text/yaml;charset=utf-8' }))
    anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = filename
    anchor.rel = 'noopener'
    document.body.append(anchor)
    anchor.click()
  } finally {
    anchor?.remove()
    if (objectUrl !== null) URL.revokeObjectURL(objectUrl)
  }
}

function fileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => {
      reject(new Error('文件读取失败'))
    }
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result)
      else reject(new Error('文件读取失败'))
    }
    reader.readAsText(file)
  })
}

async function exportCatalogBackup(): Promise<void> {
  if (catalogOperationActive.value) return
  try {
    await ElMessageBox.confirm(
      '此备份可能包含上游 API 密钥和自定义请求头。请妥善保管下载文件。',
      '导出目录备份',
      { confirmButtonText: '导出包含密钥的备份', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  catalogExporting.value = true
  try {
    downloadCatalog(await exportCatalog(true))
    notice.value = { type: 'success', text: '目录备份下载已开始，请妥善保管其中的密钥。' }
  } catch (error: unknown) {
    notice.value = { type: 'error', text: errorText(error, '目录备份导出失败') }
  } finally {
    catalogExporting.value = false
  }
}

function chooseCatalogImportFile(): void {
  if (catalogOperationActive.value) return
  catalogFileInput.value?.click()
}

async function importCatalogFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  try {
    if (file === undefined || catalogOperationActive.value) return
    let bundleText: string
    try {
      bundleText = await fileText(file)
      JSON.parse(bundleText) as unknown
    } catch {
      notice.value = { type: 'error', text: '目录文件 JSON 格式不正确，未发送导入请求。' }
      return
    }

    try {
      await ElMessageBox.confirm(
        '导入会按名称合并目录中的供应商、模型、别名和路由，且不会删除未包含的现有资源。是否继续？',
        '合并目录配置',
        { confirmButtonText: '确认合并', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }

    catalogImporting.value = true
    const result = await importCatalog(bundleText)
    await load()
    notice.value = {
      type: 'success',
      text: `目录合并完成：新增供应商 ${String(result.providers_created)} 个，更新供应商 ${String(result.providers_updated)} 个；新增模型 ${String(result.models_created)} 个，更新模型 ${String(result.models_updated)} 个；新增路由 ${String(result.routes_created)} 条，更新路由 ${String(result.routes_updated)} 条。`,
    }
  } catch (error: unknown) {
    notice.value = { type: 'error', text: errorText(error, '目录导入失败') }
  } finally {
    input.value = ''
    catalogImporting.value = false
  }
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
    if (
      !mounted ||
      controller.signal.aborted ||
      generation !== loadGeneration ||
      startingRevision !== stateRevision
    ) {
      return
    }
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

function isCurrentProviderOperation(
  controller: AbortController,
  providerId: number,
  operation: ProviderOperation,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    providerOperations.value.get(providerId) === operation
  )
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
    if (providerId !== undefined && updated.id !== providerId) {
      throw new Error('供应商更新响应供应商不匹配')
    }
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

function openSyncDialog(provider: ProviderResponse): void {
  if (syncSession.value !== null) return
  if (!beginProviderOperation(provider.id, 'sync')) return
  syncSession.value = {
    token: Symbol('provider-sync'),
    provider,
    submitting: false,
  }
}

function setSyncDialogOpen(open: boolean): void {
  if (open) return
  const session = syncSession.value
  if (session === null || session.submitting) return
  syncSession.value = null
  finishProviderOperation(session.provider.id, 'sync')
}

function isCurrentSyncSession(session: ProviderSyncSession): boolean {
  return (
    mounted &&
    session.controller?.signal.aborted === false &&
    syncSession.value?.token === session.token &&
    syncSession.value.controller === session.controller &&
    syncSession.value.submitting
  )
}

async function confirmSyncModels(models: string[]): Promise<void> {
  const pendingSession = syncSession.value
  if (pendingSession === null || pendingSession.submitting) return
  const controller = operationController()
  const session: ProviderSyncSession = {
    ...pendingSession,
    controller,
    submitting: true,
  }
  syncSession.value = session
  const provider = session.provider
  try {
    const result = await syncProviderModels(provider.id, models, controller.signal)
    if (!isCurrentSyncSession(session)) return
    if (result.provider_id !== provider.id) {
      throw new Error('模型同步响应供应商不匹配')
    }
    const refreshed = await getProvider(provider.id, controller.signal)
    if (!isCurrentSyncSession(session)) return
    if (refreshed.id !== provider.id) {
      throw new Error('供应商刷新响应供应商不匹配')
    }
    replaceProvider(refreshed)
    notice.value = {
      type: 'success',
      text: `供应商”${provider.name}”同步完成：发现 ${String(result.discovered_models)} 个，新增模型 ${String(result.created_models)} 个，新增路由 ${String(result.created_routes)} 条，更新路由 ${String(result.updated_routes)} 条，停用路由 ${String(result.disabled_routes)} 条`,
    }
  } catch (error: unknown) {
    if (isCurrentSyncSession(session)) {
      notice.value = { type: 'error', text: errorText(error, '模型同步失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentSyncSession(session)) {
      syncSession.value = null
      finishProviderOperation(provider.id, 'sync')
    }
  }
}

async function removeProvider(provider: ProviderResponse): Promise<void> {
  if (nonDeletableIds.value.has(provider.id)) return
  if (!beginProviderOperation(provider.id, 'delete')) return
  const controller = operationController()
  try {
    await ElMessageBox.confirm(
      `确定删除供应商“${provider.name}”吗？此操作无法撤销。`,
      '删除供应商',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    operationControllers.delete(controller)
    if (isCurrentProviderOperation(controller, provider.id, 'delete')) {
      finishProviderOperation(provider.id, 'delete')
    }
    return
  }
  if (!isCurrentProviderOperation(controller, provider.id, 'delete')) {
    operationControllers.delete(controller)
    return
  }

  try {
    await deleteProvider(provider.id, controller.signal)
    if (!isCurrentProviderOperation(controller, provider.id, 'delete')) return
    stateRevision += 1
    deletedIds.add(provider.id)
    providers.value = providers.value.filter((item) => item.id !== provider.id)
    notice.value = { type: 'success', text: `供应商“${provider.name}”已删除` }
  } catch (error: unknown) {
    if (!isCurrentProviderOperation(controller, provider.id, 'delete')) return
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
    if (isCurrentProviderOperation(controller, provider.id, 'delete')) {
      finishProviderOperation(provider.id, 'delete')
    }
  }
}

async function toggleProvider(provider: ProviderResponse): Promise<void> {
  if (!beginProviderOperation(provider.id, 'toggle')) return
  const controller = operationController()
  try {
    const updated = await updateProvider(provider.id, { enabled: !provider.enabled }, controller.signal)
    if (updated.id !== provider.id || !isCurrentProviderOperation(controller, provider.id, 'toggle')) {
      return
    }
    replaceProvider(updated)
    notice.value = {
      type: 'success',
      text: `供应商“${updated.name}”已${updated.enabled ? '启用' : '停用'}`,
    }
  } catch (error: unknown) {
    if (isCurrentProviderOperation(controller, provider.id, 'toggle')) {
      notice.value = { type: 'error', text: errorText(error, '供应商状态更新失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentProviderOperation(controller, provider.id, 'toggle')) {
      finishProviderOperation(provider.id, 'toggle')
    }
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  harnessLoadGeneration += 1
  drawerSessionGeneration += 1
  requestController?.abort()
  saveController?.abort()
  for (const controller of operationControllers) controller.abort()
  operationControllers.clear()
})
</script>

<template>
  <div class="route-page">
    <PageHeader title="供应商管理" description="管理上游服务、协议入口与模型自动同步。">
      <template #actions>
        <input
          ref="catalogFileInput"
          data-test="import-catalog-input"
          class="catalog-file-input"
          type="file"
          accept="application/json,.json"
          @change="importCatalogFile"
        />
        <ElButton
          data-test="import-catalog"
          :loading="catalogImporting"
          :disabled="catalogOperationActive"
          @click="chooseCatalogImportFile"
        >
          导入目录
        </ElButton>
        <ElButton
          data-test="export-catalog"
          :loading="catalogExporting"
          :disabled="catalogOperationActive"
          @click="exportCatalogBackup"
        >
          导出备份
        </ElButton>
        <ElButton data-test="generate-deepseek-harness-config" @click="openHarnessDialog">
          生成 DeepSeek Harness 配置
        </ElButton>
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

      <div v-else-if="filteredProviders.length > 0" class="resource-groups">
        <ResourceStatusGroup
          v-if="enabledProviders.length > 0"
          data-test="enabled-provider-group"
          status="enabled"
          title="启用中"
          :count="enabledProviders.length"
        >
          <div class="providers-grid">
            <ProviderCard
              v-for="provider in enabledProviders"
              :key="provider.id"
              :data-test="`provider-card-${String(provider.id)}`"
              :provider="provider"
              :loading="providerOperations.has(provider.id)"
              :non-deletable="nonDeletableIds.has(provider.id)"
              @edit="openEdit"
              @delete="removeProvider"
              @sync="openSyncDialog"
              @toggle="toggleProvider"
            />
          </div>
        </ResourceStatusGroup>
        <ResourceStatusGroup
          v-if="disabledProviders.length > 0"
          data-test="disabled-provider-group"
          status="disabled"
          title="已停用"
          :count="disabledProviders.length"
        >
          <div class="providers-grid">
            <ProviderCard
              v-for="provider in disabledProviders"
              :key="provider.id"
              :data-test="`provider-card-${String(provider.id)}`"
              :provider="provider"
              :loading="providerOperations.has(provider.id)"
              :non-deletable="nonDeletableIds.has(provider.id)"
              @edit="openEdit"
              @delete="removeProvider"
              @sync="openSyncDialog"
              @toggle="toggleProvider"
            />
          </div>
        </ResourceStatusGroup>
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

    <ModelSyncDialog
      :model-value="syncDialogOpen"
      :provider-id="syncTargetProvider?.id ?? null"
      :provider-name="syncTargetProvider?.name ?? ''"
      :submitting="syncSubmitting"
      @update:model-value="setSyncDialogOpen"
      @confirm="confirmSyncModels"
    />

    <ElDialog
      :model-value="harnessDialogOpen"
      width="min(94vw, 52rem)"
      :close-on-click-modal="false"
      @update:model-value="(value) => { if (!value) closeHarnessDialog() }"
    >
      <template #header>
        <div>
          <h2 class="dialog-heading">生成 DeepSeek Harness 配置</h2>
          <p class="dialog-description">下载凭据和设置文件后，分别合并到 Harness 配置目录。</p>
        </div>
      </template>

      <ElAlert
        title="凭据文件包含真实接口密钥，请勿提交到版本库或分享给他人。"
        type="warning"
        :closable="false"
        show-icon
      />

      <div class="harness-form">
        <label for="harness-provider-id">供应商 ID</label>
        <ElInput id="harness-provider-id" v-model="harnessProviderId" required />
        <label for="harness-display-name">显示名称</label>
        <ElInput id="harness-display-name" v-model="harnessDisplayName" required />
        <label for="harness-base-url">基础地址</label>
        <ElInput id="harness-base-url" v-model="harnessBaseUrl" required />
        <label for="harness-api-key-env">环境变量名称</label>
        <ElInput id="harness-api-key-env" v-model="harnessApiKeyEnv" required />
        <label for="harness-api-key">API 密钥</label>
        <ElInput
          id="harness-api-key"
          v-model="harnessApiKey"
          data-test="deepseek-harness-api-key"
          type="password"
          show-password
          autocomplete="off"
          required
        />
        <fieldset class="harness-api" aria-label="OpenAI API 类型">
          <legend>OpenAI API 类型</legend>
          <label>
            <input v-model="harnessApi" name="harness-api" type="radio" value="openai-responses">
            Responses
          </label>
          <label>
            <input v-model="harnessApi" name="harness-api" type="radio" value="openai-completions">
            Chat Completions
          </label>
        </fieldset>
        <label for="harness-default-model">默认模型</label>
        <select id="harness-default-model" v-model="harnessDefaultModel" required>
          <option value="" disabled>选择默认模型</option>
          <option
            v-for="model in harnessModels.filter((item) => item.enabled)"
            :key="model.id"
            :value="model.canonical_name"
          >
            {{ model.canonical_name }}
          </option>
        </select>
        <p v-if="harnessLoadingModels" class="muted">正在加载模型…</p>
        <p v-else-if="harnessModelLoadError" class="harness-error" role="alert">
          {{ harnessModelLoadError }}
        </p>
      </div>

      <section class="harness-file" aria-labelledby="harness-credentials-heading">
        <div class="harness-file-header">
          <h3 id="harness-credentials-heading">.credentials.yaml</h3>
          <div>
            <ElButton
              data-test="deepseek-harness-copy-credentials"
              :disabled="!harnessReady"
              @click="copyHarnessFile(harnessFiles.credentialsYaml)"
            >
              复制
            </ElButton>
            <ElButton
              data-test="deepseek-harness-download-credentials"
              :disabled="!harnessReady"
              @click="downloadHarnessFile('.credentials.yaml', harnessFiles.credentialsYaml)"
            >
              下载
            </ElButton>
          </div>
        </div>
        <pre data-test="deepseek-harness-credentials">{{ harnessFiles.credentialsYaml }}</pre>
      </section>
      <section class="harness-file" aria-labelledby="harness-settings-heading">
        <div class="harness-file-header">
          <h3 id="harness-settings-heading">settings.yaml</h3>
          <div>
            <ElButton
              data-test="deepseek-harness-copy-settings"
              :disabled="!harnessReady"
              @click="copyHarnessFile(harnessFiles.settingsYaml)"
            >
              复制
            </ElButton>
            <ElButton
              data-test="deepseek-harness-download-settings"
              :disabled="!harnessReady"
              @click="downloadHarnessFile('settings.yaml', harnessFiles.settingsYaml)"
            >
              下载
            </ElButton>
          </div>
        </div>
        <pre data-test="deepseek-harness-settings">{{ harnessFiles.settingsYaml }}</pre>
      </section>

      <template #footer>
        <ElButton data-test="deepseek-harness-close" @click="closeHarnessDialog">关闭</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 1rem;
}

.catalog-file-input {
  display: none;
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
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 0.75rem;
  padding: 1rem;
}

.provider-skeleton {
  height: 180px;
}

.resource-groups {
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
}

.dialog-heading,
.dialog-description {
  margin: 0;
}

.dialog-description,
.muted {
  margin-top: 0.35rem;
  color: var(--gateway-muted);
}

.harness-form {
  display: grid;
  gap: 0.4rem;
  margin-top: 1rem;
}

.harness-form > label,
.harness-api legend {
  color: var(--gateway-text);
  font-size: 0.9rem;
  font-weight: 600;
}

.harness-form select {
  min-height: 2rem;
  padding: 0.45rem 0.7rem;
  color: var(--gateway-text);
  background: var(--gateway-panel);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.harness-api {
  display: flex;
  gap: 1rem;
  margin: 0.6rem 0;
  padding: 0.6rem;
  border: 1px solid var(--gateway-border);
  border-radius: var(--el-border-radius-base);
}

.harness-api legend {
  padding: 0 0.25rem;
}

.harness-api label {
  display: flex;
  gap: 0.35rem;
  align-items: center;
}

.harness-error {
  margin: 0;
  color: var(--el-color-danger);
}

.harness-file {
  margin-top: 1rem;
}

.harness-file-header {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
}

.harness-file-header h3 {
  margin: 0;
  font-size: 1rem;
}

.harness-file pre {
  max-height: 16rem;
  margin: 0.5rem 0 0;
  padding: 0.8rem;
  overflow: auto;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.providers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 0.75rem;
}

@media (max-width: 640px) {
  .provider-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .provider-search {
    width: 100%;
  }

  .provider-loading,
  .providers-grid {
    grid-template-columns: 1fr;
  }

  .resource-groups {
    padding: 0.75rem;
  }
}
</style>
