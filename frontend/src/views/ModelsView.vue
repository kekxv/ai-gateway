<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Delete, Edit, Plus, Search } from '@element-plus/icons-vue'
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
  createModel,
  createModelRoute,
  deleteModel,
  deleteModelRoute,
  listModelRoutes,
  listModels,
  updateModel,
  updateModelRoute,
} from '@/api/models'
import { listProviders } from '@/api/providers'
import type {
  ModelCreate,
  ModelResponse,
  ModelRouteCreate,
  ModelRouteResponse,
  ModelRouteUpdate,
  ModelUpdate,
  Protocol,
  ProviderResponse,
  RouteRuntimeState,
  RouteSource,
} from '@/api/types'
import { formatMoney } from '@/utils/format'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ModelFormDrawer from '@/components/models/ModelFormDrawer.vue'
import RouteFormDrawer from '@/components/models/RouteFormDrawer.vue'

type NoticeType = 'success' | 'warning' | 'error'
type ModelOperation = 'edit' | 'delete' | 'disable'
type RouteOperation = 'edit' | 'delete' | 'disable'

interface Notice {
  type: NoticeType
  text: string
  conflictId?: number
}

interface RouteNotice extends Notice {
  modelId: number
}

interface RouteOperationState {
  modelId: number
  operation: RouteOperation
}

const models = ref<ModelResponse[]>([])
const providers = ref<ProviderResponse[]>([])
const allRoutes = ref<ModelRouteResponse[]>([])
const modelRoutes = ref<ModelRouteResponse[]>([])
const selectedModelId = ref<number | null>(null)
const searchText = ref('')
const loading = ref(true)
const catalogReady = ref(false)
const loadError = ref('')
const routesLoading = ref(false)
const routeLoadError = ref('')
const modelNotice = ref<Notice | null>(null)
const routeNotice = ref<RouteNotice | null>(null)
const modelDrawerOpen = ref(false)
const routeDrawerOpen = ref(false)
const editingModel = ref<ModelResponse | null>(null)
const editingRoute = ref<ModelRouteResponse | null>(null)
const routeDrawerModelId = ref<number | null>(null)
const modelSubmitting = ref(false)
const routeSubmitting = ref(false)
const modelOperations = ref(new Map<number, ModelOperation>())
const routeOperations = ref(new Map<number, RouteOperationState>())
const nonDeletableModelIds = ref(new Set<number>())
const nonDeletableRouteIds = ref(new Set<number>())
const deletedModelIds = new Set<number>()
const deletedRouteIds = new Set<number>()
const operationControllers = new Set<AbortController>()
let loadController: AbortController | undefined
let routeLoadController: AbortController | undefined
let modelSaveController: AbortController | undefined
let routeSaveController: AbortController | undefined
let mounted = true
let loadGeneration = 0
let routeLoadGeneration = 0
let stateRevision = 0
let routeStateRevision = 0
let selectionRevision = 0
let modelDrawerSession = 0
let routeDrawerSession = 0
let activeModelSaveToken: symbol | undefined
let activeRouteSaveToken: symbol | undefined

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

const selectedModel = computed(
  () => models.value.find((model) => model.id === selectedModelId.value) ?? null,
)

const visibleRouteNotice = computed(() =>
  routeNotice.value?.modelId === selectedModelId.value ? routeNotice.value : null,
)

const selectedContextBusy = computed(() => {
  const modelId = selectedModelId.value
  if (modelId === null) return false
  return modelOperations.value.has(modelId) || hasRouteActivity(modelId)
})

const selectionLocked = computed(
  () =>
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    modelOperations.value.size > 0 ||
    routeOperations.value.size > 0,
)

const filteredModels = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase('zh-CN')
  if (query === '') return models.value
  return models.value.filter((model) =>
    [model.display_name, model.canonical_name, ...model.aliases.map((alias) => alias.alias)].some(
      (value) => value.toLocaleLowerCase('zh-CN').includes(query),
    ),
  )
})

const routeCounts = computed(() => {
  const counts = new Map<number, number>()
  for (const route of allRoutes.value) {
    counts.set(route.model_id, (counts.get(route.model_id) ?? 0) + 1)
  }
  return counts
})

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function operationController(): AbortController {
  const controller = new AbortController()
  operationControllers.add(controller)
  return controller
}

function beginModelOperation(modelId: number, operation: ModelOperation): boolean {
  if (modelOperations.value.has(modelId)) return false
  const next = new Map(modelOperations.value)
  next.set(modelId, operation)
  modelOperations.value = next
  return true
}

