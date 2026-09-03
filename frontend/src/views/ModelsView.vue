<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
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

import { ApiError } from '@/api/client'
import {
  createModel,
  createModelRoute,
  deleteModel,
  deleteModelRoute,
  listAvailableModels,
  listModelRoutes,
  listModels,
  recoverModelRoute,
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
  ProviderResponse,
} from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import ResourceStatusGroup from '@/components/common/ResourceStatusGroup.vue'
import ModelFormDrawer from '@/components/models/ModelFormDrawer.vue'
import RouteFormDrawer from '@/components/models/RouteFormDrawer.vue'
import ModelCard from '@/components/models/ModelCard.vue'
import ModelPriceComparisonDialog from '@/components/models/ModelPriceComparisonDialog.vue'
import { useAuthStore } from '@/stores/auth'

type NoticeType = 'success' | 'warning' | 'error'
type ModelOperation = 'edit' | 'delete' | 'disable' | 'toggle'
type RouteOperation = 'edit' | 'delete' | 'disable' | 'recover'

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
const auth = useAuthStore()
const providers = ref<ProviderResponse[]>([])
const allRoutes = ref<ModelRouteResponse[]>([])
const searchText = ref('')
const providerFilter = ref<number | null>(null)
const loading = ref(true)
const catalogReady = ref(false)
const loadError = ref('')
const routesLoading = ref(true)
const modelNotice = ref<Notice | null>(null)
const routeNotice = ref<RouteNotice | null>(null)
const modelDrawerOpen = ref(false)
const routeDrawerOpen = ref(false)
const editingModel = ref<ModelResponse | null>(null)
const editingRoute = ref<ModelRouteResponse | null>(null)
const routeDrawerModelId = ref<number | null>(null)
const modelSubmitting = ref(false)
const routeSubmitting = ref(false)
const priceComparisonOpen = ref(false)
const selectedModelIds = ref(new Set<number>())
const modelOperations = ref(new Map<number, ModelOperation>())
const routeOperations = ref(new Map<number, RouteOperationState>())
const expandedRouteModelIds = ref(new Set<number>())
const nonDeletableModelIds = ref(new Set<number>())
const deletedModelIds = new Set<number>()
const deletedRouteIds = new Set<number>()
const operationControllers = new Set<AbortController>()
let loadController: AbortController | undefined
let modelSaveController: AbortController | undefined
let routeSaveController: AbortController | undefined
let mounted = true
let loadGeneration = 0
let stateRevision = 0
let modelDrawerSession = 0
let routeDrawerSession = 0
let activeModelSaveToken: symbol | undefined
let activeRouteSaveToken: symbol | undefined

const controlsLocked = computed(
  () =>
    modelDrawerOpen.value ||
    routeDrawerOpen.value ||
    modelOperations.value.size > 0 ||
    routeOperations.value.size > 0,
)

const filteredModels = computed(() => {
  let result = models.value
  const query = searchText.value.trim().toLocaleLowerCase('zh-CN')
  if (query !== '') {
    result = result.filter((model) =>
      [model.display_name, model.canonical_name, ...model.aliases.map((alias) => alias.alias)].some(
        (value) => value.toLocaleLowerCase('zh-CN').includes(query),
      ),
    )
  }
  if (providerFilter.value !== null) {
    const providerId = providerFilter.value
    const modelIdsWithRoutes = new Set(
      allRoutes.value.filter((route) => route.provider_id === providerId).map((route) => route.model_id),
    )
    result = result.filter((model) => modelIdsWithRoutes.has(model.id))
  }
  return [...result].sort(
    (left, right) =>
      left.display_name.localeCompare(right.display_name, 'zh-CN') ||
      left.canonical_name.localeCompare(right.canonical_name, 'zh-CN'),
  )
})

const enabledModels = computed(() => filteredModels.value.filter((model) => model.enabled))
const disabledModels = computed(() => filteredModels.value.filter((model) => !model.enabled))

