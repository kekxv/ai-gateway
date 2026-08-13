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
  ElInputNumber,
  ElSwitch,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-input-number.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-switch.css'

import type {
  ModelCreate,
  ModelPriceTierInput,
  ModelResponse,
  ModelTimePriceRuleInput,
  ModelType,
  ModelUpdate,
} from '@/api/types'

interface AliasRow {
  key: number
  alias: string
  enabled: boolean
  error: string
}

interface PriceTierRow {
  key: number
  maxInputValue: number | null
  maxInputUnit: TierLimitUnit
  inputPrice: string
  outputPrice: string
  cacheReadPrice: string
  cacheWritePrice: string
  error: string
}

interface TimePriceRuleRow {
  key: number
  weekdays: number[]
  startTime: string
  endTime: string
  effectiveAt: string
  inputPrice: string
  outputPrice: string
  cacheReadPrice: string
  cacheWritePrice: string
  error: string
}

type TierLimitUnit = 'token' | 'k'

const TOKENS_PER_K = 1000

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
const signedScientificZeroPattern = /^[+-]?0+(?:\.0+)?[eE][+-]?\d+$/
const scientificDecimalPattern = /^\+?(\d+)(?:\.(\d+))?[eE]([+-]?)(\d+)$/
const canonicalName = ref('')
const displayName = ref('')
const modelType = ref<ModelType>('text')
const inputPrice = ref('0')
const outputPrice = ref('0')
const cacheReadPrice = ref('0')
const cacheWritePrice = ref('0')
const priceMultiplier = ref(1.0)
const enabled = ref(true)
const aliases = ref<AliasRow[]>([])
const priceTiers = ref<PriceTierRow[]>([])
const timePriceRules = ref<TimePriceRuleRow[]>([])
const canonicalNameError = ref('')
const displayNameError = ref('')
const inputPriceError = ref('')
const outputPriceError = ref('')
const cacheReadPriceError = ref('')
const cacheWritePriceError = ref('')
const formContent = ref<HTMLElement | null>(null)
let nextAliasKey = 1
let nextTierKey = 1
let nextTimeRuleKey = 1
const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const editing = computed(() => props.model !== null)
const drawerTitle = computed(() => (editing.value ? '编辑模型' : '新建模型'))

function tierLimitState(maxInputTokens: number | null): {
  value: number | null
  unit: TierLimitUnit
} {
  if (maxInputTokens === null) return { value: null, unit: 'k' }
  return maxInputTokens % TOKENS_PER_K === 0
    ? { value: maxInputTokens / TOKENS_PER_K, unit: 'k' }
    : { value: maxInputTokens, unit: 'token' }
}

function tierLimitTokens(row: PriceTierRow): number | null {
  if (row.maxInputValue === null) return null
  if (row.maxInputUnit === 'token') return row.maxInputValue

  const source = String(row.maxInputValue)
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(source)
  if (match === null) return row.maxInputValue * TOKENS_PER_K

  const sign = match[1] === '-' ? -1n : 1n
  const whole = match[2] ?? '0'
  const fraction = match[3] ?? ''
  const exponent = Number(match[4] ?? '0')
  const shift = exponent - fraction.length + 3
  const digits = sign * BigInt(`${whole}${fraction}`)
  if (shift >= 0) return Number(digits * 10n ** BigInt(shift))

  const divisor = 10n ** BigInt(-shift)
  if (digits % divisor !== 0n) return row.maxInputValue * TOKENS_PER_K
  return Number(digits / divisor)
}

function changeTierLimitUnit(row: PriceTierRow, event: Event): void {
  const target = event.target
  if (!(target instanceof HTMLSelectElement)) return
  const nextUnit: TierLimitUnit = target.value === 'k' ? 'k' : 'token'
  const tokens = tierLimitTokens(row)
  row.maxInputUnit = nextUnit
  if (tokens !== null) {
    row.maxInputValue = nextUnit === 'k' ? tokens / TOKENS_PER_K : tokens
  }
}

function normalizeDecimalInput(value: string): string {
  const trimmed = value.trim()
  if (signedScientificZeroPattern.test(trimmed)) return '0'
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
  cacheReadPriceError.value = ''
  cacheWritePriceError.value = ''
  for (const row of aliases.value) row.error = ''
  for (const row of priceTiers.value) row.error = ''
  for (const row of timePriceRules.value) row.error = ''
}

function clearDraft(): void {
  canonicalName.value = ''
  displayName.value = ''
  modelType.value = 'text'
  inputPrice.value = '0'
  outputPrice.value = '0'
  cacheReadPrice.value = '0'
  cacheWritePrice.value = '0'
  priceMultiplier.value = 1.0
  enabled.value = true
  aliases.value = []
  priceTiers.value = []
  timePriceRules.value = []
  resetErrors()
}

function resetForm(): void {
  const model = props.model
  canonicalName.value = model?.canonical_name ?? ''
  displayName.value = model?.display_name ?? ''
  modelType.value = model?.model_type ?? 'text'
  inputPrice.value = normalizeDecimalInput(model?.input_price_per_million ?? '0')
  outputPrice.value = normalizeDecimalInput(model?.output_price_per_million ?? '0')
  cacheReadPrice.value = normalizeDecimalInput(model?.cache_read_price_per_million ?? '0')
  cacheWritePrice.value = normalizeDecimalInput(model?.cache_write_price_per_million ?? '0')
  priceMultiplier.value = Number(model?.price_multiplier ?? 1.0)
  enabled.value = model?.enabled ?? true
  aliases.value =
    model?.aliases.map((alias) => ({
      key: nextAliasKey++,
      alias: alias.alias,
      enabled: alias.enabled,
      error: '',
    })) ?? []
  priceTiers.value =
    model?.price_tiers?.map((tier) => {
      const limit = tierLimitState(tier.max_input_tokens)
      return {
        key: nextTierKey++,
        maxInputValue: limit.value,
        maxInputUnit: limit.unit,
        inputPrice: normalizeDecimalInput(tier.input_price_per_million),
        outputPrice: normalizeDecimalInput(tier.output_price_per_million),
        cacheReadPrice: normalizeDecimalInput(tier.cache_read_price_per_million),
        cacheWritePrice: normalizeDecimalInput(tier.cache_write_price_per_million),
        error: '',
      }
    }) ?? []
  timePriceRules.value =
    model?.time_price_rules?.map((rule) => ({
      key: nextTimeRuleKey++,
      weekdays: [...rule.weekdays],
      startTime: rule.start_time,
      endTime: rule.end_time,
      effectiveAt: rule.effective_at === null || rule.effective_at === undefined ? '' : rule.effective_at.slice(0, 16),
      inputPrice: normalizeDecimalInput(rule.input_price_per_million),
      outputPrice: normalizeDecimalInput(rule.output_price_per_million),
      cacheReadPrice: normalizeDecimalInput(rule.cache_read_price_per_million),
      cacheWritePrice: normalizeDecimalInput(rule.cache_write_price_per_million),
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

function addPriceTier(): void {
  const row: PriceTierRow = {
    key: nextTierKey++,
    maxInputValue: null,
    maxInputUnit: 'k',
    inputPrice: inputPrice.value,
    outputPrice: outputPrice.value,
    cacheReadPrice: cacheReadPrice.value,
    cacheWritePrice: cacheWritePrice.value,
    error: '',
  }
  if (priceTiers.value.length === 0) priceTiers.value.push(row)
  else priceTiers.value.splice(priceTiers.value.length - 1, 0, row)
}

function removePriceTier(index: number): void {
  priceTiers.value.splice(index, 1)
  const last = priceTiers.value.at(-1)
  if (last !== undefined) last.maxInputValue = null
}

function addTimePriceRule(): void {
  timePriceRules.value.push({
    key: nextTimeRuleKey++,
    weekdays: [0, 1, 2, 3, 4],
    startTime: '09:00:00',
    endTime: '12:00:00',
    effectiveAt: '',
    inputPrice: inputPrice.value,
    outputPrice: outputPrice.value,
    cacheReadPrice: cacheReadPrice.value,
    cacheWritePrice: cacheWritePrice.value,
    error: '',
  })
}

function removeTimePriceRule(index: number): void {
  timePriceRules.value.splice(index, 1)
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

function tierPayload(): ModelPriceTierInput[] {
  return priceTiers.value.map((row, index) => ({
    max_input_tokens: index === priceTiers.value.length - 1 ? null : tierLimitTokens(row),
    input_price_per_million: row.inputPrice,
    output_price_per_million: row.outputPrice,
    cache_read_price_per_million: row.cacheReadPrice,
    cache_write_price_per_million: row.cacheWritePrice,
  }))
}

function timePriceRulePayload(): ModelTimePriceRuleInput[] {
  return timePriceRules.value.map((rule) => ({
    weekdays: [...rule.weekdays].sort((left, right) => left - right),
    start_time: rule.startTime,
    end_time: rule.endTime,
    effective_at: rule.effectiveAt === '' ? null : rule.effectiveAt,
    input_price_per_million: rule.inputPrice,
    output_price_per_million: rule.outputPrice,
    cache_read_price_per_million: rule.cacheReadPrice,
    cache_write_price_per_million: rule.cacheWritePrice,
  }))
}

function timePriceRulesChanged(model: ModelResponse): boolean {
  const stored = (model.time_price_rules ?? []).map((rule) => ({
    weekdays: rule.weekdays,
    start_time: rule.start_time,
    end_time: rule.end_time,
    effective_at:
      rule.effective_at === null || rule.effective_at === undefined
        ? null
        : rule.effective_at.slice(0, 16),
    input_price_per_million: rule.input_price_per_million,
    output_price_per_million: rule.output_price_per_million,
    cache_read_price_per_million: rule.cache_read_price_per_million,
    cache_write_price_per_million: rule.cache_write_price_per_million,
  }))
  return JSON.stringify(timePriceRulePayload()) !== JSON.stringify(stored)
}

function priceTiersChanged(model: ModelResponse): boolean {
  const original = model.price_tiers ?? []
  const current = tierPayload()
  if (original.length !== current.length) return true
  return current.some((tier, index) => {
    const stored = original[index]
    return (
      stored === undefined ||
      tier.max_input_tokens !== stored.max_input_tokens ||
      normalizeDecimalInput(tier.input_price_per_million) !==
        normalizeDecimalInput(stored.input_price_per_million) ||
      normalizeDecimalInput(tier.output_price_per_million) !==
        normalizeDecimalInput(stored.output_price_per_million) ||
      normalizeDecimalInput(tier.cache_read_price_per_million) !==
        normalizeDecimalInput(stored.cache_read_price_per_million) ||
      normalizeDecimalInput(tier.cache_write_price_per_million) !==
        normalizeDecimalInput(stored.cache_write_price_per_million)
    )
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
  if (!decimalPattern.test(cacheReadPrice.value)) {
    cacheReadPriceError.value = '请输入非负价格，最多 12 位整数和 8 位小数'
  }
  if (!decimalPattern.test(cacheWritePrice.value)) {
    cacheWritePriceError.value = '请输入非负价格，最多 12 位整数和 8 位小数'
  }

  const seen = new Set<string>()
  for (const row of aliases.value) {
    const value = row.alias.trim()
    if (value === '') row.error = '请输入模型别名'
    else if (seen.has(value)) row.error = '模型别名不能重复'
    seen.add(value)
  }

  let previousLimit = 0
  for (const [index, row] of priceTiers.value.entries()) {
    const prices = [row.inputPrice, row.outputPrice, row.cacheReadPrice, row.cacheWritePrice]
    if (prices.some((price) => !decimalPattern.test(price))) {
      row.error = '四项价格均需为非负小数，最多 8 位小数'
      continue
    }
    if (index < priceTiers.value.length - 1) {
      const limit = tierLimitTokens(row)
      if (limit === null || !Number.isSafeInteger(limit) || limit <= previousLimit) {
        row.error = '长度上限换算后必须是严格递增的正安全整数'
        continue
      }
      previousLimit = limit
    }
  }
  for (const row of timePriceRules.value) {
    if (
      row.weekdays.length === 0 ||
      row.startTime >= row.endTime ||
      [row.inputPrice, row.outputPrice, row.cacheReadPrice, row.cacheWritePrice].some(
        (price) => !decimalPattern.test(price),
      )
    ) {
      row.error = '请选择星期、填写有效时间段与四项非负价格'
    }
  }

  if (canonicalNameError.value !== '') return '[data-validation="model-canonical-name"] input'
  if (displayNameError.value !== '') return '[data-validation="model-display-name"] input'
  if (inputPriceError.value !== '') return '[data-validation="model-input-price"] input'
  if (outputPriceError.value !== '') return '[data-validation="model-output-price"] input'
  if (cacheReadPriceError.value !== '') {
    return '[data-validation="model-cache-read-price"] input'
  }
  if (cacheWritePriceError.value !== '') {
    return '[data-validation="model-cache-write-price"] input'
  }
  const invalidTier = priceTiers.value.findIndex((row) => row.error !== '')
  if (invalidTier !== -1) {
    return `[data-validation="model-price-tier-${String(invalidTier)}"] input`
  }
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
      model_type: modelType.value,
      input_price_per_million: inputPrice.value,
      output_price_per_million: outputPrice.value,
      cache_read_price_per_million: cacheReadPrice.value,
      cache_write_price_per_million: cacheWritePrice.value,
      price_multiplier: priceMultiplier.value,
      enabled: enabled.value,
      aliases: aliasPayload,
      routing_strategy: 'weighted_random',
      price_tiers: tierPayload(),
      time_price_rules: timePriceRulePayload(),
    })
    return
  }

  const model = props.model
  if (model === null) return
  const payload: ModelUpdate = {}
  if (canonical !== model.canonical_name) payload.canonical_name = canonical
  if (display !== model.display_name) payload.display_name = display
  if (modelType.value !== (model.model_type ?? 'text')) payload.model_type = modelType.value
  if (inputPrice.value !== normalizeDecimalInput(model.input_price_per_million)) {
    payload.input_price_per_million = inputPrice.value
  }
  if (outputPrice.value !== normalizeDecimalInput(model.output_price_per_million)) {
    payload.output_price_per_million = outputPrice.value
  }
  if (cacheReadPrice.value !== normalizeDecimalInput(model.cache_read_price_per_million)) {
    payload.cache_read_price_per_million = cacheReadPrice.value
  }
  if (cacheWritePrice.value !== normalizeDecimalInput(model.cache_write_price_per_million)) {
    payload.cache_write_price_per_million = cacheWritePrice.value
  }
  if (priceMultiplier.value !== Number(model.price_multiplier)) {
    payload.price_multiplier = priceMultiplier.value
  }
  if (enabled.value !== model.enabled) payload.enabled = enabled.value
  if (aliasesChanged(model)) payload.aliases = aliasPayload
  if (priceTiersChanged(model)) payload.price_tiers = tierPayload()
  if (timePriceRulesChanged(model)) payload.time_price_rules = timePriceRulePayload()
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
          <ElFormItem label="模型类型">
            <select v-model="modelType" data-test="model-type" class="tier-limit-unit">
              <option value="text">文本</option>
              <option value="image">图像理解</option>
              <option value="text_to_image">文生图</option>
              <option value="audio">音频</option>
              <option value="video">视频</option>
              <option value="embedding">向量嵌入</option>
            </select>
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
          <ElFormItem
            data-validation="model-cache-read-price"
            label="缓存读取价格（每百万令牌）"
            :error="cacheReadPriceError"
          >
            <ElInput
              v-model="cacheReadPrice"
              data-test="model-cache-read-price"
              inputmode="decimal"
              spellcheck="false"
            />
          </ElFormItem>
          <ElFormItem
            data-validation="model-cache-write-price"
            label="缓存写入价格（每百万令牌）"
            :error="cacheWritePriceError"
          >
            <ElInput
              v-model="cacheWritePrice"
              data-test="model-cache-write-price"
              inputmode="decimal"
              spellcheck="false"
            />
          </ElFormItem>
          <ElFormItem
            data-test="price-multiplier-field"
            data-validation="price-multiplier"
            label="价格倍率"
          >
            <ElInputNumber
              v-model="priceMultiplier"
              data-test="model-price-multiplier"
              :min="0.10"
              :max="10.00"
              :step="0.1"
              :precision="2"
              :placeholder="'1.00'"
              controls-position="right"
            />
            <div class="form-help">
              应用于该模型的价格倍率（0.10 ~ 10.00）
            </div>
          </ElFormItem>
        </div>

        <section class="tier-section" aria-labelledby="model-tier-heading">
          <div class="section-heading">
            <div>
              <h3 id="model-tier-heading">分段计费</h3>
              <p>按输入上下文长度（输入 + 缓存读写令牌）选价，边界按“长度 ≤ 上限”计算。</p>
            </div>
            <ElButton data-test="add-model-price-tier" plain :disabled="submitting" @click="addPriceTier">
              <ElIcon><Plus /></ElIcon>添加分段
            </ElButton>
          </div>
          <div v-if="priceTiers.length === 0" class="empty-alias">未启用分段计费，使用基础价格。</div>
          <div
            v-for="(row, index) in priceTiers"
            :key="row.key"
            class="tier-row"
            :data-validation="`model-price-tier-${String(index)}`"
          >
            <div class="tier-row__header">
              <div class="tier-row__title">
                <strong>分段 {{ String(index + 1) }}</strong>
                <span>每百万令牌价格</span>
              </div>
              <ElFormItem class="tier-limit-field" label="长度上限" :error="row.error">
                <span v-if="index === priceTiers.length - 1" class="tier-unbounded">不限长度（最终分段）</span>
                <div v-else class="tier-limit-input">
                  <ElInputNumber
                    v-model="row.maxInputValue"
                    :data-test="`model-tier-limit-${String(index)}`"
                    :min="row.maxInputUnit === 'k' ? 0.001 : 1"
                    :step="1"
                    controls-position="right"
                  />
                  <select
                    :value="row.maxInputUnit"
                    :data-test="`model-tier-limit-unit-${String(index)}`"
                    class="tier-limit-unit"
                    :aria-label="`分段 ${String(index + 1)} 长度单位`"
                    :disabled="submitting"
                    @change="changeTierLimitUnit(row, $event)"
                  >
                    <option value="token">无单位</option>
                    <option value="k">K</option>
                  </select>
                </div>
              </ElFormItem>
              <ElButton
                class="tier-remove"
                text
                type="danger"
                :aria-label="`移除分段 ${String(index + 1)}`"
                :data-test="`remove-model-price-tier-${String(index)}`"
                @click="removePriceTier(index)"
              >
                <ElIcon><Delete /></ElIcon>移除
              </ElButton>
            </div>
            <div class="tier-price-grid">
              <ElFormItem label="输入价格"><ElInput v-model="row.inputPrice" :data-test="`model-tier-input-${String(index)}`" inputmode="decimal" spellcheck="false" /></ElFormItem>
              <ElFormItem label="输出价格"><ElInput v-model="row.outputPrice" :data-test="`model-tier-output-${String(index)}`" inputmode="decimal" spellcheck="false" /></ElFormItem>
              <ElFormItem label="缓存读取价格"><ElInput v-model="row.cacheReadPrice" :data-test="`model-tier-cache-read-${String(index)}`" inputmode="decimal" spellcheck="false" /></ElFormItem>
              <ElFormItem label="缓存写入价格"><ElInput v-model="row.cacheWritePrice" :data-test="`model-tier-cache-write-${String(index)}`" inputmode="decimal" spellcheck="false" /></ElFormItem>
            </div>
          </div>
        </section>

        <section class="tier-section" aria-labelledby="model-time-price-heading">
          <div class="section-heading">
            <div>
              <h3 id="model-time-price-heading">按时段计费</h3>
              <p>按北京时间匹配；未命中任何规则时使用基础价格或分段价格。</p>
            </div>
            <ElButton data-test="add-model-time-price-rule" plain :disabled="submitting" @click="addTimePriceRule">
              <ElIcon><Plus /></ElIcon>添加时段
            </ElButton>
          </div>
          <div v-if="timePriceRules.length === 0" class="empty-alias">未配置时段规则</div>
          <div v-for="(rule, index) in timePriceRules" :key="rule.key" class="tier-row">
            <div class="tier-row__header">
              <div class="tier-row__title"><strong>时段 {{ String(index + 1) }}</strong><span>北京时间</span></div>
              <ElButton text type="danger" :data-test="`remove-model-time-price-rule-${String(index)}`" @click="removeTimePriceRule(index)">
                <ElIcon><Delete /></ElIcon>移除
              </ElButton>
            </div>
            <ElFormItem label="适用星期" :error="rule.error">
              <div class="weekday-checkboxes">
                <label v-for="(label, day) in weekdayLabels" :key="label">
                  <input v-model="rule.weekdays" type="checkbox" :value="day" :data-test="`model-time-rule-day-${String(index)}-${String(day)}`" />
                  {{ label }}
                </label>
              </div>
            </ElFormItem>
            <div class="tier-price-grid">
              <ElFormItem label="开始时间"><ElInput v-model="rule.startTime" :data-test="`model-time-rule-start-${String(index)}`" placeholder="09:00:00" /></ElFormItem>
              <ElFormItem label="结束时间"><ElInput v-model="rule.endTime" :data-test="`model-time-rule-end-${String(index)}`" placeholder="12:00:00" /></ElFormItem>
              <ElFormItem label="生效时间（可选）"><ElInput v-model="rule.effectiveAt" type="datetime-local" /></ElFormItem>
              <ElFormItem label="输入价格"><ElInput v-model="rule.inputPrice" inputmode="decimal" /></ElFormItem>
              <ElFormItem label="输出价格"><ElInput v-model="rule.outputPrice" inputmode="decimal" /></ElFormItem>
              <ElFormItem label="缓存读取价格"><ElInput v-model="rule.cacheReadPrice" inputmode="decimal" /></ElFormItem>
              <ElFormItem label="缓存写入价格"><ElInput v-model="rule.cacheWritePrice" inputmode="decimal" /></ElFormItem>
            </div>
          </div>
        </section>

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

.alias-section,
.tier-section {
  padding-top: 1.25rem;
  border-top: 1px solid var(--gateway-border);
}

.tier-section {
  margin: 0.5rem 0 1.5rem;
}

.tier-row {
  margin-top: 0.75rem;
  padding: 0.75rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.tier-row__header {
  display: grid;
  grid-template-columns: minmax(7rem, 1fr) minmax(12rem, 16rem) auto;
  gap: 0.75rem;
  align-items: start;
  margin-bottom: 0.625rem;
}

.tier-row__title {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding-top: 0.2rem;
}

.tier-row__title span {
  color: var(--gateway-muted);
  font-size: 0.75rem;
}

.tier-limit-field,
.tier-price-grid :deep(.el-form-item) {
  margin-bottom: 0;
}

.tier-limit-field :deep(.el-form-item__label),
.tier-price-grid :deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 0.25rem;
  line-height: 1.25;
}

.tier-limit-field :deep(.el-input-number) {
  width: 100%;
}

.tier-limit-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 5.5rem;
  gap: 0.5rem;
  width: 100%;
}

.tier-limit-unit {
  min-width: 0;
  padding: 0 0.5rem;
  border: 1px solid var(--gateway-border);
  border-radius: 4px;
  background: var(--gateway-panel);
  color: var(--gateway-text);
}

.tier-limit-unit:focus {
  outline: none;
  border-color: var(--gateway-brand);
}

.tier-remove {
  margin-top: 1.25rem;
}

.tier-price-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem 0.75rem;
}

.tier-unbounded {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  padding: 0 0.75rem;
  color: #475569;
  font-size: 0.8125rem;
  font-weight: 600;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
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

.form-help {
  margin: 0.25rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.75rem;
  line-height: 1.4;
}

.drawer-actions {
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .tier-price-grid {
    grid-template-columns: 1fr;
  }

  .tier-row__header {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .tier-limit-field {
    grid-row: 2;
    grid-column: 1 / -1;
  }

  .tier-remove {
    grid-row: 1;
    grid-column: 2;
    margin-top: 0;
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
