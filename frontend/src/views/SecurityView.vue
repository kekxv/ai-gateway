<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCard, ElFormItem, ElInput, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-card.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-tag.css'
import QrcodeVue from 'qrcode.vue'

import { confirmTotp, setupTotp } from '@/api/auth'
import { ApiError } from '@/api/client'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const currentCode = ref('')
const confirmCode = ref('')
const setupUri = ref('')
const currentCodeRequiredByServer = ref(false)
const currentCodeError = ref('')
const confirmCodeError = ref('')
const statusError = ref('')
const successMessage = ref('')
const setupSubmitting = ref(false)
const confirmSubmitting = ref(false)

const totpEnabled = computed(() => auth.user?.totp_enabled === true)
const replacementRequiresCode = computed(
  () => (totpEnabled.value || currentCodeRequiredByServer.value) && setupUri.value === '',
)

let mounted = true
let operationRevision = 0
let setupController: AbortController | undefined
let confirmController: AbortController | undefined

function sixDigits(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6)
}

function normalizeCurrentCode(value: string): void {
  currentCode.value = sixDigits(value)
  currentCodeError.value = ''
}

function normalizeConfirmCode(value: string): void {
  confirmCode.value = sixDigits(value)
  confirmCodeError.value = ''
}

function eraseSecrets(): void {
  setupUri.value = ''
  currentCode.value = ''
  confirmCode.value = ''
}

function resetErrors(): void {
  currentCodeError.value = ''
  confirmCodeError.value = ''
  statusError.value = ''
}

function invalidateOperations(): void {
  operationRevision += 1
  setupController?.abort()
  confirmController?.abort()
  setupController = undefined
  confirmController = undefined
  setupSubmitting.value = false
  confirmSubmitting.value = false
  eraseSecrets()
  resetErrors()
}

function isCurrentOperation(revision: number, controller: AbortController): boolean {
  return (
    mounted &&
    auth.user !== null &&
    operationRevision === revision &&
    !controller.signal.aborted
  )
}

function setupFieldError(error: unknown): string {
  if (!(error instanceof ApiError)) return ''
  if (error.code === 'current_totp_required') return '请输入当前六位验证码'
  if (error.code === 'invalid_totp') return '当前验证码无效，请重新输入'
  if (error.code === 'totp_not_configured') {
    return '服务器未找到当前双重验证配置，请刷新后重试'
  }
  return ''
}

function confirmFieldError(error: unknown): string {
  if (!(error instanceof ApiError)) return ''
  if (error.code === 'invalid_totp') return '新验证码无效，请重新输入'
  if (error.code === 'totp_not_configured') return '双重验证配置已失效，请重新开始设置'
  if (error.code === 'current_totp_required') return '请重新验证当前验证码并开始设置'
  return ''
}

function safeError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

async function startSetup(): Promise<void> {
  if (setupSubmitting.value || confirmSubmitting.value || setupUri.value !== '') return
  if (replacementRequiresCode.value && currentCode.value.length !== 6) {
    currentCodeError.value = '请输入当前六位验证码'
    return
  }

  resetErrors()
  successMessage.value = ''
  const revision = ++operationRevision
  const controller = new AbortController()
  setupController?.abort()
  setupController = controller
  setupSubmitting.value = true
  const payload = replacementRequiresCode.value
    ? { current_totp_code: currentCode.value }
    : {}

  try {
    const result = await setupTotp(payload, controller.signal)
    if (!isCurrentOperation(revision, controller)) return
    setupUri.value = result.otpauth_uri
    currentCode.value = ''
  } catch (error: unknown) {
    if (!isCurrentOperation(revision, controller)) return
    currentCode.value = ''
    if (error instanceof ApiError && error.code === 'current_totp_required') {
      currentCodeRequiredByServer.value = true
    }
    const fieldError = setupFieldError(error)
    if (fieldError !== '') currentCodeError.value = fieldError
    else statusError.value = safeError(error, '双重验证设置请求失败，请稍后重试')
  } finally {
    if (setupController === controller) {
      setupController = undefined
      if (mounted && operationRevision === revision) setupSubmitting.value = false
    }
  }
}

