<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { BarChart, type BarSeriesOption, LineChart, type LineSeriesOption } from 'echarts/charts'
import {
  AriaComponent,
  type AriaComponentOption,
  GridComponent,
  type GridComponentOption,
  LegendComponent,
  type LegendComponentOption,
  TooltipComponent,
  type TooltipComponentOption,
} from 'echarts/components'
import { type ComposeOption, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  ElButton,
  ElResult,
  ElSkeleton,
  ElSkeletonItem,
  ElTable,
  ElTableColumn,
} from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-table.css'
import VChart from 'vue-echarts'

import { getDashboardSummary, getUserDashboardSummary } from '@/api/dashboard'
import type { DashboardSummary, UserDashboardSummary } from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import {
  formatCompactInteger,
  formatDuration,
  formatInteger,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
} from '@/utils/format'

use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  LineChart,
  TooltipComponent,
])

type DashboardChartOption = ComposeOption<
  | AriaComponentOption
  | BarSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | LineSeriesOption
  | TooltipComponentOption
>

const auth = useAuthStore()

const adminSummary = ref<DashboardSummary | null>(null)
const userSummary = ref<UserDashboardSummary | null>(null)
const initialLoading = ref(true)
const retrying = ref(false)
const errorMessage = ref('')
let hasRequested = false
let requestSequence = 0
let requestController: AbortController | undefined

// ─── Overview hero cards (top section) ───────────────────────────────────

interface HeroCard {
  label: string
  value: string
  sub: string
  accent: string
}

const heroCards = computed<HeroCard[]>(() => {
  if (auth.isAdmin && adminSummary.value) {
    const d = adminSummary.value
    return [
      {
        label: '24h 请求',
        value: formatCompactInteger(d.requests_24h),
        sub: `共 ${formatInteger(d.total_requests)} 次`,
        accent: '#2563eb',
      },
      {
        label: '24h 用户费用',
        value: formatMoneyCompact(d.cost_24h),
        sub: `累计 ${formatMoneyCompact(d.total_cost)}`,
        accent: '#0f766e',
      },
      {
        label: '24h 成本',
        value: formatMoneyCompact(d.cost_amount_24h),
        sub: `累计 ${formatMoneyCompact(d.total_cost_amount)}`,
        accent: '#7c3aed',
      },
      {
        label: '24h 毛利',
        value: formatMoneyCompact(d.gross_profit_24h),
        sub: `累计 ${formatMoneyCompact(d.total_gross_profit)}`,
        accent: '#b45309',
      },
    ]
  }
  if (userSummary.value) {
    const d = userSummary.value
    return [
      {
        label: '账户余额',
        value: formatMoney(d.balance),
        sub: '当前可用',
        accent: '#16a34a',
      },
      {
        label: '累计消费',
        value: formatMoneyCompact(d.total_spent),
        sub: `24h ${formatMoneyCompact(d.cost_24h)}`,
        accent: '#2563eb',
      },
      {
        label: '24h 请求',
        value: formatCompactInteger(d.requests_24h),
        sub: `共 ${formatInteger(d.total_requests)} 次`,
        accent: '#0f766e',
      },
      {
        label: '24h 令牌',
        value: formatCompactInteger(d.total_tokens_24h),
        sub: `输入 ${formatCompactInteger(d.prompt_tokens_24h)} / 输出 ${formatCompactInteger(d.completion_tokens_24h)}`,
        accent: '#7c3aed',
      },
    ]
  }
  return []
})

// ─── Admin resource cards ────────────────────────────────────────────────

interface ResourceCard {
  label: string
  value: string
  note: string
  icon: string
}

