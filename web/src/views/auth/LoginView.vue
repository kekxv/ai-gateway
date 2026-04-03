<template>
  <div class="login-container">
    <!-- 左侧品牌区域 -->
    <div class="brand-section">
      <div class="brand-content">
        <div class="brand-logo">
          <svg class="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h1 class="brand-title">AI Gateway</h1>
        <p class="brand-subtitle">智能 API 网关管理平台</p>
        <div class="brand-features">
          <div class="feature-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="feature-icon">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span>安全可靠</span>
          </div>
          <div class="feature-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="feature-icon">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>高效稳定</span>
          </div>
          <div class="feature-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="feature-icon">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
            <span>多模型支持</span>
          </div>
        </div>
      </div>
      <!-- 背景装饰 -->
      <div class="bg-decoration">
        <div class="circle circle-1"></div>
        <div class="circle circle-2"></div>
        <div class="circle circle-3"></div>
      </div>
    </div>

    <!-- 右侧登录区域 -->
    <div class="login-section">
      <div class="login-card">
        <div class="card-header">
          <h2>{{ t('login.title') }}</h2>
          <p>{{ t('login.subtitle') }}</p>
        </div>

        <div class="login-form">
          <div class="input-wrapper">
            <label class="input-label">{{ t('login.usernamePlaceholder') }}</label>
            <el-input
              v-model="form.username"
              :placeholder="t('login.usernamePlaceholder')"
              size="large"
              class="custom-input"
            >
              <template #prefix>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="input-icon">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </template>
            </el-input>
          </div>

          <div class="input-wrapper">
            <label class="input-label">{{ t('login.password') }}</label>
            <el-input
              v-model="form.password"
              type="password"
              :placeholder="t('login.password')"
              size="large"
              show-password
              class="custom-input"
            >
              <template #prefix>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="input-icon">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </template>
            </el-input>
          </div>

          <div v-if="showTotp" class="input-wrapper">
            <label class="input-label">{{ t('login.totpPlaceholder') }}</label>
            <el-input
              v-model="form.totp"
              :placeholder="t('login.totpPlaceholder')"
              size="large"
              maxlength="6"
              class="custom-input"
            >
              <template #prefix>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="input-icon">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.414-5.414a6 6 0 017.743-5.743L21 9z" />
                </svg>
              </template>
            </el-input>
          </div>

          <div class="form-options">
            <el-checkbox v-model="form.remember">{{ t('login.rememberMe') }}</el-checkbox>
          </div>

          <button
            type="button"
            class="submit-btn"
            :disabled="loading"
            @click="handleLogin"
          >
            <span v-if="!loading">{{ t('login.signIn') }}</span>
            <span v-else>登录中...</span>
          </button>

          <el-alert
            v-if="error"
            :title="t('login.failed')"
            type="error"
            :description="error"
            show-icon
            class="error-alert"
          />
        </div>

        <div class="card-footer">
          <p>AI Gateway &copy; {{ new Date().getFullYear() }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const loading = ref(false)
const error = ref('')
const showTotp = ref(true)

const form = reactive({
  username: '',
  password: '',
  totp: '',
  remember: false
})

const handleLogin = async () => {
  console.log('handleLogin called')

  // 简单验证
  if (!form.username) {
    error.value = t('validation.usernameRequired')
    return
  }
  if (!form.password) {
    error.value = t('validation.passwordRequired')
    return
  }

  loading.value = true
  error.value = ''

  try {
    console.log('calling authStore.login')
    const result = await authStore.login({
      email: form.username,
      password: form.password,
      totpToken: form.totp || undefined
    })
    console.log('login result:', result)

    if (result.success) {
      console.log('login success, navigating to dashboard')
      ElMessage.success(t('common.success'))
      router.push('/dashboard')
    } else {
      const errorMsg = result.error || t('login.failed')
      error.value = errorMsg
    }
  } catch (err: unknown) {
    console.error('login error:', err)
    const errorMsg = (err as { response?: { data?: { error?: string } } }).response?.data?.error || t('login.failed')
    error.value = errorMsg
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  min-height: 100vh;
  background: #f8fafc;
}

/* 左侧品牌区域 */
.brand-section {
  width: 50%;
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #a855f7 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.brand-content {
  text-align: center;
  color: white;
  z-index: 10;
  padding: 40px;
}

.brand-logo {
  width: 80px;
  height: 80px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
  backdrop-filter: blur(10px);
  animation: float 3s ease-in-out infinite;
}

.logo-icon {
  width: 40px;
  height: 40px;
  color: white;
}

.brand-title {
  font-size: 48px;
  font-weight: 700;
  margin-bottom: 12px;
  letter-spacing: -1px;
}

.brand-subtitle {
  font-size: 18px;
  opacity: 0.9;
  margin-bottom: 48px;
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.1);
  padding: 16px 24px;
  border-radius: 12px;
  backdrop-filter: blur(5px);
  transition: all 0.3s ease;
}

.feature-item:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: translateX(10px);
}

