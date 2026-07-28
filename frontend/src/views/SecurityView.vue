<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-card.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-tag.css'
import QrcodeVue from 'qrcode.vue'

import { changePassword, confirmTotp, disableTotp, setupTotp } from '@/api/auth'
import { ApiError } from '@/api/client'
import { getRegistrationSetting, updateRegistrationSetting } from '@/api/settings'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const currentPassword = ref('')
const newPassword = ref('')
const newPasswordConfirmation = ref('')
const passwordError = ref('')
const passwordSubmitting = ref(false)
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
const disablePassword = ref('')
const disableCode = ref('')
const disableError = ref('')
const disableSubmitting = ref(false)
const registrationEnabled = ref<boolean | null>(null)
const registrationLoading = ref(false)
const registrationSubmitting = ref(false)

const totpEnabled = computed(() => auth.user?.totp_enabled === true)
const replacementRequiresCode = computed(
  () => (totpEnabled.value || currentCodeRequiredByServer.value) && setupUri.value === '',
)

let mounted = true
let operationRevision = 0
let setupController: AbortController | undefined
let confirmController: AbortController | undefined
let passwordController: AbortController | undefined
let disableController: AbortController | undefined
let registrationController: AbortController | undefined

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

function normalizeDisableCode(value: string): void {
  disableCode.value = sixDigits(value)
  disableError.value = ''
}

function erasePasswordSecrets(): void {
  currentPassword.value = ''
  newPassword.value = ''
  newPasswordConfirmation.value = ''
}

function eraseDisableSecrets(): void {
  disablePassword.value = ''
  disableCode.value = ''
}

function eraseSecrets(): void {
  setupUri.value = ''
  currentCode.value = ''
  confirmCode.value = ''
  erasePasswordSecrets()
  eraseDisableSecrets()
}

function resetErrors(): void {
  currentCodeError.value = ''
  confirmCodeError.value = ''
  statusError.value = ''
  passwordError.value = ''
  disableError.value = ''
}

