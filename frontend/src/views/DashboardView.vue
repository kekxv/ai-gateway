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
import { ElAlert, ElButton, ElCard, ElResult, ElSkeleton, ElSkeletonItem } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-card.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import VChart from 'vue-echarts'

import { getDashboardSummary } from '@/api/dashboard'
import type { DashboardSummary } from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import { formatDuration, formatInteger, formatMoney, formatPercent } from '@/utils/format'

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

const summary = ref<DashboardSummary | null>(null)
const initialLoading = ref(true)
const retrying = ref(false)
const errorMessage = ref('')
let hasRequested = false
let requestSequence = 0
let requestController: AbortController | undefined

const resourceCards = computed(() => {
  const data = summary.value
  if (data === null) return []
  return [
    { label: '用户总数', value: formatInteger(data.users_total), note: '已创建账户' },
    {
      label: '活跃接口密钥',
      value: formatInteger(data.active_api_keys),
      note: '当前可用密钥',
    },
    {
      label: '启用提供商',
      value: `${formatInteger(data.providers.enabled)} / ${formatInteger(data.providers.total)}`,
      note: '上游服务连接',
    },
    {
      label: '启用模型',
      value: `${formatInteger(data.models.enabled)} / ${formatInteger(data.models.total)}`,
      note: '可路由模型',
    },
    {
      label: '启用路由',
      value: `${formatInteger(data.routes.enabled)} / ${formatInteger(data.routes.total)}`,
      note: '模型到提供商',
    },
  ]
})

const usageCards = computed(() => {
  const data = summary.value
  if (data === null) return []
  return [
    { label: '24 小时请求', value: formatInteger(data.requests_24h) },
    {
      label: '失败率',
      value: formatPercent(data.failed_requests_24h, data.requests_24h),
    },
    { label: '提示词令牌', value: formatInteger(data.prompt_tokens_24h) },
    { label: '补全令牌', value: formatInteger(data.completion_tokens_24h) },
    { label: '24 小时费用', value: formatMoney(data.cost_24h) },
    { label: '平均延迟', value: formatDuration(data.average_latency_ms_24h) },
  ]
})

function isZeroDecimal(value: string): boolean {
  return /^[+-]?0+(?:\.0*)?(?:[eE][+-]?\d+)?$/.test(value.trim())
}

const chartEmpty = computed(() => {
  const points = summary.value?.daily_usage ?? []
  return points.every(
    (point) => point.requests === 0 && point.failures === 0 && isZeroDecimal(point.cost),
  )
})