const resourceCards = computed<ResourceCard[]>(() => {
  const data = adminSummary.value
  if (data === null) return []
  return [
    {
      label: '用户总数',
      value: formatInteger(data.users_total),
      note: '已创建账户',
      icon: '👤',
    },
    {
      label: '活跃接口密钥',
      value: formatInteger(data.active_api_keys),
      note: '当前可用',
      icon: '🔑',
    },
    {
      label: '启用提供商',
      value: `${formatInteger(data.providers.enabled)}/${formatInteger(data.providers.total)}`,
      note: '已启用',
      icon: '🔌',
    },
    {
      label: '启用模型',
      value: `${formatInteger(data.models.enabled)}/${formatInteger(data.models.total)}`,
      note: '已启用',
      icon: '🤖',
    },
    {
      label: '启用路由',
      value: `${formatInteger(data.routes.enabled)}/${formatInteger(data.routes.total)}`,
      note: data.routes.unavailable > 0 ? `${formatInteger(data.routes.unavailable)} 条熔断` : '正常',
      icon: '🔀',
    },
  ]
})

// ─── Usage detail metrics ───────────────────────────────────────────────

interface MetricItem {
  label: string
  value: string
  hint?: string
}

const usageMetrics = computed<MetricItem[]>(() => {
  const data = auth.isAdmin ? adminSummary.value : userSummary.value
  if (data === null) return []
  const metrics: MetricItem[] = [
    {
      label: '24 小时请求',
      value: formatInteger(data.requests_24h),
      hint: `失败 ${formatInteger(data.failed_requests_24h)}（${formatPercent(data.failed_requests_24h, data.requests_24h)}）`,
    },
    {
      label: '失败率',
      value: formatPercent(data.failed_requests_24h, data.requests_24h),
    },
    {
      label: '输入令牌',
      value: formatCompactInteger(data.prompt_tokens_24h),
    },
    {
      label: '输出令牌',
      value: formatCompactInteger(data.completion_tokens_24h),
    },
    {
      label: '缓存读取',
      value: formatCompactInteger(data.cache_read_tokens_24h),
    },
    {
      label: '缓存写入',
      value: formatCompactInteger(data.cache_write_tokens_24h),
    },
    {
      label: '平均延迟',
      value: formatDuration(data.average_latency_ms_24h),
    },
  ]
  return metrics
})

// ─── Chart ───────────────────────────────────────────────────────────────

function isZeroDecimal(value: string): boolean {
  return /^[+-]?0+(?:\.0*)?(?:[eE][+-]?\d+)?$/.test(value.trim())
}

const dailyUsageData = computed(() => {
  if (auth.isAdmin) return adminSummary.value?.daily_usage ?? []
  return userSummary.value?.daily_usage ?? []
})

const chartEmpty = computed(() => {
  const points = dailyUsageData.value
  return points.every(
    (point) => point.requests === 0 && point.failures === 0 && isZeroDecimal(point.cost),
  )
})

const chartOption = computed<DashboardChartOption>(() => {
  const points = dailyUsageData.value
  const isAdmin = auth.isAdmin

  const legendData = isAdmin
    ? ['请求数', '失败数', '用户费用', '成本']
    : ['请求数', '失败数', '费用']

  const series: DashboardChartOption['series'] = [
    {
      name: '请求数',
      type: 'bar',
      barMaxWidth: 24,
      data: points.map((point) => point.requests),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
    {
      name: '失败数',
      type: 'bar',
      barMaxWidth: 24,
      data: points.map((point) => point.failures),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
    {
      name: isAdmin ? '用户费用' : '费用',
      type: 'line',
      yAxisIndex: 1,
      symbol: 'circle',
      symbolSize: 6,
      smooth: true,
      data: points.map((point) => point.cost),
      lineStyle: { width: 2.5 },
    },
  ]

  if (isAdmin) {
    series.push({
      name: '成本',
      type: 'line',
      yAxisIndex: 1,
      symbol: 'diamond',
      symbolSize: 6,
      smooth: true,
      data: points.map((point) => point.cost_amount ?? '0'),
      lineStyle: { width: 2, type: 'dashed' },
    })
  }

  return {
    aria: {
      enabled: true,
      label: { enabled: false },
      decal: { show: true },
    },
    color: ['#2563eb', '#ef4444', '#0f766e', '#7c3aed'],
    grid: { top: 56, right: 72, bottom: 32, left: 56 },
    legend: { top: 8, textStyle: { fontSize: 12 } , data: legendData },
    tooltip: { trigger: 'axis', formatter: formatChartTooltip },
    xAxis: {
      type: 'category',
      axisTick: { alignWithLabel: true },
      axisLabel: { fontSize: 11 },
      data: points.map((point) => point.date.slice(5).replace('-', '/')),
    },
    yAxis: [
      {
        type: 'value',
        name: '请求',
        nameTextStyle: { fontSize: 11 },
        minInterval: 1,
        splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'value',
        name: '费用',
        nameTextStyle: { fontSize: 11 },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
    ],
    series,
  }
})

function escapeTooltipHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character] ?? character,
  )
}