function invalidateOperations(): void {
  operationRevision += 1
  setupController?.abort()
  confirmController?.abort()
  passwordController?.abort()
  disableController?.abort()
  setupController = undefined
  confirmController = undefined
  passwordController = undefined
  disableController = undefined
  setupSubmitting.value = false
  confirmSubmitting.value = false
  passwordSubmitting.value = false
  disableSubmitting.value = false
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

function isCurrentRegistrationOperation(controller: AbortController): boolean {
  return (
    mounted &&
    auth.isAdmin &&
    registrationController === controller &&
    !controller.signal.aborted
  )
}

function clearRegistrationOperation(): void {
  registrationController?.abort()
  registrationController = undefined
  registrationLoading.value = false
  registrationSubmitting.value = false
  registrationEnabled.value = null
}

async function loadRegistrationSetting(): Promise<void> {
  if (!auth.isAdmin || registrationLoading.value) return
  const controller = new AbortController()
  registrationController?.abort()
  registrationController = controller
  registrationLoading.value = true
  try {
    const setting = await getRegistrationSetting(controller.signal)
    if (!isCurrentRegistrationOperation(controller)) return
    registrationEnabled.value = setting.enabled
  } catch (error: unknown) {
    if (!isCurrentRegistrationOperation(controller)) return
    statusError.value = safeError(error, '公开注册设置加载失败，请稍后重试')
  } finally {
    if (registrationController === controller) {
      registrationController = undefined
      if (mounted) registrationLoading.value = false
    }
  }
}

async function toggleRegistration(): Promise<void> {
  if (
    !auth.isAdmin ||
    registrationEnabled.value === null ||
    registrationSubmitting.value
  ) return
  const controller = new AbortController()
  registrationController?.abort()
  registrationController = controller
  registrationSubmitting.value = true
  statusError.value = ''
  successMessage.value = ''
  const nextEnabled = !registrationEnabled.value
  try {
    const setting = await updateRegistrationSetting(nextEnabled, controller.signal)
    if (!isCurrentRegistrationOperation(controller)) return
    registrationEnabled.value = setting.enabled
    successMessage.value = setting.enabled ? '公开注册已开启' : '公开注册已关闭'
  } catch (error: unknown) {
    if (!isCurrentRegistrationOperation(controller)) return
    statusError.value = safeError(error, '公开注册设置更新失败，请稍后重试')
  } finally {
    if (registrationController === controller) {
      registrationController = undefined
      if (mounted) registrationSubmitting.value = false
    }
  }
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

async function submitPasswordChange(): Promise<void> {
  if (passwordSubmitting.value) return
  passwordError.value = ''
  statusError.value = ''
  successMessage.value = ''
  if (currentPassword.value === '') {
    passwordError.value = '请输入当前密码'
    erasePasswordSecrets()
    return
  }
  if (newPassword.value.length < 8) {
    passwordError.value = '新密码至少需要八个字符'
    erasePasswordSecrets()
    return
  }
  if (newPassword.value !== newPasswordConfirmation.value) {
    passwordError.value = '两次输入的新密码不一致'
    erasePasswordSecrets()
    return
  }

  const revision = ++operationRevision
  const controller = new AbortController()
  passwordController?.abort()
  passwordController = controller
  passwordSubmitting.value = true
  try {
    await changePassword(
      {
        current_password: currentPassword.value,
        new_password: newPassword.value,
      },
      controller.signal,
    )
    if (!isCurrentOperation(revision, controller)) return
    erasePasswordSecrets()
    successMessage.value = '密码已修改'
  } catch (error: unknown) {
    if (!isCurrentOperation(revision, controller)) return
    erasePasswordSecrets()
    if (error instanceof ApiError && error.code === 'invalid_credentials') {
      passwordError.value = '当前密码不正确'
    } else {
      statusError.value = safeError(error, '密码修改失败，请稍后重试')
    }
  } finally {
    if (passwordController === controller) {
      passwordController = undefined
      if (mounted && operationRevision === revision) passwordSubmitting.value = false
    }
  }
}

async function turnOffTotp(): Promise<void> {
  if (disableSubmitting.value) return
  disableError.value = ''
  statusError.value = ''
  successMessage.value = ''
  if (disablePassword.value === '') {
    disableError.value = '请输入当前密码'
    eraseDisableSecrets()
    return
  }
  if (disableCode.value.length !== 6) {
    disableError.value = '请输入当前六位验证码'
    eraseDisableSecrets()
    return
  }

  const revision = ++operationRevision
  const controller = new AbortController()
  disableController?.abort()
  disableController = controller
  disableSubmitting.value = true
  try {
    await disableTotp(
      {
        current_password: disablePassword.value,
        code: disableCode.value,
      },
      controller.signal,
    )
    if (!isCurrentOperation(revision, controller)) return
    eraseDisableSecrets()
    await auth.refreshCurrentUser(controller.signal)
    if (!isCurrentOperation(revision, controller)) return
    successMessage.value = '双重验证已关闭'
  } catch (error: unknown) {
    if (!isCurrentOperation(revision, controller)) return
    eraseDisableSecrets()
    if (error instanceof ApiError && error.code === 'invalid_credentials') {
      disableError.value = '当前密码不正确'
    } else if (error instanceof ApiError && error.code === 'invalid_totp') {
      disableError.value = '当前验证码无效，请重新输入'
    } else {
      statusError.value = safeError(error, '关闭双重验证失败，请稍后重试')
    }
  } finally {
    if (disableController === controller) {
      disableController = undefined
      if (mounted && operationRevision === revision) disableSubmitting.value = false
    }
  }
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
      clearRegistrationOperation()
      currentCodeRequiredByServer.value = false
      invalidateOperations()
      successMessage.value = ''
    }
  },
  { flush: 'sync' },
)

onMounted(() => void loadRegistrationSetting())

onBeforeUnmount(() => {
  mounted = false
  clearRegistrationOperation()
  currentCodeRequiredByServer.value = false
  invalidateOperations()
  successMessage.value = ''
})
</script>