const chartOption = computed<DashboardChartOption>(() => {
  const points = summary.value?.daily_usage ?? []
  return {
    aria: {
      enabled: true,
      label: { enabled: false },
      decal: { show: true },
    },
    color: ['#2563eb', '#dc2626', '#0f766e'],
    grid: { top: 64, right: 70, bottom: 36, left: 56 },
    legend: { top: 12, data: ['请求数', '失败数', '费用'] },
    tooltip: { trigger: 'axis', formatter: formatChartTooltip },
    xAxis: {
      type: 'category',
      axisTick: { alignWithLabel: true },
      data: points.map((point) => point.date.slice(5).replace('-', '/')),
    },
    yAxis: [
      {
        type: 'value',
        name: '请求',
        minInterval: 1,
        splitLine: { lineStyle: { color: '#e8eef6' } },
      },
      {
        type: 'value',
        name: '费用（元）',
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '请求数',
        type: 'bar',
        barMaxWidth: 28,
        data: points.map((point) => point.requests),
      },
      {
        name: '失败数',
        type: 'bar',
        barMaxWidth: 28,
        data: points.map((point) => point.failures),
      },
      {
        name: '费用',
        type: 'line',
        yAxisIndex: 1,
        symbol: 'circle',
        symbolSize: 7,
        smooth: true,
        data: points.map((point) => point.cost),
      },
    ],
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
  const point = item === undefined ? undefined : summary.value?.daily_usage[item.dataIndex]
  if (point === undefined) return ''

  return [
    `<strong>${escapeTooltipHtml(point.date)}</strong>`,
    `请求数：${formatInteger(point.requests)}`,
    `失败数：${formatInteger(point.failures)}`,
    `费用：${escapeTooltipHtml(formatMoney(point.cost))}`,
  ].join('<br />')
}

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
    const data = await getDashboardSummary(controller.signal)
    if (sequence !== requestSequence) return
    summary.value = data
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

onMounted(() => {
  void loadSummary()
})

onBeforeUnmount(() => {
  requestSequence += 1
  requestController?.abort()
})
</script>

<template>
  <PageHeader title="控制台概览" description="查看网关资源状态与近期请求趋势。" />

  <section v-if="initialLoading" data-test="dashboard-skeleton" aria-label="正在加载概览">
    <div class="resource-grid" aria-hidden="true">
      <ElCard v-for="index in 5" :key="index" shadow="never">
        <ElSkeleton animated>
          <template #template>
            <ElSkeletonItem variant="text" style="width: 45%" />
            <ElSkeletonItem variant="h1" style="width: 72%; margin-top: 1rem" />
            <ElSkeletonItem variant="text" style="width: 58%; margin-top: 0.75rem" />
          </template>
        </ElSkeleton>
      </ElCard>
    </div>
  </section>

  <ElResult
    v-else-if="summary === null && errorMessage"
    data-test="dashboard-error"
    icon="error"
    title="概览数据加载失败"
    :sub-title="errorMessage"
  >
    <template #extra>
      <ElButton
        data-test="dashboard-retry"
        type="primary"
        :loading="retrying"
        @click="loadSummary"
      >
        重新加载
      </ElButton>
    </template>
  </ElResult>

  <template v-else-if="summary !== null">
    <ElAlert
      v-if="summary.routes.unavailable > 0"
      class="route-alert"
      type="warning"
      :title="`${formatInteger(summary.routes.unavailable)} 条路由处于熔断状态`"
      description="请检查上游提供商健康状态与最近请求日志。"
      :closable="false"
      show-icon
    />

    <section aria-labelledby="resource-heading">
      <div class="section-heading">
        <div>
          <p class="section-heading__eyebrow">资源状态</p>
          <h2 id="resource-heading">网关资源</h2>
        </div>
      </div>
      <div class="resource-grid">
        <ElCard v-for="card in resourceCards" :key="card.label" shadow="never">
          <p class="resource-card__summary">{{ card.label }} {{ card.value }}</p>
          <p class="resource-card__note">{{ card.note }}</p>
        </ElCard>
      </div>
    </section>

    <section class="usage-section" aria-labelledby="usage-heading">
      <div class="section-heading">
        <div>
          <p class="section-heading__eyebrow">近 24 小时</p>
          <h2 id="usage-heading">使用情况</h2>
        </div>
      </div>
      <div class="usage-grid">
        <div v-for="card in usageCards" :key="card.label" class="usage-card page-card">
          <p>{{ card.label }} {{ card.value }}</p>
        </div>
      </div>
    </section>

    <section class="chart-card page-card" aria-labelledby="chart-heading">
      <div class="section-heading chart-heading">
        <div>
          <p class="section-heading__eyebrow">近 7 天</p>
          <h2 id="chart-heading">请求与费用趋势</h2>
        </div>
        <span class="chart-heading__note">双轴展示</span>
      </div>
      <div v-if="chartEmpty" class="chart-empty" data-test="chart-empty">
        <span class="chart-empty__mark" aria-hidden="true">○</span>
        <p>近 7 天暂无请求与费用数据</p>
        <small>产生网关流量后，这里会展示每日趋势。</small>
      </div>
      <VChart
        v-else
        class="usage-chart"
        :option="chartOption"
        :autoresize="true"
        aria-hidden="true"
      />
      <table class="visually-hidden" data-test="daily-usage-table">
        <caption>
          近 7 天每日请求、失败与费用明细
        </caption>
        <thead>
          <tr>
            <th scope="col">日期</th>
            <th scope="col">请求数</th>
            <th scope="col">失败数</th>
            <th scope="col">费用</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in summary.daily_usage" :key="point.date">
            <td>{{ point.date }}</td>
            <td>{{ formatInteger(point.requests) }}</td>
            <td>{{ formatInteger(point.failures) }}</td>
            <td>{{ formatMoney(point.cost) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </template>
</template>

<style scoped>
.route-alert {
  margin-bottom: 1.25rem;
}

.section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin: 1.4rem 0 0.8rem;
}

.section-heading__eyebrow {
  margin: 0 0 0.25rem;
  color: var(--gateway-brand);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
  font-size: 1.125rem;
}

.resource-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.9rem;
}

.resource-grid :deep(.el-card) {
  border-color: var(--gateway-border);
  border-radius: 12px;
}

.resource-card__summary {
  margin: 0;
  font-size: clamp(1rem, 1.7vw, 1.3rem);
  font-weight: 700;
  line-height: 1.35;
}

.resource-card__note {
  margin: 0.65rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.8rem;
}

.usage-section {
  margin-top: 1.5rem;
}

.usage-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
}

.usage-card {
  min-height: 5.25rem;
  padding: 1.1rem 1.2rem;
  background: linear-gradient(145deg, #fff 35%, #f7faff);
}

.usage-card p {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
  line-height: 1.5;
}

.chart-card {
  margin-top: 1.75rem;
  padding: 1.25rem;
}

.chart-heading {
  margin-top: 0;
}

.chart-heading__note {
  color: var(--gateway-muted);
  font-size: 0.8rem;
}

.usage-chart {
  width: 100%;
  height: 24rem;
}

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

.chart-empty {
  display: grid;
  min-height: 18rem;
  place-items: center;
  align-content: center;
  color: var(--gateway-muted);
  text-align: center;
}

.chart-empty__mark {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  margin-bottom: 0.7rem;
  color: #8aa4c8;
  font-size: 2rem;
  background: #edf4ff;
  border-radius: 999px;
}

.chart-empty p {
  margin: 0;
  color: var(--gateway-text);
  font-weight: 650;
}

.chart-empty small {
  margin-top: 0.45rem;
}

@media (max-width: 1180px) {
  .resource-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .resource-grid,
  .usage-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .usage-chart {
    height: 20rem;
  }
}

@media (max-width: 480px) {
  .resource-grid,
  .usage-grid {
    grid-template-columns: 1fr;
  }

  .chart-card {
    padding: 1rem 0.65rem;
  }
}
</style>