function formatChartTooltip(params: unknown): string {
  const items: unknown[] = Array.isArray(params) ? (params as unknown[]) : [params]
  const item = items.find(
    (candidate): candidate is { dataIndex: number } =>
      typeof candidate === 'object' &&
      candidate !== null &&
      'dataIndex' in candidate &&
      typeof candidate.dataIndex === 'number',
  )
  const point = item === undefined ? undefined : dailyUsageData.value[item.dataIndex]
  if (point === undefined) return ''

  const lines = [
    `<strong>${escapeTooltipHtml(point.date)}</strong>`,
    `请求数：${formatInteger(point.requests)}`,
    `失败数：${formatInteger(point.failures)}`,
    `用户费用：${escapeTooltipHtml(formatMoney(point.cost))}`,
  ]
  if (auth.isAdmin && point.cost_amount !== undefined) {
    lines.push(`成本：${escapeTooltipHtml(formatMoney(point.cost_amount))}`)
    if (point.gross_profit !== undefined) {
      lines.push(`毛利：${escapeTooltipHtml(formatMoney(point.gross_profit))}`)
    }
  }
  return lines.join('<br />')
}

// ─── Data loading ────────────────────────────────────────────────────────

async function loadSummary(): Promise<void> {
  const firstRequest = !hasRequested
  hasRequested = true
  const sequence = ++requestSequence
  requestController?.abort()
  const controller = new AbortController()
  requestController = controller

  if (firstRequest) initialLoading.value = true
  else retrying.value = true

  try {
    if (auth.isAdmin) {
      const data = await getDashboardSummary(controller.signal)
      if (sequence !== requestSequence) return
      adminSummary.value = data
    } else {
      const data = await getUserDashboardSummary(controller.signal)
      if (sequence !== requestSequence) return
      userSummary.value = data
    }
    errorMessage.value = ''
  } catch (error: unknown) {
    if (controller.signal.aborted || sequence !== requestSequence) return
    errorMessage.value = error instanceof Error ? error.message : '概览数据加载失败，请稍后重试'
  } finally {
    if (sequence === requestSequence) {
      initialLoading.value = false
      retrying.value = false
    }
  }
}

const hasData = computed(() => (auth.isAdmin ? adminSummary.value !== null : userSummary.value !== null))

onMounted(() => {
  void loadSummary()
})

onBeforeUnmount(() => {
  requestSequence += 1
  requestController?.abort()
})
</script>