const routesByModel = computed(() => {
  const map = new Map<number, ModelRouteResponse[]>()
  for (const route of allRoutes.value) {
    const routes = map.get(route.model_id) ?? []
    routes.push(route)
    map.set(route.model_id, routes)
  }
  return map
})

const selectedModels = computed(() =>
  models.value.filter((model) => selectedModelIds.value.has(model.id)),
)

function setModelSelected(modelId: number, selected: boolean): void {
  const next = new Set(selectedModelIds.value)
  if (selected) next.add(modelId)
  else next.delete(modelId)
  selectedModelIds.value = next
}

function pruneSelectedModels(): void {
  const currentIds = new Set(models.value.map((model) => model.id))
  selectedModelIds.value = new Set(
    [...selectedModelIds.value].filter((modelId) => currentIds.has(modelId)),
  )
  if (selectedModelIds.value.size < 2) priceComparisonOpen.value = false
}

function routeIsUsable(route: ModelRouteResponse): boolean {
  const provider = providers.value.find((item) => item.id === route.provider_id)
  return (
    route.enabled &&
    provider?.enabled === true &&
    provider.protocols.some((protocol) => protocol.enabled)
  )
}

const availableModels = computed(() =>
  enabledModels.value.filter((model) =>
    (routesByModel.value.get(model.id) ?? []).some(
      (route) => routeIsUsable(route) && route.runtime_state === 'closed',
    ),
  ),
)

const noUsableRouteModels = computed(() =>
  enabledModels.value.filter(
    (model) => !(routesByModel.value.get(model.id) ?? []).some(routeIsUsable),
  ),
)

const unhealthyRouteModels = computed(() =>
  enabledModels.value.filter((model) => {
    const routes = routesByModel.value.get(model.id) ?? []
    return (
      routes.some(routeIsUsable) &&
      !routes.some((route) => routeIsUsable(route) && route.runtime_state === 'closed')
    )
  }),
)

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

function setRoutesExpanded(modelId: number, expanded: boolean): void {
  const next = new Set(expandedRouteModelIds.value)
  if (expanded) next.add(modelId)
  else next.delete(modelId)
  expandedRouteModelIds.value = next
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
    current?.modelId === modelId &&
    current.operation === operation
  )
}

async function load(): Promise<void> {
  loadController?.abort()
  const controller = new AbortController()
  loadController = controller
  const generation = ++loadGeneration
  const startingRevision = stateRevision
  loading.value = models.value.length === 0
  routesLoading.value = true
  try {
    if (!auth.isAdmin) {
      const loadedModels = await listAvailableModels(controller.signal)
      if (!mounted || controller.signal.aborted || generation !== loadGeneration) return
      models.value = loadedModels
      providers.value = []
      allRoutes.value = []
      selectedModelIds.value = new Set()
      priceComparisonOpen.value = false
      catalogReady.value = true
      loadError.value = ''
      return
    }
    const [loadedModels, loadedProviders, loadedRoutes] = await Promise.all([
      listModels(controller.signal),
      listProviders(controller.signal),
      listModelRoutes({}, controller.signal),
    ])
    if (!mounted || controller.signal.aborted || generation !== loadGeneration) return
    providers.value = loadedProviders
    catalogReady.value = true
    if (startingRevision !== stateRevision) return
    models.value = loadedModels.filter((model) => !deletedModelIds.has(model.id))
    pruneSelectedModels()
    allRoutes.value = loadedRoutes.filter(
      (route) => !deletedRouteIds.has(route.id) && !deletedModelIds.has(route.model_id),
    )
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
    loadError.value = errorText(error, '模型列表加载失败')
  } finally {
    if (mounted && generation === loadGeneration) {
      loading.value = false
      routesLoading.value = false
    }
  }
}

