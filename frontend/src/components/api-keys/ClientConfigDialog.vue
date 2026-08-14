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
  type CodexModelSelection,
  type ClientConfigFile,
  type ClientConfigTarget,
  type OpenCodeModelSelection,
  type PiApi,
} from '@/utils/clientConfig'
import { buildDeepSeekHarnessFiles, type DeepSeekHarnessModel } from '@/lib/deepseekHarness'
import type { ModelType } from '@/api/types'

type DialogTarget = ClientConfigTarget | 'deepseek-harness'
type LoadedModel = Pick<DeepSeekHarnessModel, 'model_types' | 'model_type'> & { id: string }

const modelTypeValues = new Set<ModelType>(['text', 'image', 'text_to_image', 'audio', 'video', 'embedding'])

const props = defineProps<{
  modelValue: boolean
  baseUrl?: string
  apiKey?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const manualApiKey = ref('')
const target = ref<DialogTarget>('claude')
const claudeModels = ref<ClaudeModelSelection>({
  primary: '',
  opus: '',
  sonnet: '',
  haiku: '',
  subagent: '',
})
const codexModels = ref<CodexModelSelection>({
  primary: '',
  review: '',
  subagent: '',
})
const openCodeModels = ref<OpenCodeModelSelection>({
  primary: '',
  plan: '',
  build: '',
  review: '',
})
const piModelIds = ref<string[]>([])
const piApi = ref<PiApi>('openai-completions')
const harnessDefaultModel = ref('')
const availableModels = ref<LoadedModel[]>([])
const availableModelIds = computed(() => availableModels.value.map((model) => model.id))
const loadingModels = ref(false)
const modelLoadError = ref('')
const actionStatus = ref('')
let modelLoadGeneration = 0

const targets: Array<{ id: DialogTarget; label: string }> = [
  { id: 'claude', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' },
  { id: 'opencode', label: 'OpenCode' },
  { id: 'pi', label: 'Pi' },
  { id: 'deepseek-harness', label: 'DeepSeek Harness' },
]

const baseUrl = computed(() => props.baseUrl ?? window.location.origin)
const effectiveApiKey = computed(() => props.apiKey ?? manualApiKey.value)
const usesProvidedApiKey = computed(() => props.apiKey !== undefined)
const isClaude = computed(() => target.value === 'claude')
const isCodex = computed(() => target.value === 'codex')
const isOpenCode = computed(() => target.value === 'opencode')
const isPi = computed(() => target.value === 'pi')
const isHarness = computed(() => target.value === 'deepseek-harness')
const claudeModelsReady = computed(() => Object.values(claudeModels.value).every((id) => id !== ''))
const codexModelsReady = computed(() => Object.values(codexModels.value).every((id) => id !== ''))
const openCodeModelsReady = computed(() => Object.values(openCodeModels.value).every((id) => id !== ''))
const piModelsReady = computed(() => piModelIds.value.length > 0)
const harnessModelsReady = computed(() => harnessDefaultModel.value !== '')
const modelsReady = computed(() => {
  if (isClaude.value) return claudeModelsReady.value
  if (isCodex.value) return codexModelsReady.value
  if (isOpenCode.value) return openCodeModelsReady.value
  if (isHarness.value) return harnessModelsReady.value
  return piModelsReady.value
})

const harnessFiles = computed(() => {
  if (!isHarness.value || effectiveApiKey.value.trim() === '' || !harnessModelsReady.value) return null
  return buildDeepSeekHarnessFiles({
    providerId: 'ai-gateway',
    displayName: 'AI Gateway',
    baseUrl: `${baseUrl.value.replace(/\/+$/, '')}/v1`,
    apiKeyEnv: 'AI_GATEWAY_API_KEY',
    apiKey: effectiveApiKey.value,
    defaultModel: harnessDefaultModel.value,
    models: availableModels.value.map((model) => ({
      canonical_name: model.id,
      enabled: true,
      ...(model.model_types === undefined ? {} : { model_types: model.model_types }),
      ...(model.model_type === undefined ? {} : { model_type: model.model_type }),
    })),
  })
})

const configuration = computed<ClientConfigFile | null>(() => {
  const selectedTarget = target.value
  if (selectedTarget === 'deepseek-harness') return null
  if (effectiveApiKey.value.trim() === '') return null
  if (!modelsReady.value) return null
  const modelId = isClaude.value
    ? claudeModels.value.primary
    : isCodex.value
      ? codexModels.value.primary
      : isOpenCode.value
        ? openCodeModels.value.primary
        : piModelIds.value[0] ?? ''
  return buildClientConfig(selectedTarget, {
    apiKey: effectiveApiKey.value,
    baseUrl: baseUrl.value,
    modelId,
    ...(isClaude.value ? { claudeModels: claudeModels.value } : {}),
    ...(isCodex.value ? { codexModels: codexModels.value } : {}),
    ...(isOpenCode.value ? { openCodeModels: openCodeModels.value } : {}),
    ...(isPi.value ? { piModelIds: piModelIds.value, piApi: piApi.value } : {}),
  })
})

function resetResolvedModels(): void {
  modelLoadGeneration += 1
  loadingModels.value = false
  availableModels.value = []
  claudeModels.value = {
    primary: '',
    opus: '',
    sonnet: '',
    haiku: '',
    subagent: '',
  }
  codexModels.value = {
    primary: '',
    review: '',
    subagent: '',
  }
  openCodeModels.value = {
    primary: '',
    plan: '',
    build: '',
    review: '',
  }
  piModelIds.value = []
  piApi.value = 'openai-completions'
  harnessDefaultModel.value = ''
  modelLoadError.value = ''
}

watch(
  [effectiveApiKey, target],
  resetResolvedModels,
)

function close(): void {
  manualApiKey.value = ''
  resetResolvedModels()
  actionStatus.value = ''
  emit('update:modelValue', false)
}

function modelRequestHeaders(requestTarget: DialogTarget, requestApiKey: string): Record<string, string> {
  if (requestTarget === 'claude') {
    return {
      'x-api-key': requestApiKey,
      'anthropic-version': '2023-06-01',
    }
  }
  return { Authorization: `Bearer ${requestApiKey}` }
}

function isModelType(value: unknown): value is ModelType {
  return typeof value === 'string' && modelTypeValues.has(value as ModelType)
}

function extractModels(payload: unknown): LoadedModel[] {
  if (typeof payload !== 'object' || payload === null || !('data' in payload)) return []
  const data = payload.data
  if (!Array.isArray(data)) return []
  const models = new Map<string, LoadedModel>()
  data.forEach((item) => {
    if (typeof item !== 'object' || item === null || !('id' in item)) return
    const { id, model_types, model_type } = item as Record<string, unknown>
    if (typeof id !== 'string' || id.trim() === '' || models.has(id)) return
    const modelTypes = Array.isArray(model_types) ? model_types.filter(isModelType) : undefined
    models.set(id, {
      id,
      ...(modelTypes === undefined ? {} : { model_types: modelTypes }),
      ...(isModelType(model_type) ? { model_type } : {}),
    })
  })
  return [...models.values()]
}

async function verifyAndLoadModels(): Promise<void> {
  if (effectiveApiKey.value.trim() === '' || loadingModels.value) return
  resetResolvedModels()
  const request = {
    generation: modelLoadGeneration,
    target: target.value,
    apiKey: effectiveApiKey.value.trim(),
    baseUrl: baseUrl.value,
  }
  loadingModels.value = true
  modelLoadError.value = ''
  const isCurrentRequest = (): boolean => (
    request.generation === modelLoadGeneration &&
    request.target === target.value &&
    request.apiKey === effectiveApiKey.value.trim() &&
    request.baseUrl === baseUrl.value
  )
  try {
    const response = await fetch(`${request.baseUrl}/v1/models`, {
      headers: modelRequestHeaders(request.target, request.apiKey),
    })
    if (!isCurrentRequest()) return
    if (!response.ok) {
      modelLoadError.value = response.status === 401 || response.status === 403
        ? '接口密钥无效或没有访问模型的权限。'
        : `加载可用模型失败：HTTP ${String(response.status)}`
      return
    }
    const models = extractModels(await response.json())
    if (!isCurrentRequest()) return
    availableModels.value = models
    if (availableModelIds.value.length === 0) {
      modelLoadError.value = '此接口密钥没有可用于该客户端的模型。'
    }
  } catch {
    if (isCurrentRequest()) {
      modelLoadError.value = '无法加载可用模型，请检查网关地址和网络连接。'
    }
  } finally {
    if (isCurrentRequest()) loadingModels.value = false
  }
}

function downloadFile(filename: string, content: string, type: string): void {
  let objectUrl: string | null = null
  let anchor: HTMLAnchorElement | null = null
  try {
    const blob = new Blob([content], { type })
    objectUrl = URL.createObjectURL(blob)
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

function download(): void {
  try {
    if (harnessFiles.value !== null) {
      downloadFile('.credentials.yaml', harnessFiles.value.credentialsYaml, 'text/yaml;charset=utf-8')
      downloadFile('settings.yaml', harnessFiles.value.settingsYaml, 'text/yaml;charset=utf-8')
    } else if (configuration.value !== null) {
      downloadFile(configuration.value.filename, configuration.value.content, 'text/plain;charset=utf-8')
    } else {
      return
    }
    actionStatus.value = '下载已开始。'
  } catch {
    actionStatus.value = '下载失败，请复制预览内容并合并到已有配置文件。'
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
      <p v-if="availableModelIds.length === 0 && !loadingModels" class="model-selection-description">
        请先验证并加载模型，再选择模型 ID。
      </p>
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
      <template v-else-if="isCodex">
        <p class="model-selection-description">Codex 可为主任务、代码审查和子代理选择不同模型。</p>
        <div class="model-grid">
          <label for="client-config-codex-primary">默认模型
            <select id="client-config-codex-primary" v-model="codexModels.primary" data-test="client-config-codex-primary" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-codex-review">审查模型
            <select id="client-config-codex-review" v-model="codexModels.review" data-test="client-config-codex-review" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-codex-subagent">子代理模型
            <select id="client-config-codex-subagent" v-model="codexModels.subagent" data-test="client-config-codex-subagent" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
        </div>
      </template>
      <template v-else-if="isOpenCode">
        <p class="model-selection-description">OpenCode 可为默认、规划、构建和审查任务选择不同模型。</p>
        <div class="model-grid">
          <label for="client-config-opencode-primary">默认模型
            <select id="client-config-opencode-primary" v-model="openCodeModels.primary" data-test="client-config-opencode-primary" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-opencode-plan">规划模型
            <select id="client-config-opencode-plan" v-model="openCodeModels.plan" data-test="client-config-opencode-plan" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-opencode-build">构建模型
            <select id="client-config-opencode-build" v-model="openCodeModels.build" data-test="client-config-opencode-build" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
          <label for="client-config-opencode-review">审查模型
            <select id="client-config-opencode-review" v-model="openCodeModels.review" data-test="client-config-opencode-review" :disabled="loadingModels || availableModelIds.length === 0">
              <option value="" disabled>选择模型</option>
              <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
            </select>
          </label>
        </div>
      </template>
      <template v-else-if="isHarness">
        <label class="field-label" for="client-config-deepseek-harness-model">默认模型</label>
        <select
          id="client-config-deepseek-harness-model"
          v-model="harnessDefaultModel"
          data-test="client-config-deepseek-harness-model"
          :disabled="loadingModels || availableModelIds.length === 0"
        >
          <option value="" disabled>选择模型</option>
          <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
        </select>
        <p class="model-selection-description">DeepSeek Harness 会将全部可用模型写入设置，并使用此模型作为默认值。</p>
      </template>
      <template v-else>
        <label class="field-label" for="client-config-pi-api">OpenAI API 类型</label>
        <select id="client-config-pi-api" v-model="piApi" data-test="client-config-pi-api">
          <option value="openai-completions">Chat Completions</option>
          <option value="openai-responses">Responses</option>
        </select>
        <label class="field-label" for="client-config-pi-models">模型 ID（可多选）</label>
        <select
          id="client-config-pi-models"
          v-model="piModelIds"
          data-test="client-config-pi-models"
          multiple
          size="5"
          :disabled="loadingModels || availableModelIds.length === 0"
        >
          <option v-for="modelId in availableModelIds" :key="modelId" :value="modelId">{{ modelId }}</option>
        </select>
        <p class="model-selection-description">Pi 会将选中的模型写入配置，之后可在客户端中切换。</p>
      </template>
    </section>

    <template v-if="harnessFiles">
      <p class="config-location" data-test="client-config-location">
        保存位置：<code>~/.dsh/.credentials.yaml</code> 和 <code>~/.dsh/settings.yaml</code>
      </p>
      <section class="harness-file" aria-labelledby="client-config-harness-credentials-heading">
        <h3 id="client-config-harness-credentials-heading">.credentials.yaml</h3>
        <pre class="config-preview" data-test="client-config-harness-credentials">{{ harnessFiles.credentialsYaml }}</pre>
      </section>
      <section class="harness-file" aria-labelledby="client-config-harness-settings-heading">
        <h3 id="client-config-harness-settings-heading">settings.yaml</h3>
        <pre class="config-preview" data-test="client-config-harness-settings">{{ harnessFiles.settingsYaml }}</pre>
      </section>
    </template>
    <template v-else-if="configuration">
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
        :disabled="configuration === null && harnessFiles === null"
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
.claude-model-grid label, .model-grid label { display: grid; gap: .4rem; color: var(--gateway-text); font-size: .9rem; font-weight: 600; }
.claude-model-grid label:first-child { grid-column: 1 / -1; }
.model-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.model-grid label:first-child { grid-column: 1 / -1; }
@media (max-width: 36rem) { .claude-model-grid, .model-grid { grid-template-columns: 1fr; } .claude-model-grid label:first-child, .model-grid label:first-child { grid-column: auto; } }
.config-location { margin: 1rem 0 .5rem; color: var(--gateway-muted); }
.harness-file h3 { margin: 1rem 0 .5rem; color: var(--gateway-text); font-size: .95rem; }
.config-preview { max-height: 20rem; margin: 0; padding: .8rem; overflow: auto; background: var(--el-fill-color-light); border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .8rem; white-space: pre-wrap; word-break: break-word; }
.empty-preview { margin: 1.25rem 0 0; color: var(--gateway-muted); font-size: .9rem; }
</style>
