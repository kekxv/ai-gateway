<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import {
  ElButton,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElSwitch,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-switch.css'

import type { ModelCreate, ModelResponse, ModelUpdate } from '@/api/types'

interface AliasRow {
  key: number
  alias: string
  enabled: boolean
  error: string
}

const props = defineProps<{
  modelValue: boolean
  model: ModelResponse | null
  submitting: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: ModelCreate | ModelUpdate]
}>()

const decimalPattern = /^\d{1,12}(\.\d{1,8})?$/
const scientificDecimalPattern = /^\+?(\d+)(?:\.(\d+))?[eE]([+-]?)(\d+)$/
const canonicalName = ref('')
const displayName = ref('')
const inputPrice = ref('0')
const outputPrice = ref('0')
const enabled = ref(true)
const aliases = ref<AliasRow[]>([])
const canonicalNameError = ref('')
const displayNameError = ref('')
const inputPriceError = ref('')
const outputPriceError = ref('')
const formContent = ref<HTMLElement | null>(null)
let nextAliasKey = 1

const editing = computed(() => props.model !== null)
const drawerTitle = computed(() => (editing.value ? '编辑模型' : '新建模型'))

function normalizeDecimalInput(value: string): string {
  const trimmed = value.trim()
  const match = scientificDecimalPattern.exec(trimmed)
  if (match === null) return value

  let integer = match[1] ?? ''
  let fraction = match[2] ?? ''
  if (/^0+$/.test(`${integer}${fraction}`)) return '0'

  let remaining = (match[4] ?? '').replace(/^0+/, '')
  if (remaining.length > 3 || (remaining.length === 3 && remaining > '100')) return trimmed
  const decrement = (): void => {
    const digits = '0123456789'
    let next = ''
    let borrow = true
    for (let index = remaining.length - 1; index >= 0; index -= 1) {
      const digit = remaining[index] ?? '0'
      if (!borrow) {
        next = `${digit}${next}`
        continue
      }
      if (digit === '0') next = `9${next}`
      else {
        next = `${digits.charAt(digits.indexOf(digit) - 1)}${next}`
        borrow = false
      }
    }
    remaining = next.replace(/^0+/, '')
  }

  while (remaining !== '') {
    if (match[3] === '-') {
      const moved = integer.slice(-1)
      integer = integer.slice(0, -1)
      fraction = `${moved === '' ? '0' : moved}${fraction}`
    } else {
      const moved = fraction.slice(0, 1)
      integer = `${integer}${moved === '' ? '0' : moved}`
      fraction = fraction.slice(1)
    }
    decrement()
  }

  const normalizedInteger = integer.replace(/^0+(?=\d)/, '') || '0'
  return fraction === '' ? normalizedInteger : `${normalizedInteger}.${fraction}`
}

function resetErrors(): void {
  canonicalNameError.value = ''
  displayNameError.value = ''
  inputPriceError.value = ''
  outputPriceError.value = ''
  for (const row of aliases.value) row.error = ''
}

function clearDraft(): void {
  canonicalName.value = ''
  displayName.value = ''
  inputPrice.value = '0'
  outputPrice.value = '0'
  enabled.value = true
  aliases.value = []
  resetErrors()
}

function resetForm(): void {
  const model = props.model
  canonicalName.value = model?.canonical_name ?? ''
  displayName.value = model?.display_name ?? ''
  inputPrice.value = normalizeDecimalInput(model?.input_price_per_million ?? '0')
  outputPrice.value = normalizeDecimalInput(model?.output_price_per_million ?? '0')
  enabled.value = model?.enabled ?? true
  aliases.value =
    model?.aliases.map((alias) => ({
      key: nextAliasKey++,
      alias: alias.alias,
      enabled: alias.enabled,
      error: '',
    })) ?? []
  resetErrors()
}