<template>
  <div class="dashboard">
    <PageHeader
      title="控制台概览"
      :description="auth.isAdmin ? '查看网关运营数据、计费概览与请求趋势' : '查看账户余额、消费与使用情况'"
    />

    <!-- Loading skeleton -->
    <section v-if="initialLoading" data-test="dashboard-skeleton" aria-label="正在加载概览">
      <div class="hero-grid">
        <div v-for="index in 4" :key="index" class="hero-skeleton page-card">
          <ElSkeleton animated>
            <template #template>
              <ElSkeletonItem variant="text" style="width: 50%" />
              <ElSkeletonItem variant="h1" style="width: 65%; margin-top: 0.75rem" />
              <ElSkeletonItem variant="text" style="width: 40%; margin-top: 0.5rem" />
            </template>
          </ElSkeleton>
        </div>
      </div>
    </section>

    <!-- Error state -->
    <ElResult
      v-else-if="!hasData && errorMessage"
      data-test="dashboard-error"
      icon="error"
      title="概览数据加载失败"
      :sub-title="errorMessage"
    >
      <template #extra>
        <ElButton data-test="dashboard-retry" type="primary" :loading="retrying" @click="loadSummary">重新加载</ElButton>
      </template>
    </ElResult>

    <!-- Main content -->
    <template v-else-if="hasData">
      <!-- Hero metrics -->
      <section class="hero-grid" aria-label="核心指标">
        <div
          v-for="card in heroCards"
          :key="card.label"
          class="hero-card page-card"
        >
          <div class="hero-card__accent" :style="{ background: card.accent }" />
          <p class="hero-card__label">{{ card.label }}</p>
          <p class="hero-card__value">{{ card.value }}</p>
          <p class="hero-card__sub">{{ card.sub }}</p>
        </div>
      </section>

      <!-- Admin: billing breakdown -->
      <template v-if="auth.isAdmin && adminSummary">
        <section class="dashboard-section" aria-labelledby="billing-heading">
          <div class="section-header">
            <div>
              <p class="section-eyebrow">计费概览</p>
              <h2 id="billing-heading">成本与收入</h2>
            </div>
          </div>
          <div class="billing-grid">
            <div class="billing-card page-card">
              <div class="billing-card__header">
                <span class="billing-card__dot" style="background: #0f766e" />
                <span>用户费用</span>
              </div>
              <p class="billing-card__amount">{{ formatMoney(adminSummary.cost_24h) }}</p>
              <p class="billing-card__hint">24 小时内向用户收取</p>
              <div class="billing-card__footer">
                累计 <strong>{{ formatMoney(adminSummary.total_cost) }}</strong>
              </div>
            </div>
            <div class="billing-card page-card">
              <div class="billing-card__header">
                <span class="billing-card__dot" style="background: #7c3aed" />
                <span>成本费用</span>
              </div>
              <p class="billing-card__amount">{{ formatMoney(adminSummary.cost_amount_24h) }}</p>
              <p class="billing-card__hint">24 小时上游供应商成本</p>
              <div class="billing-card__footer">
                累计 <strong>{{ formatMoney(adminSummary.total_cost_amount) }}</strong>
              </div>
            </div>
            <div class="billing-card page-card">
              <div class="billing-card__header">
                <span class="billing-card__dot" style="background: #b45309" />
                <span>毛利润</span>
              </div>
              <p class="billing-card__amount">{{ formatMoney(adminSummary.gross_profit_24h) }}</p>
              <p class="billing-card__hint">
                毛利率
                {{
                  parseFloat(adminSummary.cost_24h) > 0
                    ? (
                        (parseFloat(adminSummary.gross_profit_24h) /
                          parseFloat(adminSummary.cost_24h)) *
                        100
                      ).toFixed(1)
                    : '0.0'
                }}%
              </p>
              <div class="billing-card__footer">
                累计 <strong>{{ formatMoney(adminSummary.total_gross_profit) }}</strong>
              </div>
            </div>
          </div>
        </section>

        <!-- Resource status -->
        <section class="dashboard-section" aria-labelledby="resource-heading">
          <div class="section-header">
            <div>
              <p class="section-eyebrow">资源状态</p>
              <h2 id="resource-heading">网关资源</h2>
            </div>
          </div>
          <div class="resource-grid">
            <div
              v-for="card in resourceCards"
              :key="card.label"
              class="resource-card page-card"
            >
              <span class="resource-card__icon">{{ card.icon }}</span>
              <div class="resource-card__body">
                <p class="resource-card__value">{{ card.value }}</p>
                <p class="resource-card__label">{{ card.label }}</p>
                <p class="resource-card__note">{{ card.note }}</p>
              </div>
            </div>
          </div>
        </section>
      </template>

      <!-- Usage details -->
      <section class="dashboard-section" aria-labelledby="usage-heading">
        <div class="section-header">
          <div>
            <p class="section-eyebrow">近 24 小时</p>
            <h2 id="usage-heading">使用详情</h2>
          </div>
        </div>
        <div class="metrics-grid">
          <div v-for="metric in usageMetrics" :key="metric.label" class="metric-item">
            <p class="metric-item__label">{{ metric.label }}</p>
            <p class="metric-item__value">{{ metric.value }}</p>
            <p v-if="metric.hint" class="metric-item__hint">{{ metric.hint }}</p>
          </div>
        </div>
      </section>

      <!-- Trend chart -->
      <section class="dashboard-section" aria-labelledby="chart-heading">
        <div class="section-header">
          <div>
            <p class="section-eyebrow">近 7 天</p>
            <h2 id="chart-heading">请求与费用趋势</h2>
          </div>
        </div>
        <div class="chart-card page-card">
          <div v-if="chartEmpty" class="chart-empty" data-test="chart-empty">
            <span class="chart-empty__icon" aria-hidden="true">○</span>
            <p>近 7 天暂无请求数据</p>
            <small>产生网关流量后，这里会展示每日趋势。</small>
          </div>
          <VChart
            v-else
            class="usage-chart"
            :option="chartOption"
            :autoresize="true"
            aria-hidden="true"
          />
        </div>
        <table class="visually-hidden" data-test="daily-usage-table">
          <caption>近 7 天每日请求、失败与费用明细</caption>
          <thead>
            <tr>
              <th scope="col">日期</th>
              <th scope="col">请求数</th>
              <th scope="col">失败数</th>
              <th scope="col">费用</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in dailyUsageData" :key="point.date">
              <td>{{ point.date }}</td>
              <td>{{ formatInteger(point.requests) }}</td>
              <td>{{ formatInteger(point.failures) }}</td>
              <td>{{ formatMoney(point.cost) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Admin: Top models -->
      <section
        v-if="auth.isAdmin && adminSummary && adminSummary.top_models.length > 0"
        class="dashboard-section"
        aria-labelledby="models-heading"
      >
        <div class="section-header">
          <div>
            <p class="section-eyebrow">近 7 天</p>
            <h2 id="models-heading">热门模型</h2>
          </div>
        </div>
        <div class="page-card models-table-card">
          <ElTable :data="adminSummary.top_models" stripe style="width: 100%">
            <ElTableColumn prop="display_name" label="模型" min-width="160">
              <template #default="{ row }">
                <span class="model-name">{{ row.display_name }}</span>
                <br />
                <span class="model-canonical">{{ row.model_name }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="请求数" width="110" align="right">
              <template #default="{ row }">{{ formatInteger(row.requests) }}</template>
            </ElTableColumn>
            <ElTableColumn label="输入令牌" width="120" align="right">
              <template #default="{ row }">{{ formatCompactInteger(row.prompt_tokens) }}</template>
            </ElTableColumn>
            <ElTableColumn label="输出令牌" width="120" align="right">
              <template #default="{ row }">{{
                formatCompactInteger(row.completion_tokens)
              }}</template>
            </ElTableColumn>
            <ElTableColumn label="用户费用" width="130" align="right">
              <template #default="{ row }">{{ formatMoney(row.cost) }}</template>
            </ElTableColumn>
            <ElTableColumn label="成本" width="130" align="right">
              <template #default="{ row }">{{ formatMoney(row.cost_amount) }}</template>
            </ElTableColumn>
          </ElTable>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ─── Hero cards ─────────────────────────────────────────────────────── */

.hero-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.hero-card {
  position: relative;
  padding: 1.25rem 1.25rem 1rem;
  overflow: hidden;
  border-radius: 14px;
}

.hero-card__accent {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  border-radius: 14px 14px 0 0;
  opacity: 0.85;
}

.hero-card__label {
  margin: 0;
  color: var(--gateway-muted);
  font-size: 0.8rem;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.hero-card__value {
  margin: 0.35rem 0 0;
  font-size: 1.65rem;
  font-weight: 750;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--gateway-text);
}

.hero-card__sub {
  margin: 0.5rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.78rem;
}

.hero-skeleton {
  padding: 1.25rem;
  border-radius: 14px;
}

/* ─── Sections ──────────────────────────────────────────────────────── */

.dashboard-section {
  margin-top: 1.75rem;
}

.section-header {
  margin-bottom: 0.85rem;
}

.section-eyebrow {
  margin: 0 0 0.2rem;
  color: var(--gateway-brand);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.section-header h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 650;
}

/* ─── Billing cards ─────────────────────────────────────────────────── */

.billing-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.billing-card {
  padding: 1.25rem;
  border-radius: 14px;
}

.billing-card__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.82rem;
  color: var(--gateway-muted);
  font-weight: 500;
}

