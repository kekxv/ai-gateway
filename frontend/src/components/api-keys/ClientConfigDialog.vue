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
  type ClaudeModelSelection,
  type ClientConfigFile,
  type ClientConfigTarget,
} from '@/utils/clientConfig'

const props = defineProps<{
  modelValue: boolean
  baseUrl?: string
  apiKey?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const manualApiKey = ref('')
const selectedModelId = ref('')
const target = ref<ClientConfigTarget>('claude')
const claudeModels = ref<ClaudeModelSelection>({
  primary: '',
  opus: '',
  sonnet: '',
  haiku: '',
  subagent: '',
})
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
const effectiveApiKey = computed(() => props.apiKey ?? manualApiKey.value)
const usesProvidedApiKey = computed(() => props.apiKey !== undefined)
const isClaude = computed(() => target.value === 'claude')
const claudeModelsReady = computed(() => Object.values(claudeModels.value).every((id) => id !== ''))

const configuration = computed<ClientConfigFile | null>(() => {
  if (effectiveApiKey.value.trim() === '') return null
  if (isClaude.value && !claudeModelsReady.value) return null
  if (!isClaude.value && selectedModelId.value === '') return null
  return buildClientConfig(target.value, {
    apiKey: effectiveApiKey.value,
    baseUrl: baseUrl.value,
    modelId: isClaude.value ? claudeModels.value.primary : selectedModelId.value,
    ...(isClaude.value ? { claudeModels: claudeModels.value } : {}),
  })
})

function resetResolvedModels(): void {
  availableModelIds.value = []
  selectedModelId.value = ''
  claudeModels.value = {
    primary: '',
    opus: '',
    sonnet: '',
    haiku: '',
    subagent: '',
  }
  modelLoadError.value = ''
}

watch(
  [manualApiKey, target],
  resetResolvedModels,
)

function close(): void {
  manualApiKey.value = ''
  resetResolvedModels()
  actionStatus.value = ''
  emit('update:modelValue', false)
}

function modelRequestHeaders(): Record<string, string> {
  const key = effectiveApiKey.value.trim()
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
  if (effectiveApiKey.value.trim() === '' || loadingModels.value) return
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
        <p class="dialog-description">选择客户端，验证接口密钥后再选择可用模型。</p>
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

    <template v-if="!usesProvidedApiKey">
      <label class="field-label" for="client-config-key">接口密钥</label>
      <ElInput
        id="client-config-key"
        v-model="manualApiKey"
        data-test="client-config-key"
        type="password"
        show-password
        autocomplete="off"
        placeholder="粘贴接口密钥"
      />
    </template>
    <p v-else class="provided-key-note">正在使用刚创建的接口密钥验证并生成配置。</p>
    <div class="model-actions">
      <ElButton
        data-test="client-config-verify"
        :loading="loadingModels"
        :disabled="effectiveApiKey.trim() === ''"
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

    <section class="model-selection" data-test="client-config-models">
      <template v-if="isClaude">
        <p class="model-selection-description">Claude Code 可为不同任务角色选择不同模型。</p>
        <div class="claude-model-grid">
          <label for="client-config-claude-primary">默认模型
            <select
              id="client-config-claude-primary"
              v-model="claudeModels.primary"
              data-test="client-config-claude-primary"
              :disabled="loadingModels || availableModelIds.length === 0"
            >
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-claude-opus">Opus 模型
            <select id="client-config-claude-opus" v-model="claudeModels.opus" data-test="client-config-claude-opus" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-claude-sonnet">Sonnet 模型
            <select id="client-config-claude-sonnet" v-model="claudeModels.sonnet" data-test="client-config-claude-sonnet" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-claude-haiku">Haiku 模型
            <select id="client-config-claude-haiku" v-model="claudeModels.haiku" data-test="client-config-claude-haiku" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-claude-subagent">子代理模型
            <select id="client-config-claude-subagent" v-model="claudeModels.subagent" data-test="client-config-claude-subagent" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
        </div>
      </template>
      <template v-else>
        <label class="field-label" for="client-config-model">模型 ID</label>
        <select
          id="client-config-model"
          v-model="selectedModelId"
          data-test="client-config-model"
          :disabled="loadingModels || availableModelIds.length === 0"
        >
          <option value="" disabled>选择模型</option>
          <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
        </select>
      </template>
    </section>

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
.provided-key-note { margin: 1rem 0 0; color: var(--gateway-muted); font-size: .9rem; }
.model-status { color: var(--gateway-muted); font-size: .875rem; }
.model-error { margin: .65rem 0 0; color: var(--el-color-danger); font-size: .875rem; }
.action-status { margin: .65rem 0 0; color: var(--gateway-muted); font-size: .875rem; }
.model-selection { margin-top: 1rem; }
.model-selection-description { margin: 0 0 .65rem; color: var(--gateway-muted); font-size: .875rem; }
.claude-model-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.claude-model-grid label { display: grid; gap: .4rem; color: var(--gateway-text); font-size: .9rem; font-weight: 600; }
.claude-model-grid label:first-child { grid-column: 1 / -1; }
@media (max-width: 36rem) { .claude-model-grid { grid-template-columns: 1fr; } .claude-model-grid label:first-child { grid-column: auto; } }
.config-location { margin: 1rem 0 .5rem; color: var(--gateway-muted); }
.config-preview { max-height: 20rem; margin: 0; padding: .8rem; overflow: auto; background: var(--el-fill-color-light); border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .8rem; white-space: pre-wrap; word-break: break-word; }
.empty-preview { margin: 1.25rem 0 0; color: var(--gateway-muted); font-size: .9rem; }
</style>
