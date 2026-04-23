<template>
  <div class="profile-page">
    <!-- User Profile Card -->
    <div class="profile-card">
      <div class="profile-avatar">
        <span class="avatar-text">{{ user?.email?.charAt(0).toUpperCase() || 'U' }}</span>
      </div>
      <div class="profile-info">
        <div class="profile-header-row">
          <h2 class="profile-email">{{ user?.email }}</h2>
          <el-button class="settings-btn" @click="settingsDialogVisible = true">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd" />
            </svg>
            <span>设置</span>
          </el-button>
        </div>
        <div class="profile-badges">
          <span class="badge" :class="user?.role === 'ADMIN' ? 'badge-danger' : 'badge-info'">
            {{ user?.role }}
          </span>
          <span class="badge" :class="user?.totpEnabled ? 'badge-success' : 'badge-default'">
            TOTP: {{ user?.totpEnabled ? '已启用' : '未启用' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon stat-icon-blue">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">余额</div>
          <div class="stat-value">{{ formatCurrency(user?.balance || 0) }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon stat-icon-green">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">创建时间</div>
          <div class="stat-value text-base">{{ formatDate(user?.createdAt || '') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon stat-icon-purple">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">有效期至</div>
          <div class="stat-value text-base">{{ user?.validUntil ? formatDate(user.validUntil) : '永久' }}</div>
        </div>
      </div>
    </div>

    <!-- Usage Stats Section -->
    <div class="usage-section">
      <div class="usage-header">
        <div class="usage-title">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z" />
            <path d="M12 2.25a2.25 2.25 0 00-2.25 2.25v.5a2.25 2.25 0 002.25 2.25h.5a2.25 2.25 0 002.25-2.25v-.5a2.25 2.25 0 00-2.25-2.25h-.5z" />
          </svg>
          <span>使用量统计</span>
        </div>
        <span class="usage-period">近 30 天</span>
      </div>

      <!-- Token Stats -->
      <div class="token-stats">
        <div class="token-stat">
          <div class="token-stat-label">输入 Token</div>
          <div class="token-stat-value">{{ formatNumber(userStats?.totalUsage?.promptTokens || 0) }}</div>
        </div>
        <div class="token-stat">
          <div class="token-stat-label">输出 Token</div>
          <div class="token-stat-value">{{ formatNumber(userStats?.totalUsage?.completionTokens || 0) }}</div>
        </div>
        <div class="token-stat token-stat-total">
          <div class="token-stat-label">总计</div>
          <div class="token-stat-value">{{ formatNumber(userStats?.totalUsage?.totalTokens || 0) }}</div>
        </div>
      </div>

      <!-- Daily Usage Chart -->
      <div class="daily-chart-section">
        <div class="chart-title">每日使用趋势</div>
        <div ref="dailyChartRef" class="daily-chart"></div>
      </div>

      <!-- Model Usage -->
      <div v-if="userStats?.usageByModel?.length" class="model-usage">
        <div class="model-usage-title">按模型统计</div>
        <div class="model-usage-list">
          <div v-for="model in userStats?.usageByModel" :key="model.name" class="model-usage-item">
            <div class="model-name">{{ model.name }}</div>
            <div class="model-stats">
              <span>{{ formatNumber(model.totalTokens) }} tokens</span>
              <span>{{ model.requestCount }} 次</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Settings Dialog -->
    <el-dialog v-model="settingsDialogVisible" title="" width="400px" destroy-on-close class="settings-dialog">
      <div class="dialog-content">
        <!-- Change Password Section -->
        <div class="dialog-section">
          <div class="section-header">
            <div class="section-icon section-icon-blue">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd" />
              </svg>
            </div>
            <span class="section-title">修改密码</span>
          </div>
          <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top" class="section-form">
            <el-form-item :label="t('profile.currentPassword')" prop="current_password">
              <el-input v-model="passwordForm.current_password" type="password" show-password placeholder="输入当前密码" />
            </el-form-item>
            <el-form-item :label="t('profile.newPassword')" prop="new_password">
              <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="输入新密码" />
            </el-form-item>
            <el-form-item :label="t('profile.confirmPassword')" prop="confirm_password">
              <el-input v-model="passwordForm.confirm_password" type="password" show-password placeholder="确认新密码" />
            </el-form-item>
            <el-button type="primary" @click="changePassword" :loading="passwordLoading" class="w-full">
              保存密码
            </el-button>
          </el-form>
        </div>

        <!-- Divider -->
        <div class="dialog-divider"></div>

        <!-- TOTP Section -->
        <div class="dialog-section">
          <div class="section-header">
            <div class="section-icon" :class="user?.totpEnabled ? 'section-icon-green' : 'section-icon-gray'">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
              </svg>
            </div>
            <span class="section-title">双因素认证</span>
          </div>
          <div v-if="!user?.totpEnabled" class="totp-content">
            <div class="totp-status-card totp-disabled">
              <div class="totp-status-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                </svg>
              </div>
              <div class="totp-status-text">
                <span class="totp-status-title">未启用</span>
                <span class="totp-status-desc">启用双因素认证可增强账户安全性</span>
              </div>
            </div>
            <el-button type="primary" @click="setupTotp" class="w-full totp-btn">
              <el-icon class="mr-1"><Plus /></el-icon>
              启用双因素认证
            </el-button>
          </div>
          <div v-else class="totp-content">
            <div class="totp-status-card totp-enabled">
              <div class="totp-status-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
              </div>
              <div class="totp-status-text">
                <span class="totp-status-title">已启用</span>
                <span class="totp-status-desc">您的账户受到额外保护</span>
              </div>
            </div>
            <el-button type="danger" plain @click="disableTotp" class="w-full totp-btn">
              禁用双因素认证
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- TOTP Setup Dialog -->
    <el-dialog v-model="totpSetupDialogVisible" title="设置 TOTP" width="480px" destroy-on-close>
      <div v-if="totpSetupData" class="totp-dialog">
        <p class="totp-instruction">使用验证器应用扫描二维码：</p>
        <div class="totp-qr">
          <img :src="totpSetupData.qrCodeDataUrl" alt="TOTP QR Code" />
        </div>
        <div class="totp-secret">
          <span class="totp-secret-label">或手动输入密钥：</span>
          <div class="totp-secret-value">
            <code class="totp-secret-code">{{ totpSetupData.secret }}</code>
            <el-button size="small" text @click="copySecret">复制</el-button>
          </div>
        </div>
        <el-form ref="totpVerifyFormRef" :model="totpVerifyForm" :rules="totpVerifyRules" class="mt-4">
          <el-form-item label="验证码" prop="token">
            <el-input v-model="totpVerifyForm.token" maxlength="6" placeholder="输入 6 位验证码" class="totp-input" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="totpSetupDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="verifyTotp" :loading="totpLoading">{{ t('profile.totpEnable') }}</el-button>
      </template>
    </el-dialog>

    <!-- Disable TOTP Dialog -->
    <el-dialog v-model="totpDisableDialogVisible" title="禁用 TOTP" width="380px" destroy-on-close>
      <div class="totp-dialog">
        <p class="totp-instruction">请输入密码和验证码以禁用双因素认证：</p>
        <el-form ref="totpDisableFormRef" :model="totpDisableForm" :rules="totpDisableRules" class="mt-4" label-position="top">
          <el-form-item label="密码" prop="password">
            <el-input v-model="totpDisableForm.password" type="password" show-password placeholder="输入密码" />
          </el-form-item>
          <el-form-item label="验证码" prop="token">
            <el-input v-model="totpDisableForm.token" maxlength="6" placeholder="输入 6 位验证码" class="totp-input" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="totpDisableDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" @click="confirmDisableTotp" :loading="totpLoading">{{ t('profile.totpDisable') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from '@/plugins/element-plus-services'
import { Plus } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import echarts, { type ECharts } from '@/utils/echarts'

import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import type { TotpSetupResponse } from '@/types/totp'
import dayjs from 'dayjs'

interface UserStats {
  totalUsage: {
    promptTokens: number
    completionTokens: number
    totalTokens: number
  }
  dailyUsage: Array<{
    date: string
    requestCount: number
    promptTokens: number
    completionTokens: number
    totalTokens: number
    cost: number
  }>
  usageByModel: Array<{
    name: string
    requestCount: number
    promptTokens: number
    completionTokens: number
    totalTokens: number
    cost: number
  }>
}

const { t } = useI18n()
const authStore = useAuthStore()
const user = computed(() => authStore.user)

const userStats = ref<UserStats | null>(null)
const statsLoading = ref(false)

// Chart
const dailyChartRef = ref<HTMLElement | null>(null)
let dailyChart: ECharts | null = null

const passwordFormRef = ref<FormInstance>()
const totpVerifyFormRef = ref<FormInstance>()
const totpDisableFormRef = ref<FormInstance>()

const passwordLoading = ref(false)
const totpLoading = ref(false)
const settingsDialogVisible = ref(false)
const totpSetupDialogVisible = ref(false)
const totpDisableDialogVisible = ref(false)
const totpSetupData = ref<TotpSetupResponse | null>(null)

const passwordForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: ''
})

const totpVerifyForm = reactive({
  token: ''
})

const totpDisableForm = reactive({
  password: '',
  token: ''
})

const passwordRules: FormRules = {
  current_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 个字符', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== passwordForm.new_password) {
          callback(new Error('两次密码输入不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

const totpVerifyRules: FormRules = {
  token: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { pattern: /^\d{6}$/, message: '验证码必须是 6 位数字', trigger: 'blur' }
  ]
}

const totpDisableRules: FormRules = {
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  token: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { pattern: /^\d{6}$/, message: '验证码必须是 6 位数字', trigger: 'blur' }
  ]
}

const formatCurrency = (num: number) => '$' + num.toFixed(4)
const formatDate = (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm')
const formatNumber = (num: number) => num.toLocaleString()

const fetchUserStats = async () => {
  statsLoading.value = true
  try {
    const response = await authApi.getUserStats()
    userStats.value = response.data as UserStats
    await nextTick()
    updateDailyChart()
  } catch (error) {
    console.error('Failed to fetch user stats:', error)
  } finally {
    statsLoading.value = false
  }
}

// Generate date range for last 30 days
const generateDateRange = (days: number): string[] => {
  const dates: string[] = []
  const today = new Date()
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(today)
    date.setDate(date.getDate() - i)
    dates.push(date.toISOString().slice(0, 10))
  }
  return dates
}

// Fill missing dates with zero values
const fillMissingDates = (
  data: Array<{ date: string; totalTokens: number; promptTokens: number; completionTokens: number; requestCount: number }>,
  dateRange: string[]
) => {
  const dataMap = new Map(data.map(d => [d.date, d]))
  return dateRange.map(date => {
    const existing = dataMap.get(date)
    return existing || { date, totalTokens: 0, promptTokens: 0, completionTokens: 0, requestCount: 0 }
  })
}

// Initialize daily usage chart
const updateDailyChart = () => {
  if (!dailyChartRef.value || !userStats.value?.dailyUsage) return

  if (!dailyChart) {
    dailyChart = echarts.init(dailyChartRef.value)
  }

  const dateRange = generateDateRange(30)
  const data = fillMissingDates(userStats.value.dailyUsage, dateRange)

  const option = {
    grid: {
      top: 20,
      right: 20,
      bottom: 30,
      left: 50
    },
    xAxis: {
      type: 'category',
      data: data.map(d => d.date.slice(5)), // MM-DD format
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: { color: '#6b7280', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f3f4f6' } },
      axisLabel: { color: '#6b7280', fontSize: 11 }
    },
    series: [
      {
        name: 'Tokens',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: data.map(d => d.totalTokens),
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99, 102, 241, 0.3)' },
            { offset: 1, color: 'rgba(99, 102, 241, 0.05)' }
          ])
        },
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' }
      }
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      textStyle: { color: '#374151' },
      formatter: (params: any) => {
        const idx = params[0].dataIndex
        const d = data[idx]
        return `
          <div style="font-weight: 500; margin-bottom: 4px;">${d.date}</div>
          <div style="display: flex; gap: 12px; font-size: 12px;">
            <span>Tokens: ${d.totalTokens.toLocaleString()}</span>
            <span>请求: ${d.requestCount}</span>
          </div>
        `
      }
    }
  }

  dailyChart.setOption(option)
}

onMounted(() => {
  fetchUserStats()
})

onUnmounted(() => {
  if (dailyChart) {
    dailyChart.dispose()
  }
})

const changePassword = async () => {
  if (!passwordFormRef.value) return
  try {
    await passwordFormRef.value.validate()
  } catch {
    return
  }

  passwordLoading.value = true
  try {
    await authApi.changePassword({
      currentPassword: passwordForm.current_password,
      newPassword: passwordForm.new_password
    })
    ElMessage.success(t('common.success'))
    passwordForm.current_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    passwordLoading.value = false
  }
}

const setupTotp = async () => {
  totpLoading.value = true
  try {
    const response = await authApi.setupTotp()
    totpSetupData.value = response.data
    totpSetupDialogVisible.value = true
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    totpLoading.value = false
  }
}

const copySecret = async () => {
  if (!totpSetupData.value) return
  try {
    await navigator.clipboard.writeText(totpSetupData.value.secret)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

const verifyTotp = async () => {
  if (!totpVerifyFormRef.value) return
  try {
    await totpVerifyFormRef.value.validate()
  } catch {
    return
  }

  totpLoading.value = true
  try {
    await authApi.verifyTotp({ token: totpVerifyForm.token })
    ElMessage.success(t('common.success'))
    totpSetupDialogVisible.value = false
    await authStore.fetchCurrentUser()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    totpLoading.value = false
  }
}

const disableTotp = () => {
  totpDisableForm.password = ''
  totpDisableForm.token = ''
  totpDisableDialogVisible.value = true
}

const confirmDisableTotp = async () => {
  if (!totpDisableFormRef.value) return
  try {
    await totpDisableFormRef.value.validate()
  } catch {
    return
  }

  totpLoading.value = true
  try {
    await authApi.disableTotp({
      password: totpDisableForm.password,
      token: totpDisableForm.token
    })
    ElMessage.success(t('common.success'))
    totpDisableDialogVisible.value = false
    await authStore.fetchCurrentUser()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    totpLoading.value = false
  }
}
</script>

<style>
.profile-page {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Profile Card */
.profile-card {
  display: flex;
  align-items: center;
  gap: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  padding: 32px;
  color: white;
}
.profile-avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.avatar-text {
  font-size: 28px;
  font-weight: 600;
}
.profile-email {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 8px 0;
}
.profile-header-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.settings-btn {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  padding: 6px 14px;
  font-size: 13px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.settings-btn:hover {
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.4);
}
.profile-badges {
  display: flex;
  gap: 8px;
}
.badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}
.badge-danger { background: #fef2f2; color: #dc2626; }
.badge-info { background: #eff6ff; color: #2563eb; }
.badge-success { background: #dcfce7; color: #16a34a; }
.badge-default { background: rgba(255,255,255,0.2); color: white; }

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.stat-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-icon-blue { background: #eff6ff; color: #2563eb; }
.stat-icon-green { background: #dcfce7; color: #16a34a; }
.stat-icon-purple { background: #f3e8ff; color: #9333ea; }
.stat-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}
.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}
.stat-value.text-base {
  font-size: 15px;
}

/* Usage Section */
.usage-section {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
}
.usage-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.usage-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}
.usage-title svg {
  color: #6366f1;
}
.usage-period {
  font-size: 12px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 4px 12px;
  border-radius: 20px;
}

/* Token Stats */
.token-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.token-stat {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.token-stat-total {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
}
.token-stat-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 8px;
}
.token-stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

/* Daily Chart */
.daily-chart-section {
  border-top: 1px solid #e5e7eb;
  padding-top: 20px;
  margin-bottom: 20px;
}
.chart-title {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  margin-bottom: 12px;
}
.daily-chart {
  height: 200px;
  width: 100%;
}

/* Model Usage */
.model-usage {
  border-top: 1px solid #e5e7eb;
  padding-top: 20px;
}
.model-usage-title {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  margin-bottom: 12px;
}
.model-usage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.model-usage-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f9fafb;
  border-radius: 6px;
  padding: 12px 16px;
}
.model-name {
  font-size: 14px;
  font-weight: 500;
  color: #111827;
}
.model-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #6b7280;
}

/* Settings Dialog */
.settings-dialog .el-dialog__header {
  padding: 0;
}
.settings-dialog .el-dialog__body {
  padding: 24px;
}
.dialog-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.dialog-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.section-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.section-icon svg {
  width: 20px;
  height: 20px;
}
.section-icon-blue { background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }
.section-icon-green { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; }
.section-icon-gray { background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%); color: white; }
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}
.section-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-form .el-form-item {
  margin-bottom: 0;
}
.section-form .el-form-item__label {
  font-size: 13px;
  color: #6b7280;
  padding-bottom: 4px;
}
.dialog-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, #e5e7eb 20%, #e5e7eb 80%, transparent);
}

/* TOTP Content */
.totp-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.totp-status-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
}
.totp-disabled {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}
.totp-enabled {
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border: 1px solid #a7f3d0;
}
.totp-status-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.totp-disabled .totp-status-icon {
  background: #fee2e2;
  color: #dc2626;
}
.totp-enabled .totp-status-icon {
  background: #86efac;
  color: #166534;
}
.totp-status-icon svg {
  width: 20px;
  height: 20px;
}
.totp-status-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.totp-status-title {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}
.totp-status-desc {
  font-size: 12px;
  color: #6b7280;
}
.totp-btn {
  margin-top: 4px;
}

/* TOTP Dialog */
.totp-dialog {
  text-align: center;
}
.totp-instruction {
  color: #374151;
  margin-bottom: 16px;
}
.totp-qr {
  display: inline-block;
  padding: 16px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  margin-bottom: 16px;
}
.totp-qr img {
  width: 180px;
  height: 180px;
}
.totp-secret {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px;
  text-align: left;
}
.totp-secret-label {
  font-size: 12px;
  color: #6b7280;
  display: block;
  margin-bottom: 8px;
}
.totp-secret-value {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.totp-secret-code {
  font-family: 'SF Mono', monospace;
  font-size: 13px;
  color: #111827;
  word-break: break-all;
  flex: 1;
}
.totp-input {
  text-align: center;
  letter-spacing: 0.5em;
}
.totp-input input {
  text-align: center;
}

/* Responsive */
@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  .token-stats {
    grid-template-columns: 1fr;
  }
  .profile-card {
    flex-direction: column;
    text-align: center;
  }
  .profile-header-row {
    flex-direction: column;
    gap: 8px;
  }
  .profile-badges {
    justify-content: center;
  }
}
</style>