.billing-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.billing-card__amount {
  margin: 0.5rem 0 0;
  font-size: 1.5rem;
  font-weight: 750;
  letter-spacing: -0.02em;
  color: var(--gateway-text);
}

.billing-card__hint {
  margin: 0.3rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.78rem;
}

.billing-card__footer {
  margin-top: 0.85rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--gateway-border);
  color: var(--gateway-muted);
  font-size: 0.8rem;
}

.billing-card__footer strong {
  color: var(--gateway-text);
  font-weight: 600;
}

/* ─── Resource cards ────────────────────────────────────────────────── */

.resource-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
}

.resource-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem 1.1rem;
  border-radius: 12px;
}

.resource-card__icon {
  font-size: 1.35rem;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.resource-card__body {
  min-width: 0;
}

.resource-card__value {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
  line-height: 1.3;
}

.resource-card__label {
  margin: 0.15rem 0 0;
  font-size: 0.8rem;
  color: var(--gateway-muted);
}

.resource-card__note {
  margin: 0.2rem 0 0;
  font-size: 0.72rem;
  color: #5a6577;
}

/* ─── Metrics grid ─────────────────────────────────────────────────── */

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.75rem;
}

.metric-item {
  padding: 1rem;
  background: var(--gateway-panel);
  border: 1px solid var(--gateway-border);
  border-radius: 10px;
}