.feature-icon {
  width: 24px;
  height: 24px;
}

.feature-item span {
  font-size: 16px;
  font-weight: 500;
}

/* 背景装饰 */
.bg-decoration {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
}

.circle-1 {
  width: 400px;
  height: 400px;
  top: -100px;
  right: -100px;
  animation: pulse 4s ease-in-out infinite;
}

.circle-2 {
  width: 300px;
  height: 300px;
  bottom: -50px;
  left: -50px;
  animation: pulse 5s ease-in-out infinite 1s;
}

.circle-3 {
  width: 200px;
  height: 200px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: pulse 3s ease-in-out infinite 2s;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

@keyframes pulse {
  0%, 100% { opacity: 0.1; transform: scale(1); }
  50% { opacity: 0.2; transform: scale(1.1); }
}

/* 右侧登录区域 */
.login-section {
  width: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: white;
  border-radius: 24px;
  padding: 48px 40px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  animation: slideUp 0.5s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.card-header {
  text-align: center;
  margin-bottom: 32px;
}

.card-header h2 {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 8px;
}

.card-header p {
  font-size: 14px;
  color: #64748b;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-wrapper {
  width: 100%;
}

.input-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 8px;
}

.custom-input :deep(.el-input__wrapper) {
  border-radius: 12px;
  padding: 12px 16px;
  background: #f8fafc;
  border: 2px solid #e2e8f0;
  box-shadow: none;
  transition: all 0.3s ease;
}

.custom-input :deep(.el-input__wrapper:hover) {
  border-color: #a5b4fc;
  background: #fff;
}

.custom-input :deep(.el-input__wrapper.is-focus) {
  border-color: #6366f1;
  background: #fff;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.custom-input :deep(.el-input__inner) {
  font-size: 16px;
  color: #1e293b;
}

.input-icon {
  width: 20px;
  height: 20px;
  color: #6366f1;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.form-options :deep(.el-checkbox__label) {
  color: #64748b;
  font-size: 14px;
}

.submit-btn {
  width: 100%;
  height: 52px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  border: none;
  cursor: pointer;
  transition: all 0.3s ease;
  margin-top: 8px;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.3);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.error-alert {
  margin-top: 16px;
  border-radius: 12px;
}

.card-footer {
  text-align: center;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #e2e8f0;
}

.card-footer p {
  font-size: 12px;
  color: #94a3b8;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .brand-section {
    width: 40%;
  }

  .login-section {
    width: 60%;
  }

  .brand-title {
    font-size: 36px;
  }
}

@media (max-width: 768px) {
  .login-container {
    flex-direction: column;
  }

  .brand-section {
    width: 100%;
    min-height: 300px;
    padding: 40px 20px;
  }

  .brand-title {
    font-size: 32px;
  }

  .brand-features {
    display: none;
  }

  .login-section {
    width: 100%;
    padding: 20px;
  }

  .login-card {
    padding: 32px 24px;
    border-radius: 20px;
  }
}
</style>