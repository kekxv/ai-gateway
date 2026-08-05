<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDialog, ElInput } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-overlay.css'

import {
  buildClientConfig,
  type ClientConfigFile,
  type ClientConfigTarget,
} from '@/utils/clientConfig'

const props = defineProps<{
  modelValue: boolean
  baseUrl?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const apiKey = ref('')
const selectedModelId = ref('')
const target = ref<ClientConfigTarget>('claude')
const availableModelIds = ref<string[]>([])
const loadingModels = ref(false)
const modelLoadError = ref('')
const actionStatus = ref('')

const targets: Array<{ id: ClientConfigTarget; label: string }> = [
  { id: 'claude', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' },
  { id: 'opencode', label: 'OpenCode' },
  { id: 'pi', label: 'Pi' },
]

const baseUrl = computed(() => props.baseUrl ?? window.location.origin)

const configuration = computed<ClientConfigFile | null>(() => {
  if (apiKey.value.trim() === '' || selectedModelId.value === '') return null
  return buildClientConfig(target.value, {
    apiKey: apiKey.value,
    baseUrl: baseUrl.value,
    modelId: selectedModelId.value,
  })
})

function resetResolvedModels(): void {
  availableModelIds.value = []
  selectedModelId.value = ''
  modelLoadError.value = ''
}

watch(
  [apiKey, target],
  resetResolvedModels,
)

function close(): void {
  apiKey.value = ''
  resetResolvedModels()
  actionStatus.value = ''
  emit('update:modelValue', false)
}

function modelRequestHeaders(): Record<string, string> {
  const key = apiKey.value.trim()
  if (target.value === 'claude') {
    return {
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
    }
  }
  return { Authorization: `Bearer ${key}` }
}

function extractModelIds(payload: unknown): string[] {
  if (typeof payload !== 'object' || payload === null || !('data' in payload)) return []
  const data = payload.data
  if (!Array.isArray(data)) return []
  return [...new Set(data.flatMap((item) => {
    if (typeof item !== 'object' || item === null || !('id' in item)) return []
    const id = (item as { id: unknown }).id
    return typeof id === 'string' && id.trim() !== '' ? [id] : []
  }))]
}

async function verifyAndLoadModels(): Promise<void> {
  if (apiKey.value.trim() === '' || loadingModels.value) return
  loadingModels.value = true
  modelLoadError.value = ''
  resetResolvedModels()
  try {
    const response = await fetch(`${baseUrl.value}/v1/models`, {
      headers: modelRequestHeaders(),
    })
    if (!response.ok) {
      modelLoadError.value = response.status === 401 || response.status === 403
        ? '接口密钥无效或没有访问模型的权限。'
        : `加载可用模型失败：HTTP ${String(response.status)}`
      return
    }
    availableModelIds.value = extractModelIds(await response.json())
    if (availableModelIds.value.length === 0) {
      modelLoadError.value = '此接口密钥没有可用于该客户端的模型。'
    }
  } catch {
    modelLoadError.value = '无法加载可用模型，请检查网关地址和网络连接。'
  } finally {
    loadingModels.value = false
  }
}

function download(): void {
  if (configuration.value === null) return
  let objectUrl: string | null = null
  let anchor: HTMLAnchorElement | null = null
  try {
    const blob = new Blob([configuration.value.content], { type: 'text/plain;charset=utf-8' })
    objectUrl = URL.createObjectURL(blob)
    anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = configuration.value.filename
    anchor.rel = 'noopener'
    document.body.append(anchor)
    anchor.click()
    actionStatus.value = '下载已开始。'
  } catch {
    actionStatus.value = '下载失败，请复制预览内容并合并到已有配置文件。'
  } finally {
    anchor?.remove()
    if (objectUrl !== null) URL.revokeObjectURL(objectUrl)
  }
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    width="min(94vw, 46rem)"
    :close-on-click-modal="false"
    @close="close"
  >
    <template #header>
      <div>
        <h2 class="dialog-heading">生成客户端配置</h2>
        <p class="dialog-description">选择客户端、模型 ID，并粘贴需要写入配置的接口密钥。</p>
      </div>
    </template>

    <ElAlert
      title="配置文件包含真实接口密钥，请勿提交到版本库或分享给他人。"
      type="warning"
      :closable="false"
      show-icon
    />
    <ElAlert
      title="请合并到已有配置，不要直接覆盖已有配置文件。"
      type="info"
      :closable="false"
      show-icon
      class="merge-warning"
    />

    <div class="target-list" aria-label="客户端类型">
      <ElButton
        v-for="item in targets"
        :key="item.id"
        :data-test="`client-config-target-${item.id}`"
        :type="target === item.id ? 'primary' : 'default'"
        @click="target = item.id"
      >
        {{ item.label }}
      </ElButton>
    </div>

    <label class="field-label" for="client-config-model">模型 ID</label>
    <select
      id="client-config-model"
      v-model="selectedModelId"
      data-test="client-config-model"
      :disabled="loadingModels || availableModelIds.length === 0"
    >
      <option value="" disabled>选择模型</option>
      <option
        v-for="modelId in availableModelIds"
        :key="modelId"
        :value="modelId"
      >
        {{ modelId }}
      </option>
    </select>

    <label class="field-label" for="client-config-key">接口密钥</label>
    <ElInput
      id="client-config-key"
      v-model="apiKey"
      data-test="client-config-key"
      type="password"
      show-password
      autocomplete="off"
      placeholder="粘贴接口密钥"
    />
    <div class="model-actions">
      <ElButton
        data-test="client-config-verify"
        :loading="loadingModels"
        :disabled="apiKey.trim() === ''"
        @click="verifyAndLoadModels"
      >
        验证并加载可用模型
      </ElButton>
      <span v-if="availableModelIds.length > 0" class="model-status">
        已加载 {{ availableModelIds.length }} 个可用模型
      </span>
    </div>
    <p v-if="modelLoadError" class="model-error" role="alert">{{ modelLoadError }}</p>
    <p v-if="actionStatus" class="action-status" data-test="client-config-status" role="status">
      {{ actionStatus }}
    </p>

    <template v-if="configuration">
      <p class="config-location" data-test="client-config-location">
        保存位置：<code>{{ configuration.location }}</code>
      </p>
      <pre class="config-preview" data-test="client-config-preview">{{ configuration.content }}</pre>
    </template>
    <p v-else class="empty-preview">选择模型并输入接口密钥后预览配置文件。</p>

    <template #footer>
      <ElButton data-test="client-config-close" @click="close">关闭</ElButton>
      <ElButton
        data-test="client-config-download"
        type="primary"
        :disabled="configuration === null"
        @click="download"
      >
        下载配置文件
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.dialog-heading { margin: 0; color: var(--gateway-text); font-size: 1.25rem; }
.dialog-description { margin: .35rem 0 0; color: var(--gateway-muted); }
.target-list { display: flex; flex-wrap: wrap; gap: .5rem; margin: 1rem 0; }
.merge-warning { margin-top: .75rem; }
.field-label { display: block; margin: 1rem 0 .4rem; color: var(--gateway-text); font-size: .9rem; font-weight: 600; }
select { box-sizing: border-box; width: 100%; min-height: 2rem; padding: .45rem .7rem; color: var(--gateway-text); background: var(--gateway-panel); border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); }
.model-actions { display: flex; flex-wrap: wrap; gap: .65rem; align-items: center; margin-top: .75rem; }
.model-status { color: var(--gateway-muted); font-size: .875rem; }
.model-error { margin: .65rem 0 0; color: var(--el-color-danger); font-size: .875rem; }
.action-status { margin: .65rem 0 0; color: var(--gateway-muted); font-size: .875rem; }
.config-location { margin: 1rem 0 .5rem; color: var(--gateway-muted); }
.config-preview { max-height: 20rem; margin: 0; padding: .8rem; overflow: auto; background: var(--el-fill-color-light); border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .8rem; white-space: pre-wrap; word-break: break-word; }
.empty-preview { margin: 1.25rem 0 0; color: var(--gateway-muted); font-size: .9rem; }
</style>
