<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElDialog, ElTabs, ElTabPane } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-checkbox.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-tabs.css'

const props = defineProps<{
  modelValue: boolean
  secret: string | null
  gatewayUrl?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const acknowledged = ref(false)
const actionStatus = ref('')
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const activeTab = ref<any>('openai')
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
let outstandingObjectUrl: string | null = null

const baseUrl = computed(() => props.gatewayUrl ?? window.location.origin)

function modelCountFromResponse(value: unknown): number {
  if (typeof value !== 'object' || value === null || !('data' in value)) return 0
  return Array.isArray(value.data) ? value.data.length : 0
}

const curlExamples = computed(() => {
  const key = '$AI_GATEWAY_API_KEY'
  const base = baseUrl.value

  return {
    openai: `curl "${base}/v1/chat/completions" \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'`,
    claude: `curl "${base}/v1/messages" \\
  -H "x-api-key: ${key}" \\
  -H "anthropic-version: 2023-06-01" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-3-opus-20240229",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
    gemini: `curl "${base}/v1beta/models/gemini-pro:generateContent" \\
  -H "x-goog-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "contents": [{"parts": [{"text": "Hello!"}]}]
  }'`,
    websocket: `# OpenAI Realtime WebSocket
websocat -H="Authorization: Bearer ${key}" \\
  -H="Sec-WebSocket-Protocol: realtime" \\
  "${base.replace('http', 'ws')}/v1/realtime?model=gpt-4"

# Gemini Live WebSocket
websocat -H="x-goog-api-key: ${key}" \\
  -H="Sec-WebSocket-Protocol: gemini-live" \\
  "${base.replace('http', 'ws')}/v1beta/live"`,
  }
})

function revokeOutstandingUrl(): void {
  if (outstandingObjectUrl === null) return
  URL.revokeObjectURL(outstandingObjectUrl)
  outstandingObjectUrl = null
}

function clearTransientState(): void {
  acknowledged.value = false
  actionStatus.value = ''
  testResult.value = null
  revokeOutstandingUrl()
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) clearTransientState()
  },
  { flush: 'sync' },
)

onBeforeUnmount(clearTransientState)

