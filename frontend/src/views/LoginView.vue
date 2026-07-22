<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-card.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'

import { ApiError } from '@/api/client'
import { resolveLoginRedirect } from '@/router/redirect'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const totpCode = ref('')
const needsTotp = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const totpInput = ref<InstanceType<typeof ElInput> | null>(null)

function clearSecrets(): void {
  password.value = ''
  totpCode.value = ''
}

async function submit(): Promise<void> {
  if (submitting.value) return
  errorMessage.value = ''
  submitting.value = true

  try {
    await auth.login({
      email: email.value.trim(),
      password: password.value,
      ...(needsTotp.value ? { totp_code: totpCode.value } : {}),
    })
    const destination = resolveLoginRedirect(route.query.redirect)
    clearSecrets()
    await router.replace(destination)
  } catch (error: unknown) {
    if (error instanceof ApiError && error.code === 'totp_required') {
      needsTotp.value = true
      totpCode.value = ''
      submitting.value = false
      await nextTick()
      totpInput.value?.focus()
    } else {
      errorMessage.value = error instanceof Error ? error.message : '登录失败，请稍后重试'
      clearSecrets()
    }
  } finally {
    submitting.value = false
  }
}

function normalizeTotp(value: string): void {
  totpCode.value = value.replace(/\D/g, '').slice(0, 6)
}

onBeforeUnmount(clearSecrets)
</script>

<template>
  <main class="login-page">
    <ElCard class="login-card" shadow="never">
      <div class="login-heading">
        <span class="login-heading__mark" aria-hidden="true">智</span>
        <div>
          <p class="login-heading__eyebrow">AI 网关</p>
          <h1>管理控制台登录</h1>
        </div>
      </div>

      <ElAlert
        v-if="errorMessage"
        class="login-alert"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <ElForm label-position="top" @submit.prevent="submit">
        <ElFormItem label="管理员邮箱">
          <ElInput
            v-model="email"
            data-test="email"
            name="email"
            type="email"
            autocomplete="username"
            placeholder="请输入管理员邮箱"
            :disabled="submitting || needsTotp"
            required
          />
        </ElFormItem>

        <ElFormItem label="密码">
          <ElInput
            v-model="password"
            data-test="password"
            name="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            show-password
            :disabled="submitting"
            required
          />
        </ElFormItem>

        <ElFormItem v-if="needsTotp" label="双重验证验证码">
          <ElInput
            ref="totpInput"
            :model-value="totpCode"
            data-test="totp-code"
            name="totp_code"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            placeholder="请输入六位验证码"
            :disabled="submitting"
            required
            @update:model-value="normalizeTotp"
          />
          <p class="field-help">请打开身份验证器并输入当前六位验证码。</p>
        </ElFormItem>

        <ElButton
          class="login-submit"
          data-test="submit"
          native-type="submit"
          type="primary"
          :loading="submitting"
          :disabled="submitting || (needsTotp && totpCode.length !== 6)"
        >
          {{ needsTotp ? '验证并登录' : '登录' }}
        </ElButton>
      </ElForm>
    </ElCard>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 2rem 1rem;
  background:
    radial-gradient(circle at 12% 18%, rgb(37 99 235 / 12%), transparent 32rem),
    var(--gateway-bg);
}

.login-card {
  width: min(100%, 28rem);
  border-color: var(--gateway-border);
  border-radius: 1rem;
  box-shadow: 0 1.5rem 4rem rgb(23 32 51 / 10%);
}

.login-heading {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.75rem;
}

.login-heading__mark {
  display: grid;
  width: 3rem;
  height: 3rem;
  flex: 0 0 auto;
  place-items: center;
  color: #fff;
  font-size: 1.25rem;
  font-weight: 700;
  background: var(--gateway-brand);
  border-radius: 0.8rem;
}

.login-heading__eyebrow {
  margin: 0 0 0.2rem;
  color: var(--gateway-brand);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

h1 {
  margin: 0;
  font-size: 1.5rem;
}

.login-alert {
  margin-bottom: 1rem;
}

.field-help {
  margin: 0.45rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.8rem;
  line-height: 1.5;
}

.login-submit {
  width: 100%;
  margin-top: 0.5rem;
}
</style>
