<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDialog, ElForm, ElFormItem, ElInput } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-overlay.css'

import type { BalanceAdjustmentCreate, UserResponse } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  user: UserResponse | null
  submitting: boolean
  retryBlocked?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: BalanceAdjustmentCreate]
}>()

const amount = ref('')
const reason = ref('')
const amountError = ref('')
const reasonError = ref('')
const lockedPayload = ref<BalanceAdjustmentCreate | null>(null)
let idempotencyKey = ''
const signedMoneyPattern = /^[+-]?(?:0|[1-9]\d{0,11})(?:\.\d{1,8})?$/

const direction = computed(() => {
  const value = amount.value.trim()
  if (!isNonzeroMoney(value)) return ''
  return value.startsWith('-') ? '扣减' : '增加'
})
const fieldsLocked = computed(() => props.submitting || lockedPayload.value !== null)

function isNonzeroMoney(value: string): boolean {
  if (!signedMoneyPattern.test(value)) return false
  const unsigned = value.replace(/^[+-]/, '').replace('.', '')
  return /[1-9]/.test(unsigned)
}

function clearTransientState(): void {
  amount.value = ''
  reason.value = ''
  amountError.value = ''
  reasonError.value = ''
  lockedPayload.value = null
  idempotencyKey = ''
}

function startSession(): void {
  clearTransientState()
  idempotencyKey = `console-${crypto.randomUUID()}`
}

watch(
  () => props.modelValue,
  (open, wasOpen) => {
    if (open && !wasOpen) startSession()
    else if (!open) clearTransientState()
  },
  { immediate: true, flush: 'sync' },
)

onBeforeUnmount(clearTransientState)

function requestClose(): void {
  if (props.submitting) return
  clearTransientState()
  emit('update:modelValue', false)
}

function handleModelValueUpdate(value: boolean): void {
  if (!value && props.submitting) return
  if (!value) clearTransientState()
  emit('update:modelValue', value)
}

function handleBeforeClose(done: () => void): void {
  if (props.submitting) return
  clearTransientState()
  done()
}

function submitForm(): void {
  if (props.submitting || props.retryBlocked) return
  if (lockedPayload.value !== null) {
    emit('submit', { ...lockedPayload.value })
    return
  }
  amountError.value = ''
  reasonError.value = ''
  const normalizedAmount = amount.value.trim()
  const normalizedReason = reason.value.trim()
  if (!isNonzeroMoney(normalizedAmount)) {
    amountError.value = '请输入非零普通小数，最多 12 位整数和 8 位小数'
  }
  if (normalizedReason === '') reasonError.value = '请输入调整原因'
  if (amountError.value !== '' || reasonError.value !== '') return
  lockedPayload.value = {
    amount: normalizedAmount,
    reason: normalizedReason,
    idempotency_key: idempotencyKey,
  }
  emit('submit', { ...lockedPayload.value })
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    width="min(94vw, 30rem)"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    :before-close="handleBeforeClose"
    destroy-on-close
    @closed="clearTransientState"
    @update:model-value="handleModelValueUpdate"
  >
    <template #header>
      <div>
        <h2 class="dialog-heading">调整余额</h2>
        <p class="dialog-description">{{ user?.email }} · 当前余额 {{ user?.balance }}</p>
      </div>
    </template>

    <ElAlert
      v-if="retryBlocked"
      data-test="balance-reconciliation"
      class="reconciliation-alert"
      title="幂等键冲突：请关闭对话框并刷新用户列表核对余额，不要直接重试。"
      type="warning"
      :closable="false"
      show-icon
    />
    <ElForm :disabled="fieldsLocked" label-position="top" @submit.prevent="submitForm">
      <ElFormItem label="调整金额" :error="amountError">
        <ElInput
          v-model="amount"
          data-test="balance-amount"
          inputmode="decimal"
          autocomplete="off"
          :disabled="fieldsLocked"
          placeholder="例如 +10.25000000 或 -2.50000000"
        />
      </ElFormItem>
      <p v-if="direction !== ''" class="direction-preview" data-test="balance-direction">
        本次将{{ direction }}用户余额
      </p>
      <ElFormItem label="调整原因" :error="reasonError">
        <ElInput
          v-model="reason"
          data-test="balance-reason"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          :disabled="fieldsLocked"
        />
      </ElFormItem>
    </ElForm>

    <template #footer>
      <ElButton data-test="balance-cancel" :disabled="submitting" @click="requestClose">
        取消
      </ElButton>
      <ElButton
        data-test="balance-submit"
        type="primary"
        :loading="submitting"
        :disabled="retryBlocked"
        @click="submitForm"
      >
        {{ lockedPayload === null ? '确认调整' : '原样重试' }}
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.dialog-heading {
  margin: 0;
  font-size: 1.2rem;
}

.dialog-description {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.direction-preview {
  margin: -0.5rem 0 1rem;
  color: var(--gateway-brand);
  font-weight: 600;
}

.reconciliation-alert {
  margin-bottom: 1rem;
}
</style>
