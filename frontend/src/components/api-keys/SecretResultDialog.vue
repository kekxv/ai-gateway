<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElDialog } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-checkbox.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-overlay.css'

const props = defineProps<{
  modelValue: boolean
  secret: string | null
}>()

const emit = defineEmits<{
  close: []
}>()

const acknowledged = ref(false)
const actionStatus = ref('')
let outstandingObjectUrl: string | null = null

function revokeOutstandingUrl(): void {
  if (outstandingObjectUrl === null) return
  URL.revokeObjectURL(outstandingObjectUrl)
  outstandingObjectUrl = null
}

function clearTransientState(): void {
  acknowledged.value = false
  actionStatus.value = ''
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
    width="min(94vw, 38rem)"
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
        复制
      </ElButton>
      <ElButton data-test="secret-download" :disabled="secret === null" @click="downloadSecret">
        下载 .txt
      </ElButton>
      <span class="action-status" role="status">{{ actionStatus }}</span>
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
</style>