function finishModelOperation(modelId: number, operation: ModelOperation): void {
  if (modelOperations.value.get(modelId) !== operation) return
  const next = new Map(modelOperations.value)
  next.delete(modelId)
  modelOperations.value = next
}

function beginRouteOperation(
  routeId: number,
  modelId: number,
  operation: RouteOperation,
): boolean {
  if (routeOperations.value.has(routeId)) return false
  const next = new Map(routeOperations.value)
  next.set(routeId, { modelId, operation })
  routeOperations.value = next
  return true
}

function finishRouteOperation(routeId: number, modelId: number, operation: RouteOperation): void {
  const current = routeOperations.value.get(routeId)
  if (current?.modelId !== modelId || current.operation !== operation) return
  const next = new Map(routeOperations.value)
  next.delete(routeId)
  routeOperations.value = next
}

function isCurrentModelOperation(
  controller: AbortController,
  modelId: number,
  operation: ModelOperation,
): boolean {
  return mounted && !controller.signal.aborted && modelOperations.value.get(modelId) === operation
}

function isCurrentRouteOperation(
  controller: AbortController,
  routeId: number,
  modelId: number,
  operation: RouteOperation,
): boolean {
  const current = routeOperations.value.get(routeId)
  return (
    mounted &&
    !controller.signal.aborted &&
    selectedModelId.value === modelId &&
    current?.modelId === modelId &&
    current.operation === operation
  )
}

function hasRouteActivity(modelId: number): boolean {
  if (routeDrawerOpen.value && routeDrawerModelId.value === modelId) return true
  for (const operation of routeOperations.value.values()) {
    if (operation.modelId === modelId) return true
  }
  return false
}

function setSelectedModelId(modelId: number | null): void {
  if (selectedModelId.value === modelId) return
  selectedModelId.value = modelId
  selectionRevision += 1
}

async function loadRoutes(modelId: number): Promise<void> {
  routeLoadController?.abort()
  const controller = new AbortController()
  routeLoadController = controller
  const generation = ++routeLoadGeneration
  const startingRevision = routeStateRevision
  const startingSelectionRevision = selectionRevision
  routesLoading.value = true
  try {
    const loadedRoutes = await listModelRoutes({ model_id: modelId }, controller.signal)
    if (
      !mounted ||
      controller.signal.aborted ||
      generation !== routeLoadGeneration ||
      selectedModelId.value !== modelId ||
      startingSelectionRevision !== selectionRevision ||
      startingRevision !== routeStateRevision
    ) {
      return
    }
    modelRoutes.value = loadedRoutes.filter(
      (route) => route.model_id === modelId && !deletedRouteIds.has(route.id),
    )
    routeLoadError.value = ''
  } catch (error: unknown) {
    if (
      !mounted ||
      controller.signal.aborted ||
      generation !== routeLoadGeneration ||
      selectedModelId.value !== modelId ||
      startingSelectionRevision !== selectionRevision ||
      startingRevision !== routeStateRevision
    ) {
      return
    }
    routeLoadError.value = errorText(error, '模型路由加载失败')
  } finally {
    if (mounted && generation === routeLoadGeneration) routesLoading.value = false
  }
}

async function load(): Promise<void> {
  loadController?.abort()
  const controller = new AbortController()
  loadController = controller
  const generation = ++loadGeneration
  const startingRevision = stateRevision
  const startingSelectionRevision = selectionRevision
  loading.value = models.value.length === 0
  try {
    const [loadedModels, loadedProviders, loadedRoutes] = await Promise.all([
      listModels(controller.signal),
      listProviders(controller.signal),
      listModelRoutes({}, controller.signal),
    ])
    if (!mounted || controller.signal.aborted || generation !== loadGeneration) return
    providers.value = loadedProviders
    catalogReady.value = true
    if (
      startingRevision !== stateRevision ||
      startingSelectionRevision !== selectionRevision
    ) return
    models.value = loadedModels.filter((model) => !deletedModelIds.has(model.id))
    allRoutes.value = loadedRoutes.filter(
      (route) => !deletedRouteIds.has(route.id) && !deletedModelIds.has(route.model_id),
    )
    loadError.value = ''
    const currentStillExists = models.value.some((model) => model.id === selectedModelId.value)
    setSelectedModelId(currentStillExists ? selectedModelId.value : (models.value[0]?.id ?? null))
    if (selectedModelId.value === null) {
      modelRoutes.value = []
      routeLoadError.value = ''
    } else {
      void loadRoutes(selectedModelId.value)
    }
  } catch (error: unknown) {
    if (
      !mounted ||
      controller.signal.aborted ||
      generation !== loadGeneration ||
      startingRevision !== stateRevision ||
      startingSelectionRevision !== selectionRevision
    ) {
      return
    }
    loadError.value = errorText(error, '模型列表加载失败')
  } finally {
    if (mounted && generation === loadGeneration) loading.value = false
  }
}

