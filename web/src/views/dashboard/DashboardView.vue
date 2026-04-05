<template>
  <div class="dashboard-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>{{ t('dashboard.title') }}</h1>
      <p>AI Gateway usage statistics and analytics</p>
    </div>

    <!-- User Stats Cards (Admin Only) -->
    <div v-if="isAdmin && stats?.userStats" class="stats-grid user-stats">
      <div class="stat-card stat-card--indigo">
        <div class="stat-icon">
          <span>👥</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.userStats.total }}</div>
          <div class="stat-label">{{ t('users.title') }}</div>
        </div>
      </div>
      <div class="stat-card stat-card--green">
        <div class="stat-icon">
          <span>✅</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.userStats.active }}</div>
          <div class="stat-label">{{ t('users.active') }}</div>
        </div>
      </div>
      <div class="stat-card stat-card--red">
        <div class="stat-icon">
          <span>🚫</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.userStats.disabled }}</div>
          <div class="stat-label">{{ t('users.disabled') }}</div>
        </div>
      </div>
      <div class="stat-card stat-card--amber">
        <div class="stat-icon">
          <span>⏰</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.userStats.expired }}</div>
          <div class="stat-label">{{ t('users.validUntil') }}</div>
        </div>
      </div>
    </div>

    <!-- Key Metrics Cards -->
    <div class="stats-grid">
      <div class="stat-card stat-card--blue">
        <div class="stat-icon">
          <span>🚀</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ formatNumber(stats?.totalRequests || 0) }}</div>
          <div class="stat-label">{{ t('dashboard.totalRequests') }}</div>
        </div>
      </div>

      <div class="stat-card stat-card--purple">
        <div class="stat-icon">
          <span>🪙</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ formatNumber(stats?.totalTokens || 0) }}</div>
          <div class="stat-label">{{ t('dashboard.totalTokens') }}</div>
        </div>
      </div>

      <div class="stat-card stat-card--green">
        <div class="stat-icon">
          <span>💰</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ formatCost(stats?.totalCost || 0) }}</div>
          <div class="stat-label">{{ t('dashboard.totalCost') }}</div>
        </div>
      </div>

      <div class="stat-card stat-card--amber">
        <div class="stat-icon">
          <span>📦</span>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ providerCount }} / {{ modelCount }}</div>
          <div class="stat-label">{{ t('dashboard.providers') }} / {{ t('dashboard.models') }}</div>
        </div>
      </div>
    </div>

    <!-- Charts Section - Row 1 -->
    <div class="charts-grid">
      <div class="chart-section">
        <div class="section-header">
          <h2>{{ t('dashboard.dailyUsage') }}</h2>
        </div>
        <div class="chart-container">
          <div ref="dailyChartRef" class="chart"></div>
        </div>
      </div>

      <div class="chart-section">
        <div class="section-header">
          <h2>{{ t('dashboard.weeklyUsage') }}</h2>
        </div>
        <div class="chart-container">
          <div ref="weeklyChartRef" class="chart"></div>
        </div>
      </div>
    </div>

    <!-- Charts Section - Row 2 -->
    <div class="charts-grid">
      <div class="chart-section">
        <div class="section-header">
          <h2>{{ t('dashboard.tokenUsageOverTime') }}</h2>
        </div>
        <div class="chart-container">
          <div ref="tokenChartRef" class="chart"></div>
        </div>
      </div>

      <div class="chart-section">
        <div class="section-header">
          <h2>每周请求统计</h2>
        </div>
        <div class="chart-container">
          <div ref="monthlyChartRef" class="chart"></div>
        </div>
      </div>
    </div>

    <!-- User Token Usage Chart (Admin Only) -->
    <div v-if="isAdmin && stats?.userTokenUsageOverTime?.length" class="chart-section full-width">
      <div class="section-header">
        <h2>{{ t('dashboard.userTokenUsage') }}</h2>
      </div>
      <div class="chart-container">
        <div ref="userTokenChartRef" class="chart"></div>
      </div>
    </div>

    <!-- Stats Tables -->
    <div class="tables-grid">
      <div class="table-section">
        <div class="section-header">
          <h2>{{ t('dashboard.byProvider') }}</h2>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('dashboard.name') }}</th>
                <th>{{ t('dashboard.promptTokens') }}</th>
                <th>{{ t('dashboard.completionTokens') }}</th>
                <th>{{ t('dashboard.totalTokens') }}</th>
                <th>{{ t('dashboard.requestCount') }}</th>
                <th>{{ t('dashboard.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in stats?.byProvider" :key="item.name">
                <td><span class="badge">{{ item.name }}</span></td>
                <td>{{ formatNumber(item.promptTokens) }}</td>
                <td>{{ formatNumber(item.completionTokens) }}</td>
                <td class="font-semibold">{{ formatNumber(item.tokens) }}</td>
                <td>{{ formatNumber(item.requests) }}</td>
                <td>{{ formatCost(item.cost) }}</td>
              </tr>
              <tr v-if="!stats?.byProvider?.length">
                <td colspan="6" class="empty-cell">{{ t('common.noData') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="table-section">
        <div class="section-header">
          <h2>{{ t('dashboard.byModel') }}</h2>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('dashboard.name') }}</th>
                <th>{{ t('dashboard.promptTokens') }}</th>
                <th>{{ t('dashboard.completionTokens') }}</th>
                <th>{{ t('dashboard.totalTokens') }}</th>
                <th>{{ t('dashboard.requestCount') }}</th>
                <th>{{ t('dashboard.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in stats?.byModel" :key="item.name">
                <td><span class="badge">{{ item.name }}</span></td>
                <td>{{ formatNumber(item.promptTokens) }}</td>
                <td>{{ formatNumber(item.completionTokens) }}</td>
                <td class="font-semibold">{{ formatNumber(item.tokens) }}</td>
                <td>{{ formatNumber(item.requests) }}</td>
                <td>{{ formatCost(item.cost) }}</td>
              </tr>
              <tr v-if="!stats?.byModel?.length">
                <td colspan="6" class="empty-cell">{{ t('common.noData') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Additional Tables -->
    <div class="tables-grid">
      <div class="table-section">
        <div class="section-header">
          <h2>{{ t('dashboard.byApiKey') }}</h2>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('dashboard.name') }}</th>
                <th>{{ t('dashboard.promptTokens') }}</th>
                <th>{{ t('dashboard.completionTokens') }}</th>
                <th>{{ t('dashboard.totalTokens') }}</th>
                <th>{{ t('dashboard.requestCount') }}</th>
                <th>{{ t('dashboard.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in stats?.byApiKey" :key="item.name">
                <td><span class="badge">{{ item.name }}</span></td>
                <td>{{ formatNumber(item.promptTokens) }}</td>
                <td>{{ formatNumber(item.completionTokens) }}</td>
                <td class="font-semibold">{{ formatNumber(item.tokens) }}</td>
                <td>{{ formatNumber(item.requests) }}</td>
                <td>{{ formatCost(item.cost) }}</td>
              </tr>
              <tr v-if="!stats?.byApiKey?.length">
                <td colspan="6" class="empty-cell">{{ t('common.noData') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- byUser Table (Admin Only) -->
      <div v-if="isAdmin" class="table-section">
        <div class="section-header">
          <h2>{{ t('dashboard.byUser') }}</h2>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('user.email') }}</th>
                <th>{{ t('dashboard.promptTokens') }}</th>
                <th>{{ t('dashboard.completionTokens') }}</th>
                <th>{{ t('dashboard.totalTokens') }}</th>
                <th>{{ t('dashboard.requestCount') }}</th>
                <th>{{ t('dashboard.cost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in stats?.byUser" :key="item.name">
                <td><span class="badge">{{ item.name }}</span></td>
                <td>{{ formatNumber(item.promptTokens) }}</td>
                <td>{{ formatNumber(item.completionTokens) }}</td>
                <td class="font-semibold">{{ formatNumber(item.tokens) }}</td>
                <td>{{ formatNumber(item.requests) }}</td>
                <td>{{ formatCost(item.cost) }}</td>
              </tr>
              <tr v-if="!stats?.byUser?.length">
                <td colspan="6" class="empty-cell">{{ t('common.noData') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts'
import { statsApi } from '@/api/stats'
import type { Stats } from '@/types/stats'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()
const user = computed(() => authStore.user)
const isAdmin = computed(() => user.value?.role === 'ADMIN')

// Chart refs
const dailyChartRef = ref<HTMLElement | null>(null)
const weeklyChartRef = ref<HTMLElement | null>(null)
const tokenChartRef = ref<HTMLElement | null>(null)
const monthlyChartRef = ref<HTMLElement | null>(null)
const userTokenChartRef = ref<HTMLElement | null>(null)

// Chart instances
let dailyChart: echarts.ECharts | null = null
let weeklyChart: echarts.ECharts | null = null
let tokenChart: echarts.ECharts | null = null
let monthlyChart: echarts.ECharts | null = null
let userTokenChart: echarts.ECharts | null = null

const stats = ref<Stats | null>(null)
const providerCount = ref(0)
const modelCount = ref(0)

const CHART_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f59e0b', '#10b981', '#0ea5e9', '#8b5cf6']

const formatNumber = (num: number) => {
  if (num === undefined || num === null) return '0'
  return num.toLocaleString()
}

const formatCost = (num: number) => {
  if (num === undefined || num === null) return '$0.0000'
  return '$' + num.toFixed(4)
}

// Generate date range array
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
  data: Array<{ date: string; tokens: number; requests: number; promptTokens: number; completionTokens: number }>,
  dateRange: string[]
) => {
  const dataMap = new Map(data.map(d => [d.date, d]))
  return dateRange.map(date => {
    const existing = dataMap.get(date)
    return existing || { date, tokens: 0, requests: 0, promptTokens: 0, completionTokens: 0 }
  })
}

const fetchStats = async () => {
  try {
    const response = await statsApi.getStats()
    stats.value = response.data as Stats

    // Get provider and model counts from API response
    providerCount.value = (stats.value?.providerCount || 0)
    modelCount.value = (stats.value?.modelCount || 0)

    await nextTick()
    updateCharts()
  } catch (error) {
    console.error('Failed to fetch stats:', error)
  }
}

const initChart = (ref: HTMLElement | null): echarts.ECharts | null => {
  if (!ref) return null
  return echarts.init(ref)
}

const updateCharts = () => {
  // Daily Usage Chart - fill missing dates for 30 days
  if (dailyChart && stats.value?.dailyUsage) {
    const dateRange = generateDateRange(30)
    const data = fillMissingDates(stats.value.dailyUsage.map(d => ({
      date: d.date,
      tokens: d.tokens || 0,
      requests: d.requests || 0,
      promptTokens: d.promptTokens || 0,
      completionTokens: d.completionTokens || 0
    })), dateRange)

    dailyChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['Tokens', 'Requests'], bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), boundaryGap: false },
      yAxis: [
        { type: 'value', name: 'Tokens', position: 'left' },
        { type: 'value', name: 'Requests', position: 'right' }
      ],
      series: [
        { name: 'Tokens', type: 'line', data: data.map(d => d.tokens), smooth: true, lineStyle: { color: '#6366f1', width: 2 }, areaStyle: { color: 'rgba(99, 102, 241, 0.1)' } },
        { name: 'Requests', type: 'line', yAxisIndex: 1, data: data.map(d => d.requests), smooth: true, lineStyle: { color: '#10b981', width: 2 } }
      ]
    })
  }

  // Weekly Usage Chart (last 14 days daily data)
  if (weeklyChart && stats.value?.weeklyUsage) {
    const dateRange = generateDateRange(14)
    const data = fillMissingDates(stats.value.weeklyUsage.map(d => ({
      date: d.date,
      tokens: d.tokens || 0,
      requests: d.requests || 0,
      promptTokens: d.promptTokens || 0,
      completionTokens: d.completionTokens || 0
    })), dateRange)

    weeklyChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['Tokens', 'Requests'], bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), boundaryGap: false },
      yAxis: [
        { type: 'value', name: 'Tokens', position: 'left' },
        { type: 'value', name: 'Requests', position: 'right' }
      ],
      series: [
        { name: 'Tokens', type: 'line', data: data.map(d => d.tokens), smooth: true, lineStyle: { color: '#8b5cf6', width: 2 } },
        { name: 'Requests', type: 'line', yAxisIndex: 1, data: data.map(d => d.requests), smooth: true, lineStyle: { color: '#10b981', width: 2 } }
      ]
    })
  }

  // Token Usage Over Time Chart (Prompt vs Completion)
  if (tokenChart && stats.value?.tokenUsageOverTime) {
    const dateRange = generateDateRange(30)
    const data = fillMissingDates(stats.value.tokenUsageOverTime.map(d => ({
      date: d.date,
      tokens: d.tokens || 0,
      requests: d.requests || 0,
      promptTokens: d.promptTokens || 0,
      completionTokens: d.completionTokens || 0
    })), dateRange)

    tokenChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: [t('dashboard.promptTokens'), t('dashboard.completionTokens')], bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), boundaryGap: false },
      yAxis: { type: 'value', name: 'Tokens' },
      series: [
        { name: t('dashboard.promptTokens'), type: 'bar', data: data.map(d => d.promptTokens), itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] } },
        { name: t('dashboard.completionTokens'), type: 'bar', data: data.map(d => d.completionTokens), itemStyle: { color: '#10b981', borderRadius: [4, 4, 0, 0] } }
      ]
    })
  }

  // Monthly/Weekly Requests Chart (12 weeks aggregated)
  if (monthlyChart && stats.value?.monthlyUsage) {
    const data = stats.value.monthlyUsage
    monthlyChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['Requests', 'Tokens'], bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: { type: 'category', data: data.map(d => d.date), boundaryGap: false },
      yAxis: [
        { type: 'value', name: 'Requests', position: 'left' },
        { type: 'value', name: 'Tokens', position: 'right' }
      ],
      series: [
        { name: 'Requests', type: 'bar', data: data.map(d => d.requests), itemStyle: { color: '#ec4899', borderRadius: [4, 4, 0, 0] } },
        { name: 'Tokens', type: 'line', yAxisIndex: 1, data: data.map(d => d.tokens), smooth: true, lineStyle: { color: '#6366f1', width: 2 } }
      ]
    })
  }

  // User Token Usage Chart (Multi-line)
  if (userTokenChart && stats.value?.userTokenUsageOverTime) {
    const userData = stats.value.userTokenUsageOverTime

    // Get all unique dates
    const allDates = new Set<string>()
    userData.forEach(user => {
      user.data.forEach(d => allDates.add(d.date))
    })
    const sortedDates = Array.from(allDates).sort()

    // Transform data for chart
    const chartData = sortedDates.map(date => {
      const dataPoint: Record<string, number | string> = { date }
      userData.forEach(user => {
        const userDayData = user.data.find(d => d.date === date)
        dataPoint[user.userName] = userDayData ? userDayData.tokens : 0
      })
      return dataPoint
    })

    userTokenChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: userData.map(u => u.userName), bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
      xAxis: { type: 'category', data: sortedDates, boundaryGap: false },
      yAxis: { type: 'value', name: 'Tokens' },
      series: userData.map((user, index) => ({
        name: user.userName,
        type: 'line',
        data: chartData.map(d => d[user.userName] as number),
        smooth: true,
        lineStyle: { color: CHART_COLORS[index % CHART_COLORS.length], width: 2 }
      }))
    })
  }
}