async function copySecret(): Promise<void> {
  if (!props.modelValue || props.secret === null) return
  try {
    await navigator.clipboard.writeText(props.secret)
    actionStatus.value = '已复制到剪贴板'
  } catch {
    actionStatus.value = '复制失败，请手动选择并复制'
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function copyCurl(protocol: any): Promise<void> {
  const example = curlExamples.value[protocol as keyof typeof curlExamples.value]
  if (!example) return
  try {
    await navigator.clipboard.writeText(example)
    actionStatus.value = `${String(protocol).toUpperCase()} 命令已复制`
  } catch {
    actionStatus.value = '复制失败'
  }
}

function downloadSecret(): void {
  if (!props.modelValue || props.secret === null) return
  revokeOutstandingUrl()
  try {
    const blob = new Blob([props.secret, '\n'], { type: 'text/plain;charset=utf-8' })
    outstandingObjectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = outstandingObjectUrl
    anchor.download = 'ai-gateway-api-key.txt'
    anchor.rel = 'noopener'
    document.body.append(anchor)
    try {
      anchor.click()
      actionStatus.value = '下载已开始'
    } finally {
      anchor.remove()
    }
  } catch {
    actionStatus.value = '下载失败，请手动复制密钥'
  } finally {
    revokeOutstandingUrl()
  }
}

async function testApiKey(): Promise<void> {
  if (!props.secret || testing.value) return
  testing.value = true
  testResult.value = null

  try {
    // Test by calling /v1/models endpoint which all API keys should have access to
    const response = await fetch(`${baseUrl.value}/v1/models`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${props.secret}`,
      },
    })

    if (response.ok) {
      const data: unknown = await response.json()
      const modelCount = modelCountFromResponse(data)
      testResult.value = {
        success: true,
        message: `密钥有效！发现 ${String(modelCount)} 个可用模型。`,
      }
    } else if (response.status === 401 || response.status === 403) {
      testResult.value = {
        success: false,
        message: '密钥无效或已过期。',
      }
    } else {
      testResult.value = {
        success: false,
        message: `请求失败：HTTP ${String(response.status)}`,
      }
    }
  } catch (error) {
    testResult.value = {
      success: false,
      message: `网络错误：${error instanceof Error ? error.message : '未知错误'}`,
    }
  } finally {
    testing.value = false
  }
}

function confirmClose(): void {
  if (!acknowledged.value) return
  clearTransientState()
  emit('close')
}

function refuseClose(): void {
  // The one-time secret must not disappear without explicit acknowledgement.
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    width="min(94vw, 42rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    :before-close="refuseClose"
    destroy-on-close
    @closed="clearTransientState"
  >
    <template #header>
      <div>
        <h2 class="dialog-heading">请立即保存接口密钥</h2>
        <p class="dialog-description">此密钥只显示一次，关闭后无法再次查看。</p>
      </div>
    </template>

    <ElAlert
      title="请勿在聊天、工单或截图中分享此密钥。"
      type="warning"
      :closable="false"
      show-icon
    />

    <pre
      v-if="modelValue && secret !== null"
      class="secret-input"
      data-test="one-time-secret"
      aria-label="一次性接口密钥"
    >{{ secret }}</pre>

    <div class="secret-actions">
      <ElButton data-test="secret-copy" :disabled="secret === null" @click="copySecret">
        复制密钥
      </ElButton>
      <ElButton data-test="secret-download" :disabled="secret === null" @click="downloadSecret">
        下载 .txt
      </ElButton>
      <ElButton
        type="success"
        :loading="testing"
        :disabled="secret === null"
        @click="testApiKey"
      >
        测试密钥
      </ElButton>
      <span class="action-status" role="status">{{ actionStatus }}</span>
    </div>

    <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
      {{ testResult.message }}
    </div>

    <div class="examples-section">
      <h3 class="examples-heading">快速开始：cURL 示例</h3>
      <ElTabs v-model="activeTab" class="protocol-tabs">
        <ElTabPane label="OpenAI" name="openai">
          <div class="code-block-wrapper">
            <pre class="code-block">{{ curlExamples.openai }}</pre>
            <ElButton size="small" class="copy-curl-btn" @click="copyCurl('openai')">
              复制
            </ElButton>
          </div>
        </ElTabPane>
        <ElTabPane label="Claude" name="claude">
          <div class="code-block-wrapper">
            <pre class="code-block">{{ curlExamples.claude }}</pre>
            <ElButton size="small" class="copy-curl-btn" @click="copyCurl('claude')">
              复制
            </ElButton>
          </div>
        </ElTabPane>
        <ElTabPane label="Gemini" name="gemini">
          <div class="code-block-wrapper">
            <pre class="code-block">{{ curlExamples.gemini }}</pre>
            <ElButton size="small" class="copy-curl-btn" @click="copyCurl('gemini')">
              复制
            </ElButton>
          </div>
        </ElTabPane>
        <ElTabPane label="WebSocket" name="websocket">
          <div class="code-block-wrapper">
            <pre class="code-block">{{ curlExamples.websocket }}</pre>
            <ElButton size="small" class="copy-curl-btn" @click="copyCurl('websocket')">
              复制
            </ElButton>
          </div>
        </ElTabPane>
      </ElTabs>
    </div>

    <ElCheckbox v-model="acknowledged" data-test="secret-acknowledged">
      我已安全保存，此密钥关闭后无法再次查看
    </ElCheckbox>

    <template #footer>
      <ElButton
        data-test="secret-confirm-close"
        type="primary"
        :disabled="!acknowledged"
        @click="confirmClose"
      >
        已保存并关闭
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.dialog-heading {
  margin: 0;
  color: var(--gateway-text);
  font-size: 1.25rem;
}

.dialog-description {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
}

.secret-input {
  box-sizing: border-box;
  width: 100%;
  margin: 1rem 0;
  padding: 0.8rem;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.secret-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-items: center;
  margin-bottom: 1rem;
}

.action-status {
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.test-result {
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  border-radius: var(--el-border-radius-base);
  font-size: 0.9rem;
}

.test-result.success {
  color: #67c23a;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
}

.test-result.error {
  color: #f56c6c;
  background: #fef0f0;
  border: 1px solid #fde2e2;
}

.examples-section {
  margin: 1.5rem 0;
}

.examples-heading {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--gateway-text);
}

.protocol-tabs :deep(.el-tabs__header) {
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

.copy-curl-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
}
</style>
