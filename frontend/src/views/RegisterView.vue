<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-card.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const passwordConfirmation = ref('')
const submitting = ref(false)
const errorMessage = ref('')

function clearSecrets(): void {
  password.value = ''
  passwordConfirmation.value = ''
}

async function submit(): Promise<void> {
  if (submitting.value) return
  errorMessage.value = ''
  if (password.value !== passwordConfirmation.value) {
    errorMessage.value = '两次输入的密码不一致'
    clearSecrets()
    return
  }

  submitting.value = true
  try {
    await auth.register({
      email: email.value.trim(),
      password: password.value,
    })
    clearSecrets()
    await router.replace({ name: auth.isAdmin ? 'dashboard' : 'security' })
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : '注册失败，请稍后重试'
    clearSecrets()
  } finally {
    submitting.value = false
  }
}

onBeforeUnmount(clearSecrets)
</script>

<template>
  <main class="register-page">
    <ElCard class="register-card" shadow="never">
      <div class="register-heading">
        <span class="register-heading__mark" aria-hidden="true">智</span>
        <div>
          <p class="register-heading__eyebrow">AI 网关</p>
          <h1>创建账户</h1>
        </div>
      </div>

      <p class="registration-policy">
        第一个注册的账户将自动成为管理员，之后注册的账户为普通用户。
      </p>

      <ElAlert
        v-if="errorMessage"
        class="register-alert"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <ElForm label-position="top" @submit.prevent="submit">
        <ElFormItem label="邮箱">
          <ElInput
            v-model="email"
            data-test="register-email"
            name="email"
            type="email"
            autocomplete="username"
            placeholder="请输入邮箱"
            :disabled="submitting"
            required
          />
        </ElFormItem>

        <ElFormItem label="密码">
          <ElInput
            v-model="password"
            data-test="register-password"
            name="password"
            type="password"
            autocomplete="new-password"
            placeholder="至少八个字符"
            minlength="8"
            show-password
            :disabled="submitting"
            required
          />
        </ElFormItem>

        <ElFormItem label="确认密码">
          <ElInput
            v-model="passwordConfirmation"
            data-test="register-password-confirm"
            name="password_confirmation"
            type="password"
            autocomplete="new-password"
            placeholder="请再次输入密码"
            minlength="8"
            show-password
            :disabled="submitting"
            required
          />
        </ElFormItem>

        <ElButton
          class="register-submit"
          data-test="register-submit"
          native-type="submit"
          type="primary"
          :loading="submitting"
          :disabled="submitting"
        >
          注册
        </ElButton>
      </ElForm>

      <p class="login-link">已有账户？<RouterLink to="/login">返回登录</RouterLink></p>
    </ElCard>
  </main>
</template>

<style scoped>
.register-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 2rem 1rem;
  background:
    radial-gradient(circle at 12% 18%, rgb(37 99 235 / 12%), transparent 32rem),
    var(--gateway-bg);
}

.register-card {
  width: min(100%, 28rem);
  border-color: var(--gateway-border);
  border-radius: 1rem;
  box-shadow: 0 1.5rem 4rem rgb(23 32 51 / 10%);
}

.register-heading {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1rem;
}

.register-heading__mark {
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

.register-heading__eyebrow {
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

.registration-policy {
  margin: 0 0 1.25rem;
  color: var(--gateway-muted);
  font-size: 0.875rem;
  line-height: 1.6;
}

.register-alert {
  margin-bottom: 1rem;
}

.register-submit {
  width: 100%;
  margin-top: 0.5rem;
}

.login-link {
  margin: 1rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.875rem;
  text-align: center;
}

.login-link a {
  color: var(--gateway-brand);
  font-weight: 600;
}
</style>