.metric-item__label {
  margin: 0;
  font-size: 0.75rem;
  color: var(--gateway-muted);
  font-weight: 500;
}

.metric-item__value {
  margin: 0.3rem 0 0;
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.metric-item__hint {
  margin: 0.25rem 0 0;
  font-size: 0.72rem;
  color: var(--gateway-muted);
}

/* ─── Chart ────────────────────────────────────────────────────────── */

.chart-card {
  padding: 1.25rem;
  border-radius: 14px;
}

.usage-chart {
  width: 100%;
  height: 22rem;
}

.chart-empty {
  display: grid;
  min-height: 16rem;
  place-items: center;
  align-content: center;
  color: var(--gateway-muted);
  text-align: center;
}

.chart-empty__icon {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  margin: 0 auto 0.6rem;
  color: #8aa4c8;
  font-size: 2rem;
  background: #edf4ff;
  border-radius: 999px;
}

.chart-empty p {
  margin: 0;
  color: var(--gateway-text);
  font-weight: 600;
}

.chart-empty small {
  margin-top: 0.35rem;
  display: block;
}

/* ─── Models table ─────────────────────────────────────────────────── */

.models-table-card {
  border-radius: 14px;
  overflow: hidden;
}

.model-name {
  font-weight: 600;
  font-size: 0.88rem;
}

.model-canonical {
  color: var(--gateway-muted);
  font-size: 0.75rem;
}

/* ─── Screen-reader only ───────────────────────────────────────────── */

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  white-space: nowrap;
  border: 0;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
}

/* ─── Responsive ───────────────────────────────────────────────────── */

@media (max-width: 1200px) {
  .hero-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metrics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .resource-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .hero-grid {
    grid-template-columns: 1fr 1fr;
  }

  .billing-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .resource-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .usage-chart {
    height: 18rem;
  }
}

@media (max-width: 480px) {
  .hero-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: 1fr 1fr;
  }

  .resource-grid {
    grid-template-columns: 1fr;
  }

  .chart-card {
    padding: 0.75rem;
  }
}
</style>