function replaceModel(updated: ModelResponse): void {
  stateRevision += 1
  deletedModelIds.delete(updated.id)
  const index = models.value.findIndex((model) => model.id === updated.id)
  if (index === -1) models.value.push(updated)
  else models.value.splice(index, 1, updated)
}

function replaceRoute(updated: ModelRouteResponse): void {
  stateRevision += 1
  deletedRouteIds.delete(updated.id)
  const allIndex = allRoutes.value.findIndex((route) => route.id === updated.id)
  if (allIndex === -1) allRoutes.value.push(updated)
  else allRoutes.value.splice(allIndex, 1, updated)
}

function openCreateModel(): void {
  if (
    !catalogReady.value ||
    loading.value ||
    controlsLocked.value
  ) return
  modelDrawerSession += 1
  editingModel.value = null
  modelDrawerOpen.value = true
}

function openEditModel(model: ModelResponse): void {
  if (
    !catalogReady.value ||
    loading.value ||
    controlsLocked.value ||
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

function openCreateRouteForModel(modelId: number): void {
  const model = models.value.find((m) => m.id === modelId)
  if (
    !catalogReady.value ||
    loading.value ||
    model === undefined ||
    controlsLocked.value
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
    !catalogReady.value ||
    loading.value ||
    controlsLocked.value ||
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
    editingRoute.value?.id === routeId
  )
}

async function saveRoute(payload: ModelRouteCreate | ModelRouteUpdate): Promise<void> {
  const modelId = routeDrawerModelId.value
  if (
    routeSubmitting.value ||
    !routeDrawerOpen.value ||
    modelId === null ||
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
      routeDrawerSession === session
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
    controlsLocked.value ||
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
    deletedModelIds.add(model.id)
    models.value = models.value.filter((item) => item.id !== model.id)
    pruneSelectedModels()
    allRoutes.value = allRoutes.value.filter((route) => route.model_id !== model.id)
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
    controlsLocked.value ||
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

async function toggleModel(model: ModelResponse): Promise<void> {
  if (
    !catalogReady.value ||
    loading.value ||
    controlsLocked.value ||
    !beginModelOperation(model.id, 'toggle')
  ) return
  const controller = operationController()
  try {
    const updated = await updateModel(model.id, { enabled: !model.enabled }, controller.signal)
    if (updated.id !== model.id || !isCurrentModelOperation(controller, model.id, 'toggle')) return
    replaceModel(updated)
    modelNotice.value = {
      type: 'success',
      text: `模型“${updated.display_name}”已${updated.enabled ? '启用' : '停用'}`,
    }
  } catch (error: unknown) {
    if (isCurrentModelOperation(controller, model.id, 'toggle')) {
      modelNotice.value = { type: 'error', text: errorText(error, '模型状态更新失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentModelOperation(controller, model.id, 'toggle')) {
      finishModelOperation(model.id, 'toggle')
    }
  }
}

async function removeRoute(route: ModelRouteResponse): Promise<void> {
  const modelId = route.model_id
  if (
    !catalogReady.value ||
    loading.value ||
    controlsLocked.value ||
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
    deletedRouteIds.add(route.id)
    allRoutes.value = allRoutes.value.filter((item) => item.id !== route.id)
    routeNotice.value = {
      type: 'success',
      text: `路由“${route.upstream_model}”已删除`,
      modelId,
    }
  } catch (error: unknown) {
    if (!isCurrentRouteOperation(controller, route.id, modelId, 'delete')) return
    routeNotice.value = {
      type: 'error',
      text: errorText(error, '模型路由删除失败'),
      modelId,
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
    controlsLocked.value ||
    !allRoutes.value.some((route) => route.id === routeId && route.model_id === modelId) ||
    !beginRouteOperation(routeId, modelId, 'disable')
  ) return
  const controller = operationController()
  try {
    const updated = await updateModelRoute(routeId, { enabled: false }, controller.signal)
    if (
      updated.id !== routeId ||
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

async function recoverRoute(routeId: number, modelId: number): Promise<void> {
  if (
    !catalogReady.value ||
    loading.value ||
    controlsLocked.value ||
    !allRoutes.value.some((route) => route.id === routeId && route.model_id === modelId) ||
    !beginRouteOperation(routeId, modelId, 'recover')
  ) return
  const controller = operationController()
  try {
    const updated = await recoverModelRoute(routeId, controller.signal)
    if (
      updated.id !== routeId ||
      updated.model_id !== modelId ||
      !isCurrentRouteOperation(controller, routeId, modelId, 'recover')
    ) return
    replaceRoute(updated)
    routeNotice.value = {
      type: 'success',
      text: `路由“${updated.upstream_model}”已恢复`,
      modelId,
    }
  } catch (error: unknown) {
    if (isCurrentRouteOperation(controller, routeId, modelId, 'recover')) {
      routeNotice.value = {
        type: 'error',
        text: errorText(error, '模型路由恢复失败'),
        modelId,
      }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentRouteOperation(controller, routeId, modelId, 'recover')) {
      finishRouteOperation(routeId, modelId, 'recover')
    }
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  modelDrawerSession += 1
  routeDrawerSession += 1
  loadController?.abort()
  modelSaveController?.abort()
  routeSaveController?.abort()
  for (const controller of operationControllers) controller.abort()
  operationControllers.clear()
})
</script>

<template>
  <div class="route-page">
    <PageHeader
      :title="auth.isAdmin ? '模型管理' : '可用模型'"
      :description="auth.isAdmin ? '管理统一模型、调用别名与加权上游路由。' : '浏览当前可调用的模型、别名与计费价格。'"
    >
      <template v-if="auth.isAdmin" #actions>
        <ElButton
          data-test="price-comparison-open"
          :disabled="selectedModels.length < 2 || controlsLocked"
          @click="priceComparisonOpen = true"
        >
          价格比对（{{ selectedModels.length }}）
        </ElButton>
        <ElButton
          data-test="create-model"
          type="primary"
          :disabled="!catalogReady || loading || controlsLocked"
          @click="openCreateModel"
        >
          <ElIcon><Plus /></ElIcon>
          新建模型
        </ElButton>
      </template>
    </PageHeader>

    <div v-if="auth.isAdmin && modelNotice" data-test="model-notice" class="notice-row">
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
        :disabled="controlsLocked"
        @click="disableModel(modelNotice.conflictId)"
      >
        改为停用
      </ElButton>
    </div>

    <div v-if="auth.isAdmin && routeNotice" data-test="route-notice" class="notice-row">
      <ElAlert
        :type="routeNotice.type"
        :title="routeNotice.text"
        show-icon
        closable
        @close="routeNotice = null"
      />
    </div>

    <section class="model-panel page-card" aria-labelledby="model-list-heading">
      <div class="panel-toolbar">
        <div>
          <h2 id="model-list-heading">模型列表</h2>
          <p>共 {{ models.length }} 个模型</p>
        </div>
        <div class="toolbar-filters">
          <select
            v-if="auth.isAdmin"
            v-model="providerFilter"
            data-test="provider-filter"
            class="provider-filter-select"
            aria-label="按供应商筛选模型"
          >
            <option :value="null">全部供应商</option>
            <option
              v-for="provider in providers"
              :key="provider.id"
              :value="provider.id"
            >
              {{ provider.name }}
            </option>
          </select>
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
      </div>

      <div v-if="loading" class="loading-grid" aria-label="正在加载模型">
        <ElSkeleton v-for="index in 3" :key="index" animated>
          <template #template><ElSkeletonItem variant="rect" class="card-skeleton" /></template>
        </ElSkeleton>
      </div>

      <ElResult v-else-if="loadError" icon="error" title="模型列表加载失败" :sub-title="loadError">
        <template #extra><ElButton type="primary" @click="load">重新加载</ElButton></template>
      </ElResult>

      <div v-else-if="filteredModels.length > 0" class="resource-groups">
        <ResourceStatusGroup
          v-if="auth.isAdmin && availableModels.length > 0"
          data-test="available-model-group"
          status="enabled"
          title="可用"
          :count="availableModels.length"
        >
          <div class="models-grid">
            <ModelCard
              v-for="model in availableModels"
              :key="model.id"
              :data-test="`model-card-${String(model.id)}`"
              :model="model"
              :routes="routesByModel.get(model.id) ?? []"
              :providers="providers"
              :loading="controlsLocked"
              :routes-loading="routesLoading"
              :route-expansion="{ expanded: expandedRouteModelIds.has(model.id) }"
              :non-deletable="nonDeletableModelIds.has(model.id)"
              :readonly="!auth.isAdmin"
              selectable
              :selected="selectedModelIds.has(model.id)"
              @update:selected="setModelSelected(model.id, $event)"
              @edit="openEditModel"
              @delete="removeModel"
              @disable="disableModel"
              @toggle="toggleModel"
              @edit-route="openEditRoute"
              @delete-route="removeRoute"
              @disable-route="disableRoute"
              @recover-route="recoverRoute"
              @update:routes-expanded="setRoutesExpanded(model.id, $event)"
              @create-route="openCreateRouteForModel(model.id)"
            />
          </div>
        </ResourceStatusGroup>
        <ResourceStatusGroup
          v-if="auth.isAdmin && noUsableRouteModels.length > 0"
          data-test="no-usable-route-model-group"
          status="warning"
          title="无可用路由"
          :count="noUsableRouteModels.length"
        >
          <div class="models-grid">
            <ModelCard
              v-for="model in noUsableRouteModels"
              :key="model.id"
              :data-test="`model-card-${String(model.id)}`"
              :model="model"
              :routes="routesByModel.get(model.id) ?? []"
              :providers="providers"
              :loading="controlsLocked"
              :routes-loading="routesLoading"
              :route-expansion="{ expanded: expandedRouteModelIds.has(model.id) }"
              :non-deletable="nonDeletableModelIds.has(model.id)"
              :readonly="!auth.isAdmin"
              selectable
              :selected="selectedModelIds.has(model.id)"
              @update:selected="setModelSelected(model.id, $event)"
              @edit="openEditModel"
              @delete="removeModel"
              @disable="disableModel"
              @toggle="toggleModel"
              @edit-route="openEditRoute"
              @delete-route="removeRoute"
              @disable-route="disableRoute"
              @recover-route="recoverRoute"
              @update:routes-expanded="setRoutesExpanded(model.id, $event)"
              @create-route="openCreateRouteForModel(model.id)"
            />
          </div>
        </ResourceStatusGroup>
        <ResourceStatusGroup
          v-if="auth.isAdmin && unhealthyRouteModels.length > 0"
          data-test="unhealthy-route-model-group"
          status="danger"
          title="无健康路由"
          :count="unhealthyRouteModels.length"
        >
          <div class="models-grid">
            <ModelCard
              v-for="model in unhealthyRouteModels"
              :key="model.id"
              :data-test="`model-card-${String(model.id)}`"
              :model="model"
              :routes="routesByModel.get(model.id) ?? []"
              :providers="providers"
              :loading="controlsLocked"
              :routes-loading="routesLoading"
              :route-expansion="{ expanded: expandedRouteModelIds.has(model.id) }"
              :non-deletable="nonDeletableModelIds.has(model.id)"
              :readonly="!auth.isAdmin"
              selectable
              :selected="selectedModelIds.has(model.id)"
              @update:selected="setModelSelected(model.id, $event)"
              @edit="openEditModel"
              @delete="removeModel"
              @disable="disableModel"
              @toggle="toggleModel"
              @edit-route="openEditRoute"
              @delete-route="removeRoute"
              @disable-route="disableRoute"
              @recover-route="recoverRoute"
              @update:routes-expanded="setRoutesExpanded(model.id, $event)"
              @create-route="openCreateRouteForModel(model.id)"
            />
          </div>
        </ResourceStatusGroup>
        <ResourceStatusGroup
          v-if="auth.isAdmin && disabledModels.length > 0"
          data-test="disabled-model-group"
          status="disabled"
          title="已停用"
          :count="disabledModels.length"
        >
          <div class="models-grid">
            <ModelCard
              v-for="model in disabledModels"
              :key="model.id"
              :data-test="`model-card-${String(model.id)}`"
              :model="model"
              :routes="routesByModel.get(model.id) ?? []"
              :providers="providers"
              :loading="controlsLocked"
              :routes-loading="routesLoading"
              :route-expansion="{ expanded: expandedRouteModelIds.has(model.id) }"
              :non-deletable="nonDeletableModelIds.has(model.id)"
              :readonly="!auth.isAdmin"
              selectable
              :selected="selectedModelIds.has(model.id)"
              @update:selected="setModelSelected(model.id, $event)"
              @edit="openEditModel"
              @delete="removeModel"
              @disable="disableModel"
              @toggle="toggleModel"
              @edit-route="openEditRoute"
              @delete-route="removeRoute"
              @disable-route="disableRoute"
              @recover-route="recoverRoute"
              @update:routes-expanded="setRoutesExpanded(model.id, $event)"
              @create-route="openCreateRouteForModel(model.id)"
            />
          </div>
        </ResourceStatusGroup>
        <div v-if="!auth.isAdmin" class="models-grid">
          <ModelCard
            v-for="model in enabledModels"
            :key="model.id"
            :data-test="`model-card-${String(model.id)}`"
            :model="model"
            :routes="[]"
            :providers="[]"
            readonly
          />
        </div>
      </div>

      <ElEmpty
        v-else
        :description="searchText.trim() === '' && providerFilter === null ? '暂无模型' : '没有匹配的模型'"
      />
    </section>

    <ModelPriceComparisonDialog
      v-if="auth.isAdmin"
      v-model="priceComparisonOpen"
      :models="selectedModels"
      :routes="allRoutes"
      :providers="providers"
    />

    <ModelFormDrawer
      v-if="auth.isAdmin"
      :model-value="modelDrawerOpen"
      :model="editingModel"
      :submitting="modelSubmitting"
      @update:model-value="setModelDrawerOpen"
      @submit="saveModel"
    />
    <RouteFormDrawer
      v-if="auth.isAdmin"
      :model-value="routeDrawerOpen"
      :model="models.find((m) => m.id === routeDrawerModelId) ?? null"
      :route="editingRoute"
      :providers="providers"
      :submitting="routeSubmitting"
      @update:model-value="setRouteDrawerOpen"
      @submit="saveRoute"
    />
  </div>
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

.model-panel {
  overflow: hidden;
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

.toolbar-filters {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.provider-filter-select {
  width: 15rem;
  height: 2rem;
  padding: 0 0.5rem;
  border: 1px solid var(--gateway-border);
  border-radius: 4px;
  background: var(--gateway-panel);
  color: var(--gateway-text);
  font-size: 0.875rem;
  cursor: pointer;
}

.provider-filter-select:focus {
  outline: none;
  border-color: var(--gateway-brand);
}

.model-search {
  width: min(100%, 25rem);
}

.loading-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 0.75rem;
  padding: 1rem;
}

.card-skeleton {
  height: 220px;
}

.resource-groups {
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 0.75rem;
  align-items: start;
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

@media (max-width: 640px) {
  .panel-toolbar,
  .notice-row {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-filters {
    flex-direction: column;
  }

  .provider-filter,
  .model-search {
    width: 100%;
  }

  .loading-grid,
  .models-grid {
    grid-template-columns: 1fr;
  }

  .resource-groups {
    padding: 0.75rem;
  }
}
</style>