function selectModel(model: ModelResponse): void {
  if (
    selectedModelId.value === model.id ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    modelSubmitting.value ||
    routeSubmitting.value ||
    selectionLocked.value
  ) {
    return
  }
  setSelectedModelId(model.id)
  routeNotice.value = null
  modelRoutes.value = []
  void loadRoutes(model.id)
}

function replaceModel(updated: ModelResponse): void {
  stateRevision += 1
  deletedModelIds.delete(updated.id)
  const index = models.value.findIndex((model) => model.id === updated.id)
  if (index === -1) models.value.push(updated)
  else models.value.splice(index, 1, updated)
  if (selectedModelId.value === null) {
    setSelectedModelId(updated.id)
    void loadRoutes(updated.id)
  }
}

function replaceRoute(updated: ModelRouteResponse): void {
  stateRevision += 1
  routeStateRevision += 1
  deletedRouteIds.delete(updated.id)
  const allIndex = allRoutes.value.findIndex((route) => route.id === updated.id)
  if (allIndex === -1) allRoutes.value.push(updated)
  else allRoutes.value.splice(allIndex, 1, updated)
  if (selectedModelId.value === updated.model_id) {
    const routeIndex = modelRoutes.value.findIndex((route) => route.id === updated.id)
    if (routeIndex === -1) modelRoutes.value.push(updated)
    else modelRoutes.value.splice(routeIndex, 1, updated)
  }
}

function openCreateModel(): void {
  if (
    !catalogReady.value ||
    loading.value ||
    modelSubmitting.value ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    selectedContextBusy.value
  ) return
  modelDrawerSession += 1
  editingModel.value = null
  modelDrawerOpen.value = true
}

function openEditModel(model: ModelResponse): void {
  if (
    modelSubmitting.value ||
    !catalogReady.value ||
    loading.value ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    hasRouteActivity(model.id) ||
    selectedContextBusy.value ||
    !beginModelOperation(model.id, 'edit')
  ) {
    return
  }
  modelDrawerSession += 1
  editingModel.value = model
  modelDrawerOpen.value = true
}

function setModelDrawerOpen(open: boolean): void {
  if (open || modelSubmitting.value) return
  const modelId = editingModel.value?.id
  modelDrawerSession += 1
  modelDrawerOpen.value = false
  editingModel.value = null
  if (modelId !== undefined) finishModelOperation(modelId, 'edit')
}

function isCurrentModelSave(
  controller: AbortController,
  token: symbol,
  session: number,
  modelId: number | undefined,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    activeModelSaveToken === token &&
    modelDrawerOpen.value &&
    modelDrawerSession === session &&
    editingModel.value?.id === modelId
  )
}

async function saveModel(payload: ModelCreate | ModelUpdate): Promise<void> {
  if (modelSubmitting.value || !modelDrawerOpen.value) return
  const modelId = editingModel.value?.id
  const isCreate = modelId === undefined
  const session = modelDrawerSession
  const token = Symbol('model-save')
  const controller = new AbortController()
  modelSaveController?.abort()
  modelSaveController = controller
  activeModelSaveToken = token
  modelSubmitting.value = true
  try {
    const updated = isCreate
      ? await createModel(payload as ModelCreate, controller.signal)
      : await updateModel(modelId, payload, controller.signal)
    if (!isCurrentModelSave(controller, token, session, modelId)) return
    if (!isCreate && updated.id !== modelId) return
    replaceModel(updated)
    activeModelSaveToken = undefined
    modelSaveController = undefined
    modelSubmitting.value = false
    modelDrawerSession += 1
    modelDrawerOpen.value = false
    editingModel.value = null
    if (modelId !== undefined) finishModelOperation(modelId, 'edit')
    modelNotice.value = {
      type: 'success',
      text: isCreate ? '模型已创建' : '模型设置已保存',
    }
  } catch (error: unknown) {
    if (
      mounted &&
      !controller.signal.aborted &&
      activeModelSaveToken === token &&
      modelDrawerSession === session
    ) {
      modelNotice.value = { type: 'error', text: errorText(error, '模型保存失败') }
    }
  } finally {
    if (activeModelSaveToken === token) {
      activeModelSaveToken = undefined
      modelSaveController = undefined
      if (mounted) modelSubmitting.value = false
    }
  }
}

function openCreateRoute(): void {
  const modelId = selectedModelId.value
  if (
    !catalogReady.value ||
    loading.value ||
    selectedModel.value === null ||
    modelId === null ||
    routeSubmitting.value ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    modelOperations.value.has(modelId) ||
    hasRouteActivity(modelId)
  ) {
    return
  }
  routeDrawerSession += 1
  editingRoute.value = null
  routeDrawerModelId.value = modelId
  routeDrawerOpen.value = true
}

function openEditRoute(route: ModelRouteResponse): void {
  if (
    routeSubmitting.value ||
    !catalogReady.value ||
    loading.value ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    selectedModelId.value !== route.model_id ||
    modelOperations.value.has(route.model_id) ||
    hasRouteActivity(route.model_id) ||
    !beginRouteOperation(route.id, route.model_id, 'edit')
  ) {
    return
  }
  routeDrawerSession += 1
  editingRoute.value = route
  routeDrawerModelId.value = route.model_id
  routeDrawerOpen.value = true
}

function setRouteDrawerOpen(open: boolean): void {
  if (open || routeSubmitting.value) return
  const routeId = editingRoute.value?.id
  routeDrawerSession += 1
  routeDrawerOpen.value = false
  editingRoute.value = null
  const modelId = routeDrawerModelId.value
  routeDrawerModelId.value = null
  if (routeId !== undefined && modelId !== null) finishRouteOperation(routeId, modelId, 'edit')
}

function isCurrentRouteSave(
  controller: AbortController,
  token: symbol,
  session: number,
  routeId: number | undefined,
  modelId: number,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    activeRouteSaveToken === token &&
    routeDrawerOpen.value &&
    routeDrawerSession === session &&
    routeDrawerModelId.value === modelId &&
    editingRoute.value?.id === routeId &&
    selectedModelId.value === modelId
  )
}

async function saveRoute(payload: ModelRouteCreate | ModelRouteUpdate): Promise<void> {
  const modelId = routeDrawerModelId.value
  if (
    routeSubmitting.value ||
    !routeDrawerOpen.value ||
    modelId === null ||
    selectedModelId.value !== modelId ||
    modelOperations.value.has(modelId)
  ) return
  const routeId = editingRoute.value?.id
  const isCreate = routeId === undefined
  if (
    (isCreate && (payload as ModelRouteCreate).model_id !== modelId) ||
    (!isCreate && editingRoute.value?.model_id !== modelId)
  ) return
  const session = routeDrawerSession
  const token = Symbol('route-save')
  const controller = new AbortController()
  routeSaveController?.abort()
  routeSaveController = controller
  activeRouteSaveToken = token
  routeSubmitting.value = true
  try {
    const updated = isCreate
      ? await createModelRoute(payload as ModelRouteCreate, controller.signal)
      : await updateModelRoute(routeId, payload, controller.signal)
    if (!isCurrentRouteSave(controller, token, session, routeId, modelId)) return
    if (updated.model_id !== modelId || (!isCreate && updated.id !== routeId)) return
    replaceRoute(updated)
    activeRouteSaveToken = undefined
    routeSaveController = undefined
    routeSubmitting.value = false
    routeDrawerSession += 1
    routeDrawerOpen.value = false
    editingRoute.value = null
    routeDrawerModelId.value = null
    if (routeId !== undefined) finishRouteOperation(routeId, modelId, 'edit')
    routeNotice.value = {
      type: 'success',
      text: isCreate ? '模型路由已创建' : '模型路由已保存',
      modelId,
    }
  } catch (error: unknown) {
    if (
      mounted &&
      !controller.signal.aborted &&
      activeRouteSaveToken === token &&
      routeDrawerSession === session &&
      selectedModelId.value === modelId
    ) {
      routeNotice.value = {
        type: 'error',
        text: errorText(error, '模型路由保存失败'),
        modelId,
      }
    }
  } finally {
    if (activeRouteSaveToken === token) {
      activeRouteSaveToken = undefined
      routeSaveController = undefined
      if (mounted) routeSubmitting.value = false
    }
  }
}