<template>
  <div class="route-page">
    <PageHeader title="安全设置" description="使用身份验证器为账户增加一层登录保护。" />

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

    <ElCard v-if="auth.isAdmin" data-test="registration-setting" class="security-card" shadow="never">
      <template #header>
        <div class="security-card__header">
          <div>
            <h2>公开注册</h2>
            <p>控制新用户是否可以从注册页面自行创建账户。</p>
          </div>
          <ElTag
            v-if="registrationEnabled !== null"
            :type="registrationEnabled ? 'success' : 'info'"
          >
            {{ registrationEnabled ? '已开启' : '已关闭' }}
          </ElTag>
        </div>
      </template>

      <p v-if="registrationLoading" class="setting-description" aria-live="polite">
        正在读取注册设置……
      </p>
      <div v-else-if="registrationEnabled !== null" class="setting-action">
        <p class="setting-description">
          关闭后，注册页面会隐藏表单，注册接口也会拒绝新账户。
        </p>
        <ElButton
          data-test="registration-toggle"
          type="primary"
          :loading="registrationSubmitting"
          :disabled="registrationSubmitting"
          @click="toggleRegistration"
        >
          {{ registrationEnabled ? '关闭公开注册' : '开启公开注册' }}
        </ElButton>
      </div>
    </ElCard>

    <ElCard class="security-card" shadow="never">
      <template #header>
        <div class="security-card__header">
          <div>
            <h2>修改密码</h2>
            <p>验证当前密码后设置新的登录密码。</p>
          </div>
        </div>
      </template>

      <ElForm class="credential-form" label-position="top" @submit.prevent="submitPasswordChange">
        <ElFormItem label="当前密码">
          <ElInput
            v-model="currentPassword"
            data-test="current-password"
            name="current_password"
            type="password"
            autocomplete="current-password"
            show-password
            :disabled="passwordSubmitting"
            required
          />
        </ElFormItem>
        <ElFormItem label="新密码">
          <ElInput
            v-model="newPassword"
            data-test="new-password"
            name="new_password"
            type="password"
            autocomplete="new-password"
            minlength="8"
            show-password
            :disabled="passwordSubmitting"
            required
          />
        </ElFormItem>
        <ElFormItem label="确认新密码">
          <ElInput
            v-model="newPasswordConfirmation"
            data-test="new-password-confirm"
            name="new_password_confirmation"
            type="password"
            autocomplete="new-password"
            minlength="8"
            show-password
            :disabled="passwordSubmitting"
            required
          />
          <p v-if="passwordError" data-test="password-error" class="field-error">
            {{ passwordError }}
          </p>
        </ElFormItem>
        <ElButton
          data-test="change-password"
          native-type="submit"
          type="primary"
          :loading="passwordSubmitting"
          :disabled="passwordSubmitting"
        >
          修改密码
        </ElButton>
      </ElForm>
    </ElCard>

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

      <div v-if="totpEnabled && setupUri === '' && !confirmSubmitting" class="disable-panel">
        <h3>关闭双重验证</h3>
        <p>关闭前需要再次验证当前密码和身份验证器中的六位验证码。</p>
        <ElForm class="credential-form" label-position="top" @submit.prevent="turnOffTotp">
          <ElFormItem label="当前密码">
            <ElInput
              v-model="disablePassword"
              data-test="disable-password"
              name="disable_current_password"
              type="password"
              autocomplete="current-password"
              show-password
              :disabled="disableSubmitting"
              required
            />
          </ElFormItem>
          <ElFormItem label="当前验证码">
            <ElInput
              :model-value="disableCode"
              data-test="disable-code"
              name="disable_totp_code"
              inputmode="numeric"
              autocomplete="one-time-code"
              maxlength="6"
              placeholder="请输入当前六位验证码"
              :disabled="disableSubmitting"
              required
              @update:model-value="normalizeDisableCode"
            />
            <p v-if="disableError" data-test="disable-error" class="field-error">
              {{ disableError }}
            </p>
          </ElFormItem>
          <ElButton
            data-test="disable-totp"
            native-type="submit"
            type="danger"
            :loading="disableSubmitting"
            :disabled="disableSubmitting || disableCode.length !== 6"
          >
            关闭双重验证
          </ElButton>
        </ElForm>
      </div>
    </ElCard>
  </div>
</template>

<style scoped>
.security-notice {
  margin-bottom: 1rem;
}

.security-card {
  border-color: var(--gateway-border);
}

.setting-action {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.setting-description {
  margin: 0;
  color: var(--gateway-muted);
  line-height: 1.6;
}

@media (max-width: 40rem) {
  .setting-action {
    align-items: stretch;
    flex-direction: column;
  }
}

.security-card + .security-card {
  margin-top: 1rem;
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

.credential-form {
  max-width: 28rem;
}

.disable-panel {
  max-width: 28rem;
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--gateway-border);
}

.disable-panel h3,
.disable-panel p {
  margin: 0;
}

.disable-panel h3 {
  font-size: 1rem;
}

.disable-panel > p {
  margin: 0.35rem 0 1rem;
  color: var(--gateway-muted);
  line-height: 1.6;
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
