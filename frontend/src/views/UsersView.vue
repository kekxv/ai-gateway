<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Delete, Edit, Money, Plus, Refresh, Search, Tickets } from '@element-plus/icons-vue'
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

import {
  adjustBalance,
  createUser,
  deleteUser,
  listLedger,
  listUsers,
  updateUser,
} from '@/api/users'
import { ApiError } from '@/api/client'
import type {
  BalanceAdjustmentCreate,
  LedgerEntryResponse,
  UserCreate,
  UserResponse,
  UserUpdate,
} from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import BalanceDialog from '@/components/users/BalanceDialog.vue'
import LedgerDrawer from '@/components/users/LedgerDrawer.vue'
import UserFormDrawer from '@/components/users/UserFormDrawer.vue'
import { useAuthStore } from '@/stores/auth'

type NoticeType = 'success' | 'warning' | 'error'
type UserOperation = 'edit' | 'adjust' | 'ledger' | 'delete'

const auth = useAuthStore()
const users = ref<UserResponse[]>([])
const searchText = ref('')
const loading = ref(true)
const loadError = ref('')
const notice = ref<{ type: NoticeType; text: string } | null>(null)

const formOpen = ref(false)
const editingUser = ref<UserResponse | null>(null)
const formSubmitting = ref(false)
const balanceOpen = ref(false)
const balanceUser = ref<UserResponse | null>(null)
const balanceSubmitting = ref(false)
const balanceRetryBlocked = ref(false)
const ledgerOpen = ref(false)
const ledgerUser = ref<UserResponse | null>(null)
const ledgerEntries = ref<LedgerEntryResponse[]>([])
const ledgerLoading = ref(false)
const ledgerError = ref('')

const userOperations = ref(new Map<number, UserOperation>())
const deletedIds = new Set<number>()
const operationControllers = new Set<AbortController>()
let loadController: AbortController | undefined
let formSaveController: AbortController | undefined
let balanceSaveController: AbortController | undefined
let ledgerController: AbortController | undefined
let mounted = true
let loadGeneration = 0
let stateRevision = 0
let formSession = 0
let balanceSession = 0
let ledgerSession = 0
let activeFormSave: symbol | undefined
let activeBalanceSave: symbol | undefined

const currentUserId = computed(() => auth.user?.id ?? null)
const filteredUsers = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase('zh-CN')
  if (query === '') return users.value
  return users.value.filter((user) =>
    [user.email, user.role, user.is_active ? '启用' : '停用'].some((value) =>
      value.toLocaleLowerCase('zh-CN').includes(query),
    ),
  )
})

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function beginUserOperation(userId: number, operation: UserOperation): boolean {
  if (userOperations.value.has(userId)) return false
  const next = new Map(userOperations.value)
  next.set(userId, operation)
  userOperations.value = next
  return true
}

function finishUserOperation(userId: number, operation: UserOperation): void {
  if (userOperations.value.get(userId) !== operation) return
  const next = new Map(userOperations.value)
  next.delete(userId)
  userOperations.value = next
}

function operationController(): AbortController {
  const controller = new AbortController()
  operationControllers.add(controller)
  return controller
}

function isCurrentOperation(
  controller: AbortController,
  userId: number,
  operation: UserOperation,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    userOperations.value.get(userId) === operation
  )
}

async function load(): Promise<void> {
  loadController?.abort()
  const controller = new AbortController()
  loadController = controller
  const generation = ++loadGeneration
  const startingRevision = stateRevision
  loading.value = users.value.length === 0
  try {
    const loadedUsers = await listUsers(controller.signal)
    if (!isCurrentLoad(controller, generation, startingRevision)) return
    users.value = loadedUsers.filter((user) => !deletedIds.has(user.id))
    loadError.value = ''
  } catch (error: unknown) {
    if (!isCurrentLoad(controller, generation, startingRevision)) return
    loadError.value = errorText(error, '用户列表加载失败')
  } finally {
    if (isCurrentLoadRequest(controller, generation)) loading.value = false
  }
}

function isCurrentLoadRequest(controller: AbortController, generation: number): boolean {
  return mounted && !controller.signal.aborted && generation === loadGeneration
}

function isCurrentLoad(
  controller: AbortController,
  generation: number,
  startingRevision: number,
): boolean {
  return isCurrentLoadRequest(controller, generation) && startingRevision === stateRevision
}

function replaceUser(updated: UserResponse): void {
  stateRevision += 1
  deletedIds.delete(updated.id)
  const index = users.value.findIndex((user) => user.id === updated.id)
  if (index === -1) users.value.push(updated)
  else users.value.splice(index, 1, updated)
}

function openCreate(): void {
  if (formSubmitting.value || formOpen.value) return
  formSession += 1
  editingUser.value = null
  formOpen.value = true
}

