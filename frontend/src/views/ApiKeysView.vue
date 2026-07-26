<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Delete, Document, Edit, Key, Plus, Refresh, Search } from '@element-plus/icons-vue'
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
  ElTabPane,
  ElTabs,
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
import 'element-plus/theme-chalk/el-tabs.css'
import 'element-plus/theme-chalk/el-tag.css'

import {
  createApiKey,
  deleteApiKey,
  listApiKeys,
  rotateApiKey,
  updateApiKey,
} from '@/api/apiKeys'
import { ApiError } from '@/api/client'
import { listModels } from '@/api/models'
import { listProviders } from '@/api/providers'
import type {
  ApiKeyCreate,
  ApiKeyResponse,
  ApiKeyScope,
  ApiKeyUpdate,
  ModelResponse,
  ProviderResponse,
  UserResponse,
} from '@/api/types'
import { listUsers } from '@/api/users'
import ApiKeyFormDrawer from '@/components/api-keys/ApiKeyFormDrawer.vue'
import SecretResultDialog from '@/components/api-keys/SecretResultDialog.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { formatDateTime } from '@/utils/format'

type NoticeType = 'success' | 'warning' | 'error'
type KeyOperation = 'edit' | 'rotate' | 'delete'

const apiKeys = ref<ApiKeyResponse[]>([])
const users = ref<UserResponse[]>([])
const providers = ref<ProviderResponse[]>([])
const models = ref<ModelResponse[]>([])
const searchText = ref('')
const loading = ref(true)
const loadError = ref('')
const notice = ref<{ type: NoticeType; text: string } | null>(null)

const formOpen = ref(false)
const editingApiKey = ref<ApiKeyResponse | null>(null)
const formSubmitting = ref(false)
const secretOpen = ref(false)
const oneTimeSecret = ref<string | null>(null)
const secretOperationActive = ref(false)
const keyOperations = ref(new Map<number, KeyOperation>())
const examplesOpen = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const examplesTab = ref<any>('openai')

const baseUrl = window.location.origin

const deletedIds = new Set<number>()
const operationControllers = new Set<AbortController>()
let loadController: AbortController | undefined
let saveController: AbortController | undefined
let mounted = true
let loadGeneration = 0
let stateRevision = 0
let formSession = 0
let activeSaveToken: symbol | undefined
let activeSecretLifecycle: symbol | undefined
let dialogSecretLifecycle: symbol | undefined

const scopeLabels: Readonly<Record<ApiKeyScope, string>> = {
  all: '全部',
  providers: '指定供应商',
  models: '指定模型',
  providers_and_models: '指定供应商和模型',
}

const testApiKey = ref('')
const testMessage = ref('你好，请用一句话介绍自己。')
const testModel = ref('')
const testChatLoading = ref(false)
const testChatResult = ref<{ success: boolean; message: string } | null>(null)
let testChatController: AbortController | null = null

const availableModelNames = computed(() =>
  models.value.map((m) => m.canonical_name),
)

const curlExamples = computed(() => {
  const key = testApiKey.value.trim() || 'sk-gw-YOUR_API_KEY'
  const base = baseUrl
  const model = testModel.value || 'gpt-4'
  const message = testMessage.value || 'Hello!'
  const escapedMessage = message.replace(/'/g, "\\'")

  return {
    openai: `curl "${base}/v1/chat/completions" \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "${escapedMessage}"}],
    "max_tokens": 100
  }'`,
    claude: `curl "${base}/v1/messages" \\
  -H "x-api-key: ${key}" \\
  -H "anthropic-version: 2023-06-01" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${model}",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "${escapedMessage}"}]
  }'`,
    gemini: `curl "${base}/v1beta/models/${model}:generateContent" \\
  -H "x-goog-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "contents": [{"parts": [{"text": "${escapedMessage}"}]}]
  }'`,
    websocket: `# OpenAI Realtime WebSocket (使用 websocat)
websocat -H="Authorization: Bearer ${key}" \\
  -H="Sec-WebSocket-Protocol: realtime" \\
  "${base.replace('http', 'ws')}/v1/realtime?model=${model}"

# Gemini Live WebSocket
websocat -H="x-goog-api-key: ${key}" \\
  -H="Sec-WebSocket-Protocol: gemini-live" \\
  "${base.replace('http', 'ws')}/v1beta/live"`,
  }
})

const copyStatus = ref('')

async function copyCurlExample(protocol: string): Promise<void> {
  const example = curlExamples.value[protocol as keyof typeof curlExamples.value]
  if (!example) return
  try {
    await navigator.clipboard.writeText(example)
    copyStatus.value = `${protocol.toUpperCase()} 示例已复制`
    setTimeout(() => { copyStatus.value = '' }, 2000)
  } catch {
    copyStatus.value = '复制失败'
  }
}

async function testChat(): Promise<void> {
  const key = testApiKey.value.trim()
  if (!key) {
    testChatResult.value = { success: false, message: '请先输入 API 密钥' }
    return
  }
  const message = testMessage.value.trim()
  if (!message) {
    testChatResult.value = { success: false, message: '请输入消息内容' }
    return
  }
  const model = testModel.value.trim() || 'gpt-4'

  testChatController?.abort()
  const controller = new AbortController()
  testChatController = controller
  testChatLoading.value = true
  testChatResult.value = null

  let collected = ''

  try {
    const response = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${key}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: message }],
        max_tokens: 500,
        stream: true,
      }),
      signal: controller.signal,
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => null)
      const errorMsg = errorData?.detail ?? errorData?.error?.message ?? `HTTP ${response.status}`
      testChatResult.value = { success: false, message: `请求失败：${errorMsg}` }
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      testChatResult.value = { success: false, message: '响应不支持流式读取' }
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let usedModel = model

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed === '' || trimmed === 'data: [DONE]') continue
        if (!trimmed.startsWith('data: ')) continue

        try {
          const json = JSON.parse(trimmed.slice(6))
          if (json.model) usedModel = json.model
          const delta =
            json.choices?.[0]?.delta?.content ??
            json.choices?.[0]?.message?.content ??
            ''
          if (typeof delta === 'string' && delta.length > 0) {
            collected += delta

            // Show partial result as streaming arrives
            testChatResult.value = {
              success: true,
              message: collected,
            }
          }
        } catch {
          // ignore malformed SSE lines
        }
      }
    }

    if (collected === '') {
      testChatResult.value = { success: false, message: '未收到响应内容' }
    } else {
      copyStatus.value = `使用模型：${usedModel}`
      setTimeout(() => { copyStatus.value = '' }, 3000)
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (collected.length > 0) {
        testChatResult.value = {
          success: true,
          message: `${collected}\n\n（已手动停止）`,
        }
      } else {
        testChatResult.value = { success: false, message: '请求已取消' }
      }
    } else {
      testChatResult.value = {
        success: false,
        message: `网络错误：${error instanceof Error ? error.message : '未知错误'}`,
      }
    }
  } finally {
    testChatController = null
    testChatLoading.value = false
  }
}

function stopTestChat(): void {
  testChatController?.abort()
}

const ownerEmails = computed(
  () => new Map(users.value.map((user) => [user.id, user.email] as const)),
)
const filteredApiKeys = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase('zh-CN')
  if (query === '') return apiKeys.value
  return apiKeys.value.filter((apiKey) =>
    [
      apiKey.name,
      apiKey.key_prefix,
      ownerEmail(apiKey.user_id),
      scopeLabels[apiKey.scope],
      apiKey.is_active ? '启用' : '停用',
    ].some((value) => value.toLocaleLowerCase('zh-CN').includes(query)),
  )
})

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function ownerEmail(userId: number): string {
  return ownerEmails.value.get(userId) ?? `用户 #${String(userId)}`
}