watch(
  () => [props.modelValue, props.model?.id] as const,
  ([open]) => {
    if (props.submitting) return
    if (open) resetForm()
    else clearDraft()
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(() => {
  if (!props.submitting) clearDraft()
})

function addAlias(): void {
  aliases.value.push({ key: nextAliasKey++, alias: '', enabled: true, error: '' })
}

function removeAlias(index: number): void {
  aliases.value.splice(index, 1)
}

function requestClose(): void {
  if (props.submitting) return
  clearDraft()
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value) {
    if (props.submitting) return
    clearDraft()
  }
  emit('update:modelValue', value)
}

function handleBeforeClose(done: () => void): void {
  if (props.submitting) return
  clearDraft()
  done()
}

async function focusInvalidField(selector: string): Promise<void> {
  await nextTick()
  const target = formContent.value?.querySelector<HTMLElement>(selector)
  if (target === undefined || target === null) return
  if (typeof target.scrollIntoView === 'function') target.scrollIntoView({ block: 'center' })
  target.focus()
}

function aliasesChanged(model: ModelResponse): boolean {
  if (aliases.value.length !== model.aliases.length) return true
  return aliases.value.some((row, index) => {
    const original = model.aliases[index]
    return original === undefined || row.alias.trim() !== original.alias || row.enabled !== original.enabled
  })
}

function validate(): string | null {
  resetErrors()
  const canonical = canonicalName.value.trim()
  if (canonical === '') canonicalNameError.value = '请输入规范模型名'
  if (displayName.value.trim() === '') displayNameError.value = '请输入显示名称'
  if (!decimalPattern.test(inputPrice.value)) {
    inputPriceError.value = '请输入非负价格，最多 12 位整数和 8 位小数'
  }
  if (!decimalPattern.test(outputPrice.value)) {
    outputPriceError.value = '请输入非负价格，最多 12 位整数和 8 位小数'
  }

  const seen = new Set<string>()
  for (const row of aliases.value) {
    const value = row.alias.trim()
    if (value === '') row.error = '请输入模型别名'
    else if (seen.has(value)) row.error = '模型别名不能重复'
    else if (value === canonical) row.error = '别名不能与规范名称相同'
    seen.add(value)
  }

  if (canonicalNameError.value !== '') return '[data-validation="model-canonical-name"] input'
  if (displayNameError.value !== '') return '[data-validation="model-display-name"] input'
  if (inputPriceError.value !== '') return '[data-validation="model-input-price"] input'
  if (outputPriceError.value !== '') return '[data-validation="model-output-price"] input'
  const invalidAlias = aliases.value.findIndex((row) => row.error !== '')
  return invalidAlias === -1
    ? null
    : `[data-validation="model-alias-${String(invalidAlias)}"] input`
}

function submitForm(): void {
  if (props.submitting) return
  const invalidSelector = validate()
  if (invalidSelector !== null) {
    void focusInvalidField(invalidSelector)
    return
  }

  const aliasPayload = aliases.value.map((row) => ({
    alias: row.alias.trim(),
    enabled: row.enabled,
  }))
  const canonical = canonicalName.value.trim()
  const display = displayName.value.trim()
  if (!editing.value) {
    emit('submit', {
      canonical_name: canonical,
      display_name: display,
      input_price_per_million: inputPrice.value,
      output_price_per_million: outputPrice.value,
      enabled: enabled.value,
      aliases: aliasPayload,
      routing_strategy: 'weighted_random',
    })
    return
  }

  const model = props.model
  if (model === null) return
  const payload: ModelUpdate = {}
  if (canonical !== model.canonical_name) payload.canonical_name = canonical
  if (display !== model.display_name) payload.display_name = display
  if (inputPrice.value !== normalizeDecimalInput(model.input_price_per_million)) {
    payload.input_price_per_million = inputPrice.value
  }
  if (outputPrice.value !== normalizeDecimalInput(model.output_price_per_million)) {
    payload.output_price_per_million = outputPrice.value
  }
  if (enabled.value !== model.enabled) payload.enabled = enabled.value
  if (aliasesChanged(model)) payload.aliases = aliasPayload
  emit('submit', payload)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(94vw, 46rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleBeforeClose"
    destroy-on-close
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">{{ drawerTitle }}</h2>
        <p class="drawer-description">配置统一模型名称、调用别名与每百万令牌价格。</p>
      </div>
    </template>

    <ElForm :disabled="submitting" label-position="top" @submit.prevent="submitForm">
      <div ref="formContent">
        <div class="form-grid">
          <ElFormItem
            data-validation="model-canonical-name"
            label="规范模型名"
            :error="canonicalNameError"
          >
            <ElInput v-model="canonicalName" data-test="model-canonical-name" maxlength="255" />
          </ElFormItem>
          <ElFormItem
            data-validation="model-display-name"
            label="显示名称"
            :error="displayNameError"
          >
            <ElInput v-model="displayName" data-test="model-display-name" maxlength="255" />
          </ElFormItem>
          <ElFormItem
            data-validation="model-input-price"
            label="输入价格（每百万令牌）"
            :error="inputPriceError"
          >
            <ElInput
              v-model="inputPrice"
              data-test="model-input-price"
              inputmode="decimal"
              spellcheck="false"
            />
          </ElFormItem>
          <ElFormItem
            data-validation="model-output-price"
            label="输出价格（每百万令牌）"
            :error="outputPriceError"
          >
            <ElInput
              v-model="outputPrice"
              data-test="model-output-price"
              inputmode="decimal"
              spellcheck="false"
            />
          </ElFormItem>
        </div>

        <div class="switch-row">
          <label>
            <span>启用模型</span>
            <ElSwitch v-model="enabled" data-test="model-enabled" />
          </label>
          <span class="strategy-note">路由策略：加权随机</span>
        </div>

        <section class="alias-section" aria-labelledby="model-alias-heading">
          <div class="section-heading">
            <div>
              <h3 id="model-alias-heading">模型别名</h3>
              <p>客户端可使用启用的别名调用此模型。</p>
            </div>
            <ElButton data-test="add-model-alias" plain :disabled="submitting" @click="addAlias">
              <ElIcon><Plus /></ElIcon>
              添加别名
            </ElButton>
          </div>

          <div v-if="aliases.length === 0" class="empty-alias">暂未配置别名</div>
          <div v-for="(row, index) in aliases" :key="row.key" class="alias-row">
            <ElFormItem
              :data-validation="`model-alias-${String(index)}`"
              :label="`别名 ${String(index + 1)}`"
              :error="row.error"
            >
              <ElInput
                v-model="row.alias"
                :data-test="`model-alias-${String(index)}`"
                maxlength="255"
              />
            </ElFormItem>
            <label class="alias-switch">
              <span>启用</span>
              <ElSwitch
                v-model="row.enabled"
                :data-test="`model-alias-enabled-${String(index)}`"
              />
            </label>
            <ElButton
              :data-test="`remove-model-alias-${String(index)}`"
              text
              type="danger"
              :disabled="submitting"
              :aria-label="`移除别名 ${String(index + 1)}`"
              @click="removeAlias(index)"
            >
              <ElIcon><Delete /></ElIcon>
              移除
            </ElButton>
          </div>
        </section>
      </div>
    </ElForm>

    <template #footer>
      <div class="drawer-actions">
        <ElButton data-test="model-cancel" :disabled="submitting" @click="requestClose">
          取消
        </ElButton>
        <ElButton
          data-test="model-submit"
          type="primary"
          :loading="submitting"
          :disabled="submitting"
          @click="submitForm"
        >
          保存模型
        </ElButton>
      </div>
    </template>
  </ElDrawer>
</template>

<style scoped>
.drawer-heading,
.section-heading h3 {
  margin: 0;
  color: var(--gateway-text);
}

.drawer-heading {
  font-size: 1.25rem;
}

.drawer-description,
.section-heading p {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  line-height: 1.5;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
}

.switch-row,
.section-heading,
.alias-row,
.drawer-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.switch-row {
  margin-bottom: 1.5rem;
}

.switch-row label,
.alias-switch {
  display: flex;
  gap: 0.65rem;
  align-items: center;
  font-weight: 500;
}

.strategy-note,
.empty-alias {
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.alias-section {
  padding-top: 1.25rem;
  border-top: 1px solid var(--gateway-border);
}

.alias-row {
  align-items: flex-start;
  margin-top: 1rem;
  padding: 1rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.alias-row :deep(.el-form-item) {
  flex: 1;
  margin-bottom: 0;
}

.alias-switch,
.alias-row > .el-button {
  margin-top: 1.85rem;
}

.empty-alias {
  margin-top: 1rem;
  padding: 1rem;
  text-align: center;
  background: #f8fafc;
  border-radius: 10px;
}

.drawer-actions {
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .section-heading,
  .alias-row {
    align-items: stretch;
    flex-direction: column;
  }

  .alias-switch,
  .alias-row > .el-button {
    margin-top: 0;
  }
}
</style>