function openEdit(user: UserResponse): void {
  if (formSubmitting.value || formOpen.value || !beginUserOperation(user.id, 'edit')) return
  formSession += 1
  editingUser.value = user
  formOpen.value = true
}

function setFormOpen(open: boolean): void {
  if (open || formSubmitting.value) return
  const userId = editingUser.value?.id
  formSession += 1
  formOpen.value = false
  editingUser.value = null
  if (userId !== undefined) finishUserOperation(userId, 'edit')
}

function isCurrentFormSave(
  controller: AbortController,
  token: symbol,
  session: number,
  userId: number | undefined,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    activeFormSave === token &&
    formOpen.value &&
    formSession === session &&
    editingUser.value?.id === userId
  )
}

async function saveUser(payload: UserCreate | UserUpdate): Promise<void> {
  if (formSubmitting.value || !formOpen.value) return
  const userId = editingUser.value?.id
  const isCreate = userId === undefined
  const session = formSession
  const token = Symbol('user-save')
  const controller = new AbortController()
  formSaveController?.abort()
  formSaveController = controller
  activeFormSave = token
  formSubmitting.value = true
  try {
    const updated = isCreate
      ? await createUser(payload as UserCreate, controller.signal)
      : await updateUser(userId, payload, controller.signal)
    if (!isCurrentFormSave(controller, token, session, userId)) return
    if (!isCreate && updated.id !== userId) return
    replaceUser(updated)
    formSession += 1
    formOpen.value = false
    editingUser.value = null
    if (userId !== undefined) finishUserOperation(userId, 'edit')
    notice.value = { type: 'success', text: isCreate ? '用户已创建' : '用户设置已保存' }
  } catch (error: unknown) {
    if (
      mounted &&
      !controller.signal.aborted &&
      activeFormSave === token &&
      formSession === session
    ) {
      notice.value = { type: 'error', text: errorText(error, '用户保存失败') }
    }
  } finally {
    if (activeFormSave === token) {
      activeFormSave = undefined
      formSaveController = undefined
      if (mounted) formSubmitting.value = false
    }
  }
}

function openBalance(user: UserResponse): void {
  if (balanceSubmitting.value || balanceOpen.value || !beginUserOperation(user.id, 'adjust')) return
  balanceSession += 1
  balanceRetryBlocked.value = false
  balanceUser.value = user
  balanceOpen.value = true
}

function setBalanceOpen(open: boolean): void {
  if (open || balanceSubmitting.value) return
  const userId = balanceUser.value?.id
  balanceSession += 1
  balanceOpen.value = false
  balanceUser.value = null
  balanceRetryBlocked.value = false
  if (userId !== undefined) finishUserOperation(userId, 'adjust')
}

function isCurrentBalanceSave(
  controller: AbortController,
  token: symbol,
  session: number,
  userId: number,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    activeBalanceSave === token &&
    balanceOpen.value &&
    balanceSession === session &&
    balanceUser.value?.id === userId &&
    userOperations.value.get(userId) === 'adjust'
  )
}

async function saveBalance(payload: BalanceAdjustmentCreate): Promise<void> {
  const user = balanceUser.value
  if (
    balanceSubmitting.value ||
    balanceRetryBlocked.value ||
    !balanceOpen.value ||
    user === null
  ) return
  const userId = user.id
  const session = balanceSession
  const token = Symbol('balance-save')
  const controller = new AbortController()
  balanceSaveController?.abort()
  balanceSaveController = controller
  activeBalanceSave = token
  balanceSubmitting.value = true
  try {
    const result = await adjustBalance(userId, payload, controller.signal)
    if (!isCurrentBalanceSave(controller, token, session, userId)) return
    replaceUserMoney(userId, result.balance, result.total_spent)
    balanceSession += 1
    balanceOpen.value = false
    balanceUser.value = null
    finishUserOperation(userId, 'adjust')
    notice.value = {
      type: 'success',
      text: `余额调整成功：当前余额 ${result.balance}，累计消费 ${result.total_spent}`,
    }
  } catch (error: unknown) {
    if (isCurrentBalanceSave(controller, token, session, userId)) {
      if (error instanceof ApiError && error.code === 'idempotency_conflict') {
        balanceRetryBlocked.value = true
        notice.value = {
          type: 'warning',
          text: '幂等键冲突：请关闭调账对话框并刷新用户列表核对余额，不要直接重试。',
        }
      } else {
        notice.value = { type: 'error', text: errorText(error, '余额调整失败') }
      }
    }
  } finally {
    if (activeBalanceSave === token) {
      activeBalanceSave = undefined
      balanceSaveController = undefined
      if (mounted) balanceSubmitting.value = false
    }
  }
}