async function confirmSetup(): Promise<void> {
  if (
    confirmSubmitting.value ||
    setupSubmitting.value ||
    setupUri.value === '' ||
    confirmCode.value.length !== 6
  ) return

  confirmCodeError.value = ''
  statusError.value = ''
  successMessage.value = ''
  const revision = ++operationRevision
  const controller = new AbortController()
  confirmController?.abort()
  confirmController = controller
  confirmSubmitting.value = true

  try {
    try {
      await confirmTotp({ code: confirmCode.value }, controller.signal)
    } catch (error: unknown) {
      if (!isCurrentOperation(revision, controller)) return
      confirmCode.value = ''
      const fieldError = confirmFieldError(error)
      if (fieldError !== '') confirmCodeError.value = fieldError
      else statusError.value = safeError(error, '新验证码确认失败，请稍后重试')
      return
    }

    if (!isCurrentOperation(revision, controller)) return
    eraseSecrets()

    try {
      await auth.refreshCurrentUser(controller.signal)
      if (!isCurrentOperation(revision, controller)) return
      successMessage.value = '双重验证已启用'
    } catch (error: unknown) {
      if (!isCurrentOperation(revision, controller)) return
      statusError.value = safeError(error, '双重验证状态刷新失败，请重新登录后确认')
    }
  } finally {
    if (confirmController === controller) {
      confirmController = undefined
      if (mounted && operationRevision === revision) confirmSubmitting.value = false
    }
  }
}

function cancelSetup(): void {
  invalidateOperations()
  successMessage.value = ''
}

async function copyManualUri(): Promise<void> {
  const uri = setupUri.value
  const revision = operationRevision
  if (uri === '') return
  try {
    await navigator.clipboard.writeText(uri)
    if (mounted && revision === operationRevision && setupUri.value === uri) {
      successMessage.value = '手动配置地址已复制'
      statusError.value = ''
    }
  } catch {
    if (mounted && revision === operationRevision && setupUri.value === uri) {
      statusError.value = '无法复制，请手动选择配置地址'
    }
  }
}

watch(
  () => auth.user,
  (user) => {
    if (user === null) {
      currentCodeRequiredByServer.value = false
      invalidateOperations()
      successMessage.value = ''
    }
  },
  { flush: 'sync' },
)

onBeforeUnmount(() => {
  mounted = false
  currentCodeRequiredByServer.value = false
  invalidateOperations()
  successMessage.value = ''
})
</script>

<template>
  <PageHeader title="安全设置" description="使用身份验证器为管理员账户增加一层登录保护。" />

  <ElAlert
    v-if="successMessage"
    class="security-notice"
    :title="successMessage"
    type="success"
    :closable="false"
    show-icon
  />
  <ElAlert
    v-if="statusError"
    class="security-notice"
    :title="statusError"
    type="error"
    :closable="false"
    show-icon
  />

  <ElCard class="security-card" shadow="never">
    <template #header>
      <div class="security-card__header">
        <div>
          <h2>双重验证</h2>
          <p>登录时需要输入身份验证器生成的六位验证码。</p>
        </div>
        <ElTag :type="totpEnabled ? 'success' : 'info'">
          {{ totpEnabled ? '已启用' : '未启用' }}
        </ElTag>
      </div>
    </template>

    <div v-if="setupUri === '' && !confirmSubmitting" class="setup-start">
      <ElFormItem v-if="replacementRequiresCode" label="当前验证码">
        <ElInput
          :model-value="currentCode"
          data-test="current-code"
          name="current_totp_code"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          placeholder="请输入当前六位验证码"
          :disabled="setupSubmitting"
          @update:model-value="normalizeCurrentCode"
        />
        <p v-if="currentCodeError" data-test="current-code-error" class="field-error">
          {{ currentCodeError }}
        </p>
      </ElFormItem>

      <div class="button-row">
        <ElButton
          data-test="start-totp"
          type="primary"
          :loading="setupSubmitting"
          :disabled="
            setupSubmitting || confirmSubmitting || (replacementRequiresCode && currentCode.length !== 6)
          "
          @click="startSetup"
        >
          {{ replacementRequiresCode ? '重新绑定验证器' : '启用双重验证' }}
        </ElButton>
        <ElButton v-if="setupSubmitting" data-test="cancel-setup" @click="cancelSetup">
          取消
        </ElButton>
      </div>
    </div>

    <div v-else-if="setupUri !== ''" class="enrollment">
      <div class="qr-panel">
        <QrcodeVue
          :value="setupUri"
          :size="200"
          level="M"
          render-as="svg"
          aria-label="双重验证配置二维码"
        />
        <p>使用身份验证器扫描二维码。</p>
      </div>

      <div class="manual-panel">
        <ElFormItem label="手动配置地址">
          <ElInput
            :model-value="setupUri"
            data-test="manual-uri"
            readonly
            autocomplete="off"
            :spellcheck="false"
          />
        </ElFormItem>
        <ElButton data-test="copy-uri" @click="copyManualUri">复制配置地址</ElButton>

        <ElFormItem label="新验证码">
          <ElInput
            :model-value="confirmCode"
            data-test="confirm-code"
            name="code"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            placeholder="请输入新的六位验证码"
            :disabled="confirmSubmitting"
            @update:model-value="normalizeConfirmCode"
          />
          <p v-if="confirmCodeError" data-test="confirm-code-error" class="field-error">
            {{ confirmCodeError }}
          </p>
        </ElFormItem>

        <div class="button-row">
          <ElButton
            data-test="confirm-totp"
            type="primary"
            :loading="confirmSubmitting"
            :disabled="confirmSubmitting || confirmCode.length !== 6"
            @click="confirmSetup"
          >
            确认启用
          </ElButton>
          <ElButton data-test="cancel-totp" @click="cancelSetup">取消</ElButton>
        </div>
      </div>
    </div>

    <div v-else class="refreshing" aria-live="polite">正在刷新双重验证状态…</div>
  </ElCard>
</template>

<style scoped>
.security-notice {
  margin-bottom: 1rem;
}

.security-card {
  border-color: var(--gateway-border);
}

.security-card__header {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  justify-content: space-between;
}

h2,
.security-card__header p,
.qr-panel p,
.field-error {
  margin: 0;
}

h2 {
  font-size: 1.125rem;
}

.security-card__header p,
.qr-panel p {
  margin-top: 0.35rem;
  color: var(--gateway-muted);
  line-height: 1.6;
}

.setup-start {
  max-width: 28rem;
}

.enrollment {
  display: grid;
  grid-template-columns: minmax(14rem, 18rem) minmax(18rem, 1fr);
  gap: 2rem;
  align-items: start;
}

.qr-panel {
  display: grid;
  justify-items: center;
  padding: 1.5rem;
  text-align: center;
  background: var(--gateway-bg);
  border: 1px solid var(--gateway-border);
  border-radius: 0.75rem;
}

.manual-panel {
  min-width: 0;
}

.manual-panel > .el-button {
  margin: -0.6rem 0 1.25rem;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.button-row :deep(.el-button + .el-button) {
  margin-left: 0;
}

.field-error {
  width: 100%;
  margin-top: 0.35rem;
  color: var(--el-color-danger);
  font-size: 0.75rem;
  line-height: 1.2;
}

.refreshing {
  padding: 1rem 0;
  color: var(--gateway-muted);
}

@media (max-width: 720px) {
  .enrollment {
    grid-template-columns: 1fr;
  }

  .qr-panel {
    justify-self: stretch;
  }
}
</style>