async function removeModel(model: ModelResponse): Promise<void> {
  if (
    !catalogReady.value ||
    loading.value ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    hasRouteActivity(model.id) ||
    selectedContextBusy.value ||
    nonDeletableModelIds.value.has(model.id) ||
    !beginModelOperation(model.id, 'delete')
  ) return
  const controller = operationController()
  try {
    await ElMessageBox.confirm(
      `确定删除模型“${model.display_name}”吗？关联且无历史记录的路由也会被删除。`,
      '删除模型',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    operationControllers.delete(controller)
    if (isCurrentModelOperation(controller, model.id, 'delete')) {
      finishModelOperation(model.id, 'delete')
    }
    return
  }
  if (!isCurrentModelOperation(controller, model.id, 'delete')) {
    operationControllers.delete(controller)
    return
  }

  try {
    await deleteModel(model.id, controller.signal)
    if (!isCurrentModelOperation(controller, model.id, 'delete')) return
    stateRevision += 1
    routeStateRevision += 1
    deletedModelIds.add(model.id)
    models.value = models.value.filter((item) => item.id !== model.id)
    allRoutes.value = allRoutes.value.filter((route) => route.model_id !== model.id)
    if (selectedModelId.value === model.id) {
      const nextModelId = models.value[0]?.id ?? null
      setSelectedModelId(nextModelId)
      modelRoutes.value = []
      if (nextModelId !== null) void loadRoutes(nextModelId)
    }
    modelNotice.value = { type: 'success', text: `模型“${model.display_name}”已删除` }
  } catch (error: unknown) {
    if (!isCurrentModelOperation(controller, model.id, 'delete')) return
    if (error instanceof ApiError && error.code === 'model_has_history') {
      nonDeletableModelIds.value = new Set(nonDeletableModelIds.value).add(model.id)
      modelNotice.value = {
        type: 'warning',
        text: '模型已有请求历史，不能直接删除；可以改为停用。',
        conflictId: model.id,
      }
    } else {
      modelNotice.value = { type: 'error', text: errorText(error, '模型删除失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentModelOperation(controller, model.id, 'delete')) {
      finishModelOperation(model.id, 'delete')
    }
  }
}

async function disableModel(modelId: number): Promise<void> {
  if (
    !catalogReady.value ||
    loading.value ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    hasRouteActivity(modelId) ||
    selectedContextBusy.value ||
    !beginModelOperation(modelId, 'disable')
  ) return
  const controller = operationController()
  try {
    const updated = await updateModel(modelId, { enabled: false }, controller.signal)
    if (updated.id !== modelId || !isCurrentModelOperation(controller, modelId, 'disable')) return
    replaceModel(updated)
    modelNotice.value = { type: 'success', text: `模型“${updated.display_name}”已停用` }
  } catch (error: unknown) {
    if (isCurrentModelOperation(controller, modelId, 'disable')) {
      modelNotice.value = { type: 'error', text: errorText(error, '模型停用失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentModelOperation(controller, modelId, 'disable')) {
      finishModelOperation(modelId, 'disable')
    }
  }
}

async function removeRoute(route: ModelRouteResponse): Promise<void> {
  const modelId = route.model_id
  if (
    !catalogReady.value ||
    loading.value ||
    selectedModelId.value !== modelId ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    modelOperations.value.has(modelId) ||
    hasRouteActivity(modelId) ||
    nonDeletableRouteIds.value.has(route.id) ||
    !beginRouteOperation(route.id, modelId, 'delete')
  ) return
  const controller = operationController()
  try {
    await ElMessageBox.confirm(
      `确定删除路由“${route.upstream_model}”吗？此操作无法撤销。`,
      '删除模型路由',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    operationControllers.delete(controller)
    if (isCurrentRouteOperation(controller, route.id, modelId, 'delete')) {
      finishRouteOperation(route.id, modelId, 'delete')
    }
    return
  }
  if (!isCurrentRouteOperation(controller, route.id, modelId, 'delete')) {
    operationControllers.delete(controller)
    return
  }

  try {
    await deleteModelRoute(route.id, controller.signal)
    if (!isCurrentRouteOperation(controller, route.id, modelId, 'delete')) return
    stateRevision += 1
    routeStateRevision += 1
    deletedRouteIds.add(route.id)
    allRoutes.value = allRoutes.value.filter((item) => item.id !== route.id)
    modelRoutes.value = modelRoutes.value.filter((item) => item.id !== route.id)
    routeNotice.value = {
      type: 'success',
      text: `路由“${route.upstream_model}”已删除`,
      modelId,
    }
  } catch (error: unknown) {
    if (!isCurrentRouteOperation(controller, route.id, modelId, 'delete')) return
    if (error instanceof ApiError && error.code === 'model_route_has_history') {
      nonDeletableRouteIds.value = new Set(nonDeletableRouteIds.value).add(route.id)
      routeNotice.value = {
        type: 'warning',
        text: '模型路由已有请求历史，不能直接删除；可以改为停用。',
        conflictId: route.id,
        modelId,
      }
    } else {
      routeNotice.value = {
        type: 'error',
        text: errorText(error, '模型路由删除失败'),
        modelId,
      }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentRouteOperation(controller, route.id, modelId, 'delete')) {
      finishRouteOperation(route.id, modelId, 'delete')
    }
  }
}

async function disableRoute(routeId: number, modelId: number): Promise<void> {
  if (
    !catalogReady.value ||
    loading.value ||
    selectedModelId.value !== modelId ||
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    modelOperations.value.has(modelId) ||
    hasRouteActivity(modelId) ||
    !modelRoutes.value.some((route) => route.id === routeId && route.model_id === modelId) ||
    !beginRouteOperation(routeId, modelId, 'disable')
  ) return
  const controller = operationController()
  try {
    const updated = await updateModelRoute(routeId, { enabled: false }, controller.signal)
    if (
      updated.model_id !== modelId ||
      !isCurrentRouteOperation(controller, routeId, modelId, 'disable')
    ) return
    replaceRoute(updated)
    routeNotice.value = {
      type: 'success',
      text: `路由“${updated.upstream_model}”已停用`,
      modelId,
    }
  } catch (error: unknown) {
    if (isCurrentRouteOperation(controller, routeId, modelId, 'disable')) {
      routeNotice.value = {
        type: 'error',
        text: errorText(error, '模型路由停用失败'),
        modelId,
      }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentRouteOperation(controller, routeId, modelId, 'disable')) {
      finishRouteOperation(routeId, modelId, 'disable')
    }
  }
}

function providerName(providerId: number): string {
  return (
    providers.value.find((provider) => provider.id === providerId)?.name ??
    `#${String(providerId)}`
  )
}

function protocolName(providerId: number, protocolId: number): string {
  const protocol = providers.value
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

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  routeLoadGeneration += 1
  modelDrawerSession += 1
  routeDrawerSession += 1
  loadController?.abort()
  routeLoadController?.abort()
  modelSaveController?.abort()
  routeSaveController?.abort()
  for (const controller of operationControllers) controller.abort()
  operationControllers.clear()
})
</script>

<template>
  <PageHeader title="模型管理" description="管理统一模型、调用别名与加权上游路由。">
    <template #actions>
      <ElButton
        data-test="create-model"
        type="primary"
        :disabled="!catalogReady || loading || selectionLocked"
        @click="openCreateModel"
      >
        <ElIcon><Plus /></ElIcon>
        新建模型
      </ElButton>
    </template>
  </PageHeader>

  <div v-if="modelNotice" data-test="model-notice" class="notice-row">
    <ElAlert
      :type="modelNotice.type"
      :title="modelNotice.text"
      show-icon
      closable
      @close="modelNotice = null"
    />
    <ElButton
      v-if="modelNotice.conflictId !== undefined"
      :data-test="`disable-model-${String(modelNotice.conflictId)}`"
      type="warning"
      plain
      :loading="modelOperations.get(modelNotice.conflictId) === 'disable'"
      :disabled="modelOperations.has(modelNotice.conflictId)"
      @click="disableModel(modelNotice.conflictId)"
    >
      改为停用
    </ElButton>
  </div>

  <section class="model-panel page-card" aria-labelledby="model-list-heading">
    <div class="panel-toolbar">
      <div>
        <h2 id="model-list-heading">模型列表</h2>
        <p>共 {{ models.length }} 个模型，选择模型可管理其上游路由</p>
      </div>
      <ElInput
        v-model="searchText"
        data-test="model-search"
        class="model-search"
        clearable
        placeholder="搜索显示名称、规范名称或别名"
        aria-label="搜索模型"
      >
        <template #prefix><ElIcon><Search /></ElIcon></template>
      </ElInput>
    </div>

    <div v-if="loading" class="loading-list" aria-label="正在加载模型">
      <ElSkeleton v-for="index in 3" :key="index" animated>
        <template #template><ElSkeletonItem variant="rect" class="list-skeleton" /></template>
      </ElSkeleton>
    </div>

    <ElResult v-else-if="loadError" icon="error" title="模型列表加载失败" :sub-title="loadError">
      <template #extra><ElButton type="primary" @click="load">重新加载</ElButton></template>
    </ElResult>

    <div v-else-if="filteredModels.length > 0" class="table-scroll">
      <table class="model-table">
        <thead>
          <tr>
            <th scope="col">模型</th>
            <th scope="col">规范名称</th>
            <th scope="col">别名</th>
            <th scope="col">输入价格 / 百万令牌</th>
            <th scope="col">输出价格 / 百万令牌</th>
            <th scope="col">路由策略</th>
            <th scope="col">状态</th>
            <th scope="col">路由数</th>
            <th scope="col" class="actions-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="model in filteredModels"
            :key="model.id"
            :class="{ selected: selectedModelId === model.id }"
          >
            <td>
              <ElButton
                :data-test="`select-model-${String(model.id)}`"
                class="model-select"
                text
                type="primary"
                :disabled="!catalogReady || loading || selectionLocked"
                @click="selectModel(model)"
              >
                {{ model.display_name }}
              </ElButton>
            </td>
            <td><code>{{ model.canonical_name }}</code></td>
            <td>
              <div class="tag-list">
                <ElTag
                  v-for="alias in model.aliases"
                  :key="alias.id"
                  :type="alias.enabled ? 'primary' : 'info'"
                  effect="plain"
                >
                  {{ alias.alias }} · {{ alias.enabled ? '已启用' : '已停用' }}
                </ElTag>
                <span v-if="model.aliases.length === 0" class="muted">无别名</span>
              </div>
            </td>
            <td class="decimal-value">{{ formatMoney(model.input_price_per_million) }}</td>
            <td class="decimal-value">{{ formatMoney(model.output_price_per_million) }}</td>
            <td>加权随机</td>
            <td :data-test="`model-status-${String(model.id)}`">
              <StatusTag :status="model.enabled ? 'enabled' : 'disabled'" />
            </td>
            <td :data-test="`route-count-${String(model.id)}`">
              {{ routeCounts.get(model.id) ?? 0 }}
            </td>
            <td>
              <div class="row-actions">
                <ElButton
                  :data-test="`edit-model-${String(model.id)}`"
                  text
                  :disabled="
                    !catalogReady ||
                    loading ||
                    selectionLocked ||
                    modelOperations.has(model.id) ||
                    hasRouteActivity(model.id)
                  "
                  @click="openEditModel(model)"
                >
                  <ElIcon><Edit /></ElIcon>
                  编辑
                </ElButton>
                <ElButton
                  :data-test="`delete-model-${String(model.id)}`"
                  text
                  type="danger"
                  :loading="modelOperations.get(model.id) === 'delete'"
                  :disabled="
                    !catalogReady ||
                    loading ||
                    selectionLocked ||
                    modelOperations.has(model.id) ||
                    hasRouteActivity(model.id) ||
                    nonDeletableModelIds.has(model.id)
                  "
                  :title="
                    nonDeletableModelIds.has(model.id)
                      ? '该模型已有请求历史，请改为停用'
                      : undefined
                  "
                  @click="removeModel(model)"
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
      :description="searchText.trim() === '' ? '暂无模型' : '没有匹配的模型'"
    />
  </section>

  <section data-test="route-panel" class="route-panel page-card" aria-labelledby="route-heading">
    <div class="panel-toolbar">
      <div>
        <h2 id="route-heading">
          {{ selectedModel === null ? '模型路由' : `${selectedModel.display_name} 的模型路由` }}
        </h2>
        <p v-if="selectedModel">客户端名称会在转发前重写为路由中的提供商原始模型名</p>
        <p v-else>请先创建或选择一个模型</p>
      </div>
      <ElButton
        data-test="create-route"
        type="primary"
        plain
        :disabled="
          !catalogReady ||
          loading ||
          selectedModel === null ||
          selectionLocked ||
          selectedContextBusy
        "
        @click="openCreateRoute"
      >
        <ElIcon><Plus /></ElIcon>
        新建路由
      </ElButton>
    </div>

    <div v-if="visibleRouteNotice" data-test="route-notice" class="route-notice notice-row">
      <ElAlert
        :type="visibleRouteNotice.type"
        :title="visibleRouteNotice.text"
        show-icon
        closable
        @close="routeNotice = null"
      />
      <ElButton
        v-if="visibleRouteNotice.conflictId !== undefined"
        :data-test="`disable-route-${String(visibleRouteNotice.conflictId)}`"
        type="warning"
        plain
        :loading="
          routeOperations.get(visibleRouteNotice.conflictId)?.operation === 'disable'
        "
        :disabled="routeOperations.has(visibleRouteNotice.conflictId)"
        @click="disableRoute(visibleRouteNotice.conflictId, visibleRouteNotice.modelId)"
      >
        改为停用
      </ElButton>
    </div>

    <div v-if="routesLoading" class="loading-list" aria-label="正在加载模型路由">
      <ElSkeleton v-for="index in 2" :key="index" animated>
        <template #template><ElSkeletonItem variant="rect" class="list-skeleton" /></template>
      </ElSkeleton>
    </div>
    <ElResult
      v-else-if="routeLoadError"
      icon="error"
      title="模型路由加载失败"
      :sub-title="routeLoadError"
    >
      <template #extra>
        <ElButton v-if="selectedModelId !== null" type="primary" @click="loadRoutes(selectedModelId)">
          重新加载
        </ElButton>
      </template>
    </ElResult>
    <div v-else-if="modelRoutes.length > 0" class="table-scroll">
      <table class="route-table">
        <thead>
          <tr>
            <th scope="col">供应商</th>
            <th scope="col">协议</th>
            <th scope="col">提供商原始模型名</th>
            <th scope="col">权重</th>
            <th scope="col">状态</th>
            <th scope="col">来源</th>
            <th scope="col">运行状态</th>
            <th scope="col">连续失败</th>
            <th scope="col">禁用至</th>
            <th scope="col">最近错误</th>
            <th scope="col" class="actions-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="route in modelRoutes" :key="route.id">
            <td>{{ providerName(route.provider_id) }}</td>
            <td>{{ protocolName(route.provider_id, route.provider_protocol_id) }}</td>
            <td><code>{{ route.upstream_model }}</code></td>
            <td>{{ route.weight }}</td>
            <td :data-test="`route-status-${String(route.id)}`">
              <StatusTag :status="route.enabled ? 'enabled' : 'disabled'" />
            </td>
            <td>
              <ElTag :type="route.source === 'discovered' ? 'primary' : 'info'" effect="plain">
                {{ sourceLabels[route.source] }}
              </ElTag>
            </td>
            <td>
              <ElTag :type="runtimeDetails[route.runtime_state].type" effect="light">
                {{ runtimeDetails[route.runtime_state].label }}
              </ElTag>
            </td>
            <td>{{ route.consecutive_failures }}</td>
            <td>{{ formatDate(route.disabled_until) }}</td>
            <td>
              <span v-if="route.last_error_code" :title="formatDate(route.last_error_at)">
                {{ route.last_error_code }}
              </span>
              <span v-else>—</span>
            </td>
            <td>
              <div class="row-actions">
                <ElButton
                  :data-test="`edit-route-${String(route.id)}`"
                  text
                  :disabled="
                    selectionLocked ||
                    modelOperations.has(route.model_id) ||
                    routeOperations.has(route.id)
                  "
                  @click="openEditRoute(route)"
                >
                  <ElIcon><Edit /></ElIcon>
                  编辑
                </ElButton>
                <ElButton
                  :data-test="`delete-route-${String(route.id)}`"
                  text
                  type="danger"
                  :loading="routeOperations.get(route.id)?.operation === 'delete'"
                  :disabled="
                    selectionLocked ||
                    modelOperations.has(route.model_id) ||
                    routeOperations.has(route.id) ||
                    nonDeletableRouteIds.has(route.id)
                  "
                  :title="
                    nonDeletableRouteIds.has(route.id)
                      ? '该路由已有请求历史，请改为停用'
                      : undefined
                  "
                  @click="removeRoute(route)"
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
    <ElEmpty v-else :description="selectedModel === null ? '尚未选择模型' : '暂无模型路由'" />
  </section>

  <ModelFormDrawer
    :model-value="modelDrawerOpen"
    :model="editingModel"
    :submitting="modelSubmitting"
    @update:model-value="setModelDrawerOpen"
    @submit="saveModel"
  />
  <RouteFormDrawer
    :model-value="routeDrawerOpen"
    :model="selectedModel"
    :route="editingRoute"
    :providers="providers"
    :submitting="routeSubmitting"
    @update:model-value="setRouteDrawerOpen"
    @submit="saveRoute"
  />
</template>

<style scoped>
.notice-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
}

.notice-row :deep(.el-alert) {
  flex: 1;
}

.model-panel,
.route-panel {
  overflow: hidden;
}

.route-panel {
  margin-top: 1.25rem;
}

.panel-toolbar {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--gateway-border);
}

.panel-toolbar h2,
.panel-toolbar p {
  margin: 0;
}

.panel-toolbar h2 {
  font-size: 1.1rem;
}

.panel-toolbar p,
.muted {
  margin-top: 0.25rem;
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.model-search {
  width: min(100%, 25rem);
}

.loading-list {
  display: grid;
  gap: 0.75rem;
  padding: 1.25rem;
}

.list-skeleton {
  height: 3.5rem;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

.model-table {
  min-width: 94rem;
}

.route-table {
  min-width: 105rem;
}

th,
td {
  padding: 0.9rem 1rem;
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

tbody tr:hover,
tbody tr.selected {
  background: #f8fafc;
}

tbody tr.selected td:first-child {
  box-shadow: inset 3px 0 var(--gateway-brand);
}

.model-select {
  padding: 0;
  font-weight: 600;
}

code,
.decimal-value {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  white-space: nowrap;
}

.tag-list,
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

.actions-column {
  width: 12rem;
}

.route-notice {
  padding: 1rem 1.25rem 0;
  margin-bottom: 0;
}

@media (max-width: 640px) {
  .panel-toolbar,
  .notice-row {
    align-items: stretch;
    flex-direction: column;
  }

  .model-search {
    width: 100%;
  }
}
</style>