function replaceUserMoney(userId: number, balance: string, totalSpent: string): void {
  const index = users.value.findIndex((candidate) => candidate.id === userId)
  if (index === -1) return
  stateRevision += 1
  const current = users.value[index]
  if (current === undefined) return
  users.value.splice(index, 1, { ...current, balance, total_spent: totalSpent })
}

function openLedger(user: UserResponse): void {
  if (ledgerOpen.value || !beginUserOperation(user.id, 'ledger')) return
  ledgerSession += 1
  const session = ledgerSession
  ledgerUser.value = user
  ledgerEntries.value = []
  ledgerError.value = ''
  ledgerLoading.value = true
  ledgerOpen.value = true
  ledgerController?.abort()
  const controller = operationController()
  ledgerController = controller
  void listLedger(user.id, controller.signal)
    .then((entries) => {
      if (!isCurrentLedger(controller, user.id, session)) return
      ledgerEntries.value = entries
      ledgerError.value = ''
    })
    .catch((error: unknown) => {
      if (!isCurrentLedger(controller, user.id, session)) return
      ledgerError.value = errorText(error, '账本加载失败')
    })
    .finally(() => {
      operationControllers.delete(controller)
      if (isCurrentLedger(controller, user.id, session)) ledgerLoading.value = false
    })
}

function isCurrentLedger(
  controller: AbortController,
  userId: number,
  session: number,
): boolean {
  return (
    ledgerController === controller &&
    isCurrentOperation(controller, userId, 'ledger') &&
    ledgerOpen.value &&
    ledgerSession === session &&
    ledgerUser.value?.id === userId
  )
}

function setLedgerOpen(open: boolean): void {
  if (open) return
  const userId = ledgerUser.value?.id
  ledgerSession += 1
  ledgerController?.abort()
  ledgerController = undefined
  ledgerOpen.value = false
  ledgerUser.value = null
  ledgerEntries.value = []
  ledgerError.value = ''
  ledgerLoading.value = false
  if (userId !== undefined) finishUserOperation(userId, 'ledger')
}