onMounted(() => {
  dailyChart = initChart(dailyChartRef.value)
  weeklyChart = initChart(weeklyChartRef.value)
  tokenChart = initChart(tokenChartRef.value)
  monthlyChart = initChart(monthlyChartRef.value)
  if (isAdmin.value) {
    userTokenChart = initChart(userTokenChartRef.value)
  }
  fetchStats()
})

// Handle window resize
onMounted(() => {
  window.addEventListener('resize', () => {
    dailyChart?.resize()
    weeklyChart?.resize()
    tokenChart?.resize()
    monthlyChart?.resize()
    userTokenChart?.resize()
  })
})
</script>

<style scoped>
.dashboard-page {
  padding: 0;
}

/* 页面标题 */
.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 4px 0;
}

.page-header p {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 24px;
  min-width: 0; /* 防止内容溢出 */
}

.stats-grid.user-stats {
  grid-template-columns: repeat(2, 1fr);
}

.stat-card {
  background: white;
  border-radius: 16px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
  min-width: 0; /* 防止内容溢出 */
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 20px;
}

.stat-card--blue .stat-icon { background: #dbeafe; }
.stat-card--green .stat-icon { background: #d1fae5; }
.stat-card--purple .stat-icon { background: #ede9fe; }
.stat-card--amber .stat-icon { background: #fef3c7; }
.stat-card--indigo .stat-icon { background: #e0e7ff; }
.stat-card--red .stat-icon { background: #fee2e2; }

.stat-content {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  color: #64748b;
  margin-top: 2px;
}

/* 图表区域 */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  margin-bottom: 24px;
}

.chart-section {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.chart-section.full-width {
  grid-column: span 2;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.chart-container {
  width: 100%;
}

.chart {
  width: 100%;
  height: 300px;
}

/* 数据表格 */
.tables-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  margin-bottom: 24px;
}

.table-section {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid #f1f5f9;
}

.data-table th {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.data-table td {
  font-size: 14px;
  color: #334155;
}

.data-table tbody tr:hover {
  background-color: #f8fafc;
}

.badge {
  display: inline-block;
  padding: 4px 10px;
  background: #f1f5f9;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
}

.empty-cell {
  text-align: center;
  color: #94a3b8;
  padding: 24px !important;
}

.font-semibold {
  font-weight: 600;
}

/* 响应式 */
/* 平板及以上：4列布局 */
@media (min-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
  }

  .stats-grid.user-stats {
    grid-template-columns: repeat(4, 1fr);
  }

  .stat-card {
    padding: 24px;
    gap: 20px;
  }

  .stat-icon {
    width: 56px;
    height: 56px;
    border-radius: 14px;
    font-size: 24px;
  }

  .stat-value {
    font-size: 28px;
  }

  .stat-label {
    font-size: 14px;
    margin-top: 4px;
  }
}

@media (max-width: 768px) {
  .charts-grid,
  .tables-grid {
    grid-template-columns: 1fr;
  }

  .chart-section.full-width {
    grid-column: span 1;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>