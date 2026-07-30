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

import type { ModelCreate, ModelPriceTierInput, ModelResponse, ModelUpdate } from '@/api/types'

interface AliasRow {
  key: number
  alias: string
  enabled: boolean
  error: string
}

interface PriceTierRow {
  key: number
  maxInputTokens: number | null
  inputPrice: string
  outputPrice: string
  cacheReadPrice: string
  cacheWritePrice: string
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
const signedScientificZeroPattern = /^[+-]?0+(?:\.0+)?[eE][+-]?\d+$/
const scientificDecimalPattern = /^\+?(\d+)(?:\.(\d+))?[eE]([+-]?)(\d+)$/
const canonicalName = ref('')
const displayName = ref('')
const inputPrice = ref('0')
const outputPrice = ref('0')
const cacheReadPrice = ref('0')
const cacheWritePrice = ref('0')
const priceMultiplier = ref(1.0)
const enabled = ref(true)
const aliases = ref<AliasRow[]>([])
const priceTiers = ref<PriceTierRow[]>([])
const canonicalNameError = ref('')
const displayNameError = ref('')
const inputPriceError = ref('')
const outputPriceError = ref('')
const cacheReadPriceError = ref('')
const cacheWritePriceError = ref('')
const formContent = ref<HTMLElement | null>(null)
let nextAliasKey = 1
let nextTierKey = 1

const editing = computed(() => props.model !== null)
const drawerTitle = computed(() => (editing.value ? '编辑模型' : '新建模型'))

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
}

function clearDraft(): void {
  canonicalName.value = ''
  displayName.value = ''
  inputPrice.value = '0'
  outputPrice.value = '0'
  cacheReadPrice.value = '0'
  cacheWritePrice.value = '0'
  priceMultiplier.value = 1.0
  enabled.value = true
  aliases.value = []
  priceTiers.value = []
  resetErrors()
}

function resetForm(): void {
  const model = props.model
  canonicalName.value = model?.canonical_name ?? ''
  displayName.value = model?.display_name ?? ''
  inputPrice.value = normalizeDecimalInput(model?.input_price_per_million ?? '0')
  outputPrice.value = normalizeDecimalInput(model?.output_price_per_million ?? '0')
  cacheReadPrice.value = normalizeDecimalInput(model?.cache_read_price_per_million ?? '0')
  cacheWritePrice.value = normalizeDecimalInput(model?.cache_write_price_per_million ?? '0')
  priceMultiplier.value = model?.price_multiplier ?? 1.0
  enabled.value = model?.enabled ?? true
  aliases.value =
    model?.aliases.map((alias) => ({
      key: nextAliasKey++,
      alias: alias.alias,
      enabled: alias.enabled,
      error: '',
    })) ?? []
  priceTiers.value =
    model?.price_tiers?.map((tier) => ({
      key: nextTierKey++,
      maxInputTokens: tier.max_input_tokens,
      inputPrice: normalizeDecimalInput(tier.input_price_per_million),
      outputPrice: normalizeDecimalInput(tier.output_price_per_million),
      cacheReadPrice: normalizeDecimalInput(tier.cache_read_price_per_million),
      cacheWritePrice: normalizeDecimalInput(tier.cache_write_price_per_million),
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
    maxInputTokens: null,
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
  if (last !== undefined) last.maxInputTokens = null
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
    max_input_tokens: index === priceTiers.value.length - 1 ? null : row.maxInputTokens,
    input_price_per_million: row.inputPrice,
    output_price_per_million: row.outputPrice,
    cache_read_price_per_million: row.cacheReadPrice,
    cache_write_price_per_million: row.cacheWritePrice,
  }))
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
    else if (value === canonical) row.error = '别名不能与规范名称相同'
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
      const limit = row.maxInputTokens
      if (limit === null || !Number.isInteger(limit) || limit <= previousLimit) {
        row.error = '长度上限必须是严格递增的正整数'
        continue
      }
      previousLimit = limit
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
      input_price_per_million: inputPrice.value,
      output_price_per_million: outputPrice.value,
      cache_read_price_per_million: cacheReadPrice.value,
      cache_write_price_per_million: cacheWritePrice.value,
      price_multiplier: priceMultiplier.value,
      enabled: enabled.value,
      aliases: aliasPayload,
      routing_strategy: 'weighted_random',
      price_tiers: tierPayload(),
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
  if (cacheReadPrice.value !== normalizeDecimalInput(model.cache_read_price_per_million)) {
    payload.cache_read_price_per_million = cacheReadPrice.value
  }
  if (cacheWritePrice.value !== normalizeDecimalInput(model.cache_write_price_per_million)) {
    payload.cache_write_price_per_million = cacheWritePrice.value
  }
  if (priceMultiplier.value !== model.price_multiplier) {
    payload.price_multiplier = priceMultiplier.value
  }
  if (enabled.value !== model.enabled) payload.enabled = enabled.value
  if (aliasesChanged(model)) payload.aliases = aliasPayload
  if (priceTiersChanged(model)) payload.price_tiers = tierPayload()
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
              <strong>分段 {{ String(index + 1) }}</strong>
              <ElButton text type="danger" :data-test="`remove-model-price-tier-${String(index)}`" @click="removePriceTier(index)">
                <ElIcon><Delete /></ElIcon>移除
              </ElButton>
            </div>
            <div class="tier-grid">
              <ElFormItem label="输入长度上限" :error="row.error">
                <span v-if="index === priceTiers.length - 1" class="tier-unbounded">不限（最终分段）</span>
                <ElInputNumber
                  v-else
                  v-model="row.maxInputTokens"
                  :data-test="`model-tier-limit-${String(index)}`"
                  :min="1"
                  :step="1000"
                  controls-position="right"
                />
              </ElFormItem>
              <ElFormItem label="输入价格"><ElInput v-model="row.inputPrice" :data-test="`model-tier-input-${String(index)}`" inputmode="decimal" /></ElFormItem>
              <ElFormItem label="输出价格"><ElInput v-model="row.outputPrice" :data-test="`model-tier-output-${String(index)}`" inputmode="decimal" /></ElFormItem>
              <ElFormItem label="缓存读取价格"><ElInput v-model="row.cacheReadPrice" :data-test="`model-tier-cache-read-${String(index)}`" inputmode="decimal" /></ElFormItem>
              <ElFormItem label="缓存写入价格"><ElInput v-model="row.cacheWritePrice" :data-test="`model-tier-cache-write-${String(index)}`" inputmode="decimal" /></ElFormItem>
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
  margin-top: 1rem;
  padding: 1rem;
  background: #f8fafc;
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.tier-row__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.tier-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
}

.tier-unbounded {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  color: var(--gateway-muted);
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

  .tier-grid {
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