async function removeUser(user: UserResponse): Promise<void> {
  if (user.id === currentUserId.value || !beginUserOperation(user.id, 'delete')) return
  const controller = operationController()
  try {
    await ElMessageBox.confirm(
      `确定删除用户“${user.email}”吗？该操作会同时删除其账号数据，且无法撤销。`,
      '删除用户',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    operationControllers.delete(controller)
    if (isCurrentOperation(controller, user.id, 'delete')) {
      finishUserOperation(user.id, 'delete')
    }
    return
  }
  if (!isCurrentOperation(controller, user.id, 'delete')) {
    operationControllers.delete(controller)
    return
  }

  try {
    await deleteUser(user.id, controller.signal)
    if (!isCurrentOperation(controller, user.id, 'delete')) return
    stateRevision += 1
    deletedIds.add(user.id)
    users.value = users.value.filter((item) => item.id !== user.id)
    notice.value = { type: 'success', text: `用户“${user.email}”已删除` }
  } catch (error: unknown) {
    if (isCurrentOperation(controller, user.id, 'delete')) {
      notice.value = { type: 'error', text: errorText(error, '用户删除失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentOperation(controller, user.id, 'delete')) {
      finishUserOperation(user.id, 'delete')
    }
  }
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
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
  formSession += 1
  balanceSession += 1
  ledgerSession += 1
  loadController?.abort()
  formSaveController?.abort()
  balanceSaveController?.abort()
  ledgerController?.abort()
  for (const controller of operationControllers) controller.abort()
  operationControllers.clear()
})
</script>

<template>
  <PageHeader title="用户管理" description="管理用户账号、精确余额、累计消费与不可变账本。">
    <template #actions>
      <ElButton data-test="create-user" type="primary" @click="openCreate">
        <ElIcon><Plus /></ElIcon>
        新建用户
      </ElButton>
    </template>
  </PageHeader>

  <ElAlert
    v-if="notice !== null"
    data-test="user-notice"
    class="notice"
    :title="notice.text"
    :type="notice.type"
    show-icon
    @close="notice = null"
  />

  <section class="user-panel" aria-labelledby="user-list-title">
    <div class="panel-toolbar">
      <div>
        <h2 id="user-list-title">用户列表</h2>
        <p>共 {{ users.length }} 个用户</p>
      </div>
      <div class="toolbar-actions">
        <ElInput
          v-model="searchText"
          data-test="user-search"
          clearable
          placeholder="搜索邮箱、角色或状态"
        >
          <template #prefix><ElIcon><Search /></ElIcon></template>
        </ElInput>
        <ElButton :loading="loading" aria-label="刷新用户列表" @click="load">
          <ElIcon><Refresh /></ElIcon>
        </ElButton>
      </div>
    </div>

    <ElResult v-if="loadError !== ''" icon="error" title="用户列表加载失败" :sub-title="loadError">
      <template #extra><ElButton type="primary" @click="load">重新加载</ElButton></template>
    </ElResult>
    <ElSkeleton v-else-if="loading" animated>
      <template #template><ElSkeletonItem variant="rect" class="table-skeleton" /></template>
    </ElSkeleton>
    <ElEmpty v-else-if="filteredUsers.length === 0" description="暂无匹配用户" />
    <div v-else class="table-scroll">
      <table class="user-table">
        <thead>
          <tr>
            <th>邮箱</th><th>角色</th><th>状态</th><th>余额</th><th>累计消费</th>
            <th>创建时间</th><th>更新时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in filteredUsers" :key="user.id">
            <td><strong>{{ user.email }}</strong></td>
            <td>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</td>
            <td>
              <ElTag :type="user.is_active ? 'success' : 'info'" effect="light">
                {{ user.is_active ? '启用' : '停用' }}
              </ElTag>
            </td>
            <td class="money-cell">{{ user.balance }}</td>
            <td class="money-cell">{{ user.total_spent }}</td>
            <td>{{ formatTime(user.created_at) }}</td>
            <td>{{ formatTime(user.updated_at) }}</td>
            <td>
              <div class="row-actions">
                <ElButton
                  :data-test="`edit-user-${String(user.id)}`"
                  size="small"
                  :disabled="userOperations.has(user.id)"
                  @click="openEdit(user)"
                ><ElIcon><Edit /></ElIcon>编辑</ElButton>
                <ElButton
                  :data-test="`adjust-user-${String(user.id)}`"
                  size="small"
                  :disabled="userOperations.has(user.id)"
                  @click="openBalance(user)"
                ><ElIcon><Money /></ElIcon>调账</ElButton>
                <ElButton
                  :data-test="`ledger-user-${String(user.id)}`"
                  size="small"
                  :disabled="userOperations.has(user.id)"
                  @click="openLedger(user)"
                ><ElIcon><Tickets /></ElIcon>账本</ElButton>
                <ElButton
                  :data-test="`delete-user-${String(user.id)}`"
                  size="small"
                  type="danger"
                  plain
                  :title="user.id === currentUserId ? '不能删除当前登录管理员' : undefined"
                  :disabled="user.id === currentUserId || userOperations.has(user.id)"
                  @click="removeUser(user)"
                ><ElIcon><Delete /></ElIcon>删除</ElButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <UserFormDrawer
    :model-value="formOpen"
    :user="editingUser"
    :submitting="formSubmitting"
    :current-user-id="currentUserId"
    @submit="saveUser"
    @update:model-value="setFormOpen"
  />
  <BalanceDialog
    :model-value="balanceOpen"
    :user="balanceUser"
    :submitting="balanceSubmitting"
    :retry-blocked="balanceRetryBlocked"
    @submit="saveBalance"
    @update:model-value="setBalanceOpen"
  />
  <LedgerDrawer
    :model-value="ledgerOpen"
    :user="ledgerUser"
    :entries="ledgerEntries"
    :loading="ledgerLoading"
    :error="ledgerError"
    @update:model-value="setLedgerOpen"
  />
</template>

<style scoped>
.notice {
  margin-bottom: 1rem;
}

.user-panel {
  overflow: hidden;
  background: var(--gateway-panel);
  border: 1px solid var(--gateway-border);
  border-radius: 0.9rem;
  box-shadow: var(--gateway-shadow);
}

.panel-toolbar {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.15rem;
  border-bottom: 1px solid var(--gateway-border);
}

.panel-toolbar h2,
.panel-toolbar p {
  margin: 0;
}

.panel-toolbar h2 {
  font-size: 1.05rem;
}

.panel-toolbar p {
  margin-top: 0.2rem;
  color: var(--gateway-muted);
  font-size: 0.8rem;
}

.toolbar-actions,
.row-actions {
  display: flex;
  gap: 0.5rem;
}

.toolbar-actions :deep(.el-input) {
  width: min(20rem, 48vw);
}

.table-scroll {
  overflow-x: auto;
}

.user-table {
  width: 100%;
  min-width: 84rem;
  border-collapse: collapse;
}

.user-table th,
.user-table td {
  padding: 0.85rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--gateway-border);
  white-space: nowrap;
}

.user-table th {
  color: var(--gateway-muted);
  font-size: 0.78rem;
  font-weight: 600;
  background: rgb(248 250 252 / 72%);
}

.user-table tbody tr:last-child td {
  border-bottom: 0;
}

.money-cell {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.table-skeleton {
  height: 18rem;
  margin: 1rem;
}

@media (max-width: 767px) {
  .panel-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-actions :deep(.el-input) {
    width: 100%;
  }
}
</style>