async function load(): Promise<void> {
  loadController?.abort()
  const controller = new AbortController()
  loadController = controller
  const generation = ++loadGeneration
  const startingRevision = stateRevision
  loading.value = apiKeys.value.length === 0
  try {
    const [loadedKeys, loadedUsers, loadedProviders, loadedModels] = await Promise.all([
      listApiKeys(undefined, controller.signal),
      listUsers(controller.signal),
      listProviders(controller.signal),
      listModels(controller.signal),
    ])
    if (!isCurrentLoad(controller, generation, startingRevision)) return
    apiKeys.value = loadedKeys.filter((apiKey) => !deletedIds.has(apiKey.id))
    users.value = loadedUsers
    providers.value = loadedProviders
    models.value = loadedModels
    loadError.value = ''
  } catch (error: unknown) {
    if (!isCurrentLoad(controller, generation, startingRevision)) return
    loadError.value = errorText(error, '接口密钥列表加载失败')
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

function replaceApiKey(updated: ApiKeyResponse): void {
  stateRevision += 1
  deletedIds.delete(updated.id)
  const index = apiKeys.value.findIndex((apiKey) => apiKey.id === updated.id)
  if (index === -1) apiKeys.value.push(updated)
  else apiKeys.value.splice(index, 1, updated)
}

function replaceRotatedApiKey(oldId: number, replacement: ApiKeyResponse): void {
  stateRevision += 1
  deletedIds.add(oldId)
  deletedIds.delete(replacement.id)
  const oldIndex = apiKeys.value.findIndex((apiKey) => apiKey.id === oldId)
  if (oldIndex === -1) apiKeys.value.push(replacement)
  else apiKeys.value.splice(oldIndex, 1, replacement)
}

function beginKeyOperation(apiKeyId: number, operation: KeyOperation): boolean {
  if (keyOperations.value.has(apiKeyId)) return false
  const next = new Map(keyOperations.value)
  next.set(apiKeyId, operation)
  keyOperations.value = next
  return true
}

function finishKeyOperation(apiKeyId: number, operation: KeyOperation): void {
  if (keyOperations.value.get(apiKeyId) !== operation) return
  const next = new Map(keyOperations.value)
  next.delete(apiKeyId)
  keyOperations.value = next
}

function operationController(): AbortController {
  const controller = new AbortController()
  operationControllers.add(controller)
  return controller
}

function isCurrentOperation(
  controller: AbortController,
  apiKeyId: number,
  operation: KeyOperation,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    keyOperations.value.get(apiKeyId) === operation
  )
}

function acquireSecretLifecycle(): symbol | undefined {
  if (activeSecretLifecycle !== undefined) return undefined
  const token = Symbol('secret-lifecycle')
  activeSecretLifecycle = token
  secretOperationActive.value = true
  return token
}

function releaseSecretLifecycle(token: symbol): void {
  if (activeSecretLifecycle !== token) return
  activeSecretLifecycle = undefined
  secretOperationActive.value = false
}

function openCreate(): void {
  if (
    formSubmitting.value ||
    formOpen.value ||
    secretOpen.value ||
    secretOperationActive.value
  ) return
  formSession += 1
  editingApiKey.value = null
  formOpen.value = true
}

function openEdit(apiKey: ApiKeyResponse): void {
  if (
    formSubmitting.value ||
    formOpen.value ||
    secretOpen.value ||
    !beginKeyOperation(apiKey.id, 'edit')
  ) return
  formSession += 1
  editingApiKey.value = apiKey
  formOpen.value = true
}

function setFormOpen(open: boolean): void {
  if (open || formSubmitting.value) return
  const apiKeyId = editingApiKey.value?.id
  formSession += 1
  formOpen.value = false
  editingApiKey.value = null
  if (apiKeyId !== undefined) finishKeyOperation(apiKeyId, 'edit')
}

function isCurrentSave(
  controller: AbortController,
  token: symbol,
  session: number,
  apiKeyId: number | undefined,
): boolean {
  return (
    mounted &&
    !controller.signal.aborted &&
    activeSaveToken === token &&
    formOpen.value &&
    formSession === session &&
    editingApiKey.value?.id === apiKeyId
  )
}

async function saveApiKey(payload: ApiKeyCreate | ApiKeyUpdate): Promise<void> {
  if (formSubmitting.value || !formOpen.value || secretOpen.value) return
  const apiKeyId = editingApiKey.value?.id
  const isCreate = apiKeyId === undefined
  if (!isCreate && Object.keys(payload).length === 0) {
    setFormOpen(false)
    return
  }
  const secretLifecycle = isCreate ? acquireSecretLifecycle() : undefined
  if (isCreate && secretLifecycle === undefined) {
    notice.value = { type: 'warning', text: '请先完成当前密钥创建或轮换操作' }
    return
  }
  const session = formSession
  const token = Symbol('api-key-save')
  const controller = new AbortController()
  saveController?.abort()
  saveController = controller
  activeSaveToken = token
  formSubmitting.value = true
  let keepSecretLifecycleForDialog = false
  try {
    if (isCreate) {
      const created = await createApiKey(payload as ApiKeyCreate, controller.signal)
      if (!isCurrentSave(controller, token, session, apiKeyId)) return
      const { key, ...metadata } = created
      replaceApiKey(metadata)
      formSession += 1
      formOpen.value = false
      editingApiKey.value = null
      oneTimeSecret.value = key
      dialogSecretLifecycle = secretLifecycle
      secretOpen.value = true
      keepSecretLifecycleForDialog = true
      notice.value = { type: 'success', text: '接口密钥已创建，请立即安全保存' }
    } else {
      const updated = await updateApiKey(apiKeyId, payload, controller.signal)
      if (!isCurrentSave(controller, token, session, apiKeyId) || updated.id !== apiKeyId) return
      replaceApiKey(updated)
      formSession += 1
      formOpen.value = false
      editingApiKey.value = null
      finishKeyOperation(apiKeyId, 'edit')
      notice.value = { type: 'success', text: '接口密钥设置已保存' }
    }
  } catch (error: unknown) {
    if (isCurrentSave(controller, token, session, apiKeyId)) {
      notice.value = { type: 'error', text: errorText(error, '接口密钥保存失败') }
    }
  } finally {
    if (activeSaveToken === token) {
      activeSaveToken = undefined
      saveController = undefined
      if (mounted) formSubmitting.value = false
    }
    if (secretLifecycle !== undefined && !keepSecretLifecycleForDialog) {
      releaseSecretLifecycle(secretLifecycle)
    }
  }
}

function closeSecret(): void {
  const secretLifecycle = dialogSecretLifecycle
  oneTimeSecret.value = null
  secretOpen.value = false
  dialogSecretLifecycle = undefined
  if (secretLifecycle !== undefined) releaseSecretLifecycle(secretLifecycle)
}

async function rotate(apiKey: ApiKeyResponse): Promise<void> {
  if (secretOpen.value || secretOperationActive.value) return
  const secretLifecycle = acquireSecretLifecycle()
  if (secretLifecycle === undefined) return
  if (!beginKeyOperation(apiKey.id, 'rotate')) {
    releaseSecretLifecycle(secretLifecycle)
    return
  }
  const controller = operationController()
  try {
    await ElMessageBox.confirm(
      `确定轮换密钥“${apiKey.name}”吗？旧密钥将立即停用，所有使用方必须改用新密钥。`,
      '轮换接口密钥',
      { confirmButtonText: '确认轮换', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    operationControllers.delete(controller)
    if (isCurrentOperation(controller, apiKey.id, 'rotate')) {
      finishKeyOperation(apiKey.id, 'rotate')
    }
    releaseSecretLifecycle(secretLifecycle)
    return
  }
  if (!isCurrentOperation(controller, apiKey.id, 'rotate')) {
    operationControllers.delete(controller)
    releaseSecretLifecycle(secretLifecycle)
    return
  }

  let keepSecretLifecycleForDialog = false
  try {
    const rotated = await rotateApiKey(apiKey.id, controller.signal)
    if (!isCurrentOperation(controller, apiKey.id, 'rotate')) return
    const { key, ...metadata } = rotated
    replaceRotatedApiKey(apiKey.id, metadata)
    oneTimeSecret.value = key
    dialogSecretLifecycle = secretLifecycle
    secretOpen.value = true
    keepSecretLifecycleForDialog = true
    notice.value = { type: 'success', text: '密钥已轮换，旧密钥已停用，请立即保存新密钥' }
  } catch (error: unknown) {
    if (!isCurrentOperation(controller, apiKey.id, 'rotate')) return
    if (error instanceof ApiError && error.code === 'api_key_inactive') {
      await load()
      if (isCurrentOperation(controller, apiKey.id, 'rotate')) {
        notice.value = { type: 'warning', text: '只有启用中的密钥可以轮换，列表已刷新' }
      }
    } else {
      notice.value = { type: 'error', text: errorText(error, '接口密钥轮换失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentOperation(controller, apiKey.id, 'rotate')) {
      finishKeyOperation(apiKey.id, 'rotate')
    }
    if (!keepSecretLifecycleForDialog) releaseSecretLifecycle(secretLifecycle)
  }
}

async function remove(apiKey: ApiKeyResponse): Promise<void> {
  if (secretOpen.value || !beginKeyOperation(apiKey.id, 'delete')) return
  const controller = operationController()
  try {
    await ElMessageBox.confirm(
      `确定删除密钥“${apiKey.name}”吗？使用此密钥的请求将立即失败，且无法撤销。`,
      '删除接口密钥',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    operationControllers.delete(controller)
    if (isCurrentOperation(controller, apiKey.id, 'delete')) {
      finishKeyOperation(apiKey.id, 'delete')
    }
    return
  }
  if (!isCurrentOperation(controller, apiKey.id, 'delete')) {
    operationControllers.delete(controller)
    return
  }

  try {
    await deleteApiKey(apiKey.id, controller.signal)
    if (!isCurrentOperation(controller, apiKey.id, 'delete')) return
    stateRevision += 1
    deletedIds.add(apiKey.id)
    apiKeys.value = apiKeys.value.filter((item) => item.id !== apiKey.id)
    notice.value = { type: 'success', text: `接口密钥“${apiKey.name}”已删除` }
  } catch (error: unknown) {
    if (isCurrentOperation(controller, apiKey.id, 'delete')) {
      notice.value = { type: 'error', text: errorText(error, '接口密钥删除失败') }
    }
  } finally {
    operationControllers.delete(controller)
    if (isCurrentOperation(controller, apiKey.id, 'delete')) {
      finishKeyOperation(apiKey.id, 'delete')
    }
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  formSession += 1
  oneTimeSecret.value = null
  secretOpen.value = false
  dialogSecretLifecycle = undefined
  activeSecretLifecycle = undefined
  secretOperationActive.value = false
  loadController?.abort()
  saveController?.abort()
  testChatController?.abort()
  for (const controller of operationControllers) controller.abort()
  operationControllers.clear()
})
</script>

<template>
  <PageHeader title="接口密钥" description="管理用户密钥、访问作用域、有效期与安全轮换。">
    <template #actions>
      <ElButton
        data-test="toggle-examples"
        :type="examplesOpen ? 'info' : 'default'"
        @click="examplesOpen = !examplesOpen"
      >
        <ElIcon><Document /></ElIcon>
        {{ examplesOpen ? '隐藏示例' : '使用示例' }}
      </ElButton>
      <ElButton
        data-test="create-api-key"
        type="primary"
        :disabled="secretOpen || secretOperationActive"
        @click="openCreate"
      >
        <ElIcon><Plus /></ElIcon>
        新建密钥
      </ElButton>
    </template>
  </PageHeader>

  <section v-if="examplesOpen" class="examples-panel page-card">
    <div class="examples-header">
      <h3>API 使用示例</h3>
      <p>输入你的 API 密钥，示例命令会自动更新</p>
    </div>
    <div class="test-input-grid">
      <div class="test-input-row">
        <ElInput
          v-model="testApiKey"
          placeholder="sk-gw-..."
          clearable
          type="password"
          show-password
        >
          <template #prepend>API 密钥</template>
        </ElInput>
      </div>
      <div class="test-input-row test-input-row--split">
        <ElInput
          v-model="testModel"
          placeholder="gpt-4（留空使用默认）"
          clearable
          class="test-model-input"
        >
          <template #prepend>模型</template>
          <template #append>
            <select v-model="testModel" class="model-pick-select">
              <option value="">从列表选择...</option>
              <option v-for="name in availableModelNames" :key="name" :value="name">
                {{ name }}
              </option>
            </select>
          </template>
        </ElInput>
        <ElButton
          v-if="!testChatLoading"
          type="primary"
          :disabled="!testApiKey.trim() || !testMessage.trim()"
          @click="testChat"
        >
          测试聊天
        </ElButton>
        <ElButton
          v-else
          type="danger"
          @click="stopTestChat"
        >
          停止
        </ElButton>
      </div>
      <div class="test-input-row">
        <ElInput
          v-model="testMessage"
          type="textarea"
          :rows="2"
          placeholder="输入要测试的消息..."
          maxlength="500"
          show-word-limit
        />
      </div>
      <div v-if="testChatResult" class="test-result" :class="[testChatResult.success ? 'success' : 'error', testChatLoading ? 'test-result--streaming' : '']">
        <strong>{{ testChatResult.success ? '✓ 成功' : '✗ 失败' }}：</strong>
        <pre class="test-result-message">{{ testChatResult.message }}</pre>
      </div>
    </div>
    <ElTabs v-model="examplesTab" class="examples-tabs">
      <ElTabPane label="OpenAI" name="openai">
        <div class="code-block-wrapper">
          <pre class="code-block">{{ curlExamples.openai }}</pre>
          <ElButton size="small" class="copy-btn" @click="copyCurlExample('openai')">
            复制
          </ElButton>
        </div>
      </ElTabPane>
      <ElTabPane label="Claude" name="claude">
        <div class="code-block-wrapper">
          <pre class="code-block">{{ curlExamples.claude }}</pre>
          <ElButton size="small" class="copy-btn" @click="copyCurlExample('claude')">
            复制
          </ElButton>
        </div>
      </ElTabPane>
      <ElTabPane label="Gemini" name="gemini">
        <div class="code-block-wrapper">
          <pre class="code-block">{{ curlExamples.gemini }}</pre>
          <ElButton size="small" class="copy-btn" @click="copyCurlExample('gemini')">
            复制
          </ElButton>
        </div>
      </ElTabPane>
      <ElTabPane label="WebSocket" name="websocket">
        <div class="code-block-wrapper">
          <pre class="code-block">{{ curlExamples.websocket }}</pre>
          <ElButton size="small" class="copy-btn" @click="copyCurlExample('websocket')">
            复制
          </ElButton>
        </div>
      </ElTabPane>
    </ElTabs>
    <div v-if="copyStatus" class="copy-status">{{ copyStatus }}</div>
  </section>

  <ElAlert
    v-if="notice !== null"
    data-test="api-key-notice"
    class="notice"
    :title="notice.text"
    :type="notice.type"
    show-icon
    @close="notice = null"
  />

  <section class="key-panel" aria-labelledby="api-key-list-title">
    <div class="panel-toolbar">
      <div>
        <h2 id="api-key-list-title">密钥列表</h2>
        <p>共 {{ apiKeys.length }} 个接口密钥</p>
      </div>
      <div class="toolbar-actions">
        <ElInput
          v-model="searchText"
          data-test="api-key-search"
          clearable
          placeholder="搜索名称、所有者、前缀或作用域"
        >
          <template #prefix><ElIcon><Search /></ElIcon></template>
        </ElInput>
        <ElButton
          data-test="refresh-api-keys"
          :loading="loading"
          aria-label="刷新接口密钥列表"
          @click="load"
        >
          <ElIcon><Refresh /></ElIcon>
        </ElButton>
      </div>
    </div>

    <ElResult
      v-if="loadError !== ''"
      icon="error"
      title="接口密钥列表加载失败"
      :sub-title="loadError"
    >
      <template #extra><ElButton type="primary" @click="load">重新加载</ElButton></template>
    </ElResult>
    <ElSkeleton v-else-if="loading" animated>
      <template #template><ElSkeletonItem variant="rect" class="table-skeleton" /></template>
    </ElSkeleton>
    <ElEmpty v-else-if="filteredApiKeys.length === 0" description="暂无匹配接口密钥" />
    <div v-else class="table-scroll">
      <table class="key-table">
        <thead>
          <tr>
            <th>名称</th><th>所有者</th><th>密钥</th><th>作用域</th><th>状态</th>
            <th>过期时间</th><th>最后使用</th><th>创建时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="apiKey in filteredApiKeys"
            :key="apiKey.id"
            :data-test="`api-key-row-${String(apiKey.id)}`"
          >
            <td><strong>{{ apiKey.name }}</strong></td>
            <td>{{ ownerEmail(apiKey.user_id) }}</td>
            <td class="prefix-cell">{{ apiKey.key_prefix.slice(0, 8) }}****</td>
            <td><ElTag effect="plain">{{ scopeLabels[apiKey.scope] }}</ElTag></td>
            <td>
              <ElTag :type="apiKey.is_active ? 'success' : 'info'" effect="light">
                {{ apiKey.is_active ? '启用' : '停用' }}
              </ElTag>
            </td>
            <td>{{ formatDateTime(apiKey.expires_at) }}</td>
            <td>{{ formatDateTime(apiKey.last_used_at) }}</td>
            <td>{{ formatDateTime(apiKey.created_at) }}</td>
            <td>
              <div class="row-actions">
                <ElButton
                  :data-test="`edit-api-key-${String(apiKey.id)}`"
                  size="small"
                  :disabled="secretOpen || keyOperations.has(apiKey.id)"
                  @click="openEdit(apiKey)"
                ><ElIcon><Edit /></ElIcon>编辑</ElButton>
                <ElButton
                  :data-test="`rotate-api-key-${String(apiKey.id)}`"
                  size="small"
                  :disabled="secretOpen || secretOperationActive || keyOperations.has(apiKey.id)"
                  @click="rotate(apiKey)"
                ><ElIcon><Key /></ElIcon>轮换</ElButton>
                <ElButton
                  :data-test="`delete-api-key-${String(apiKey.id)}`"
                  size="small"
                  type="danger"
                  plain
                  :disabled="secretOpen || keyOperations.has(apiKey.id)"
                  @click="remove(apiKey)"
                ><ElIcon><Delete /></ElIcon>删除</ElButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <ApiKeyFormDrawer
    :model-value="formOpen"
    :api-key="editingApiKey"
    :users="users"
    :providers="providers"
    :models="models"
    :submitting="formSubmitting"
    @submit="saveApiKey"
    @update:model-value="setFormOpen"
  />
  <SecretResultDialog
    :model-value="secretOpen"
    :secret="oneTimeSecret"
    @close="closeSecret"
  />
</template>

<style scoped>
.notice {
  margin-bottom: 1rem;
}

.key-panel {
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
  width: min(24rem, 50vw);
}

.table-scroll {
  overflow-x: auto;
}

.key-table {
  width: 100%;
  min-width: 90rem;
  border-collapse: collapse;
}

.key-table th,
.key-table td {
  padding: 0.85rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--gateway-border);
  white-space: nowrap;
}

.key-table th {
  color: var(--gateway-muted);
  font-size: 0.78rem;
  font-weight: 600;
  background: rgb(248 250 252 / 72%);
}

.key-table tbody tr:last-child td {
  border-bottom: 0;
}

.prefix-cell {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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

.examples-panel {
  margin-bottom: 1rem;
  padding: 1.25rem;
}

.examples-header {
  margin-bottom: 1rem;
}

.examples-header h3 {
  margin: 0 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
}

.examples-header p {
  margin: 0;
  color: var(--gateway-muted);
  font-size: 0.85rem;
}

.examples-header code {
  padding: 0.15rem 0.4rem;
  background: var(--gateway-soft);
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.85em;
}

.examples-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.code-block-wrapper {
  position: relative;
}

.code-block {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  padding: 1rem;
  padding-right: 4rem;
  overflow-x: auto;
  overflow-wrap: normal;
  white-space: pre;
  background: #f8fafc;
  color: #1e293b;
  border: 1px solid var(--gateway-border);
  border-radius: var(--el-border-radius-base);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.8rem;
  line-height: 1.5;
}

.copy-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
}

.copy-status {
  margin-top: 0.75rem;
  color: var(--gateway-muted);
  font-size: 0.85rem;
}

.test-key-input {
  margin-bottom: 1.25rem;
}

.test-key-input :deep(.el-input-group__prepend) {
  width: 5.5rem;
  flex-shrink: 0;
}

.test-input-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.test-input-row {
  width: 100%;
}

.test-input-row--split {
  display: flex;
  gap: 0.5rem;
}

.test-input-row--split :deep(.el-input-group__prepend) {
  width: 4.5rem;
  flex-shrink: 0;
}

.test-model-input {
  flex: 1;
  min-width: 0;
}

.model-pick-select {
  width: 100%;
  max-width: 14rem;
  height: 100%;
  border: 0;
  background: transparent;
  font: inherit;
  color: inherit;
  cursor: pointer;
  outline: none;
}

.model-pick-select option {
  color: var(--gateway-text);
  background: var(--gateway-panel);
}

.test-input-row--split :deep(.el-button) {
  height: auto;
  flex-shrink: 0;
}

.test-result {
  margin-top: 0.25rem;
  padding: 0.75rem 1rem;
  border-radius: var(--el-border-radius-base);
  font-size: 0.875rem;
  line-height: 1.5;
}

.test-result.success {
  color: #065f46;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.test-result.error {
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.test-result strong {
  margin-right: 0.25rem;
}

.test-result-message {
  margin: 0.35rem 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: inherit;
  color: inherit;
  background: transparent;
}

.test-result.success.test-result--streaming .test-result-message::after {
  content: '▊';
  animation: blink-cursor 1s steps(2) infinite;
  color: var(--gateway-muted);
}

@keyframes blink-cursor {
  50% { opacity: 0; }
}
</style>
