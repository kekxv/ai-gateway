<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, type Component } from 'vue'
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
  ElAlert,
  ElButton,
  ElCard,
  ElDatePicker,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElOption,
  ElPagination,
  ElResult,
  ElSelect,
  ElSkeleton,
  ElSkeletonItem,
  ElTable,
  ElTableColumn,
} from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-card.css'
import 'element-plus/theme-chalk/el-date-picker.css'
import 'element-plus/theme-chalk/el-date-picker-panel.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-pagination.css'
import 'element-plus/theme-chalk/el-result.css'
import 'element-plus/theme-chalk/el-select.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/el-tag.css'
import 'element-plus/theme-chalk/el-time-picker.css'
import VChart from 'vue-echarts'

import {
  getAdminBillingStatistics,
  getUserBillingStatistics,
} from '@/api/billingStatistics'
import { listApiKeys, listOwnApiKeys } from '@/api/apiKeys'
import { listAvailableModels, listModels } from '@/api/models'
import { listProviders } from '@/api/providers'
import type {
  AdminBillingStatisticsResponse,
  AdminBillingStatisticsDimensionStat,
  BillingStatisticsDimensionStat,
  ModelResponse,
  ProviderResponse,
  ApiKeyResponse,
  UserBillingStatisticsResponse,
} from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
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

type ChartOption = ComposeOption<
  | AriaComponentOption
  | BarSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | LineSeriesOption
  | TooltipComponentOption
>
type Dimension = 'provider' | 'model' | 'apiKey'
type DimensionStat = BillingStatisticsDimensionStat | AdminBillingStatisticsDimensionStat
const FilterSelect = ElSelect as unknown as Component
const FilterOption = ElOption as unknown as Component

const auth = useAuthStore()
const end = new Date()
const start = new Date(end)
start.setDate(start.getDate() - 29)
const selectedRange = ref<[Date, Date]>([start, end])
const selectedProviderIds = ref<number[]>([])
const selectedModelIds = ref<number[]>([])
const selectedApiKeyIds = ref<number[]>([])
const selectedDimension = ref<Dimension>('model')
const currentPage = ref(1)
const pageSize = 50

const providers = ref<ProviderResponse[]>([])
const models = ref<ModelResponse[]>([])
const apiKeys = ref<ApiKeyResponse[]>([])
const statistics = ref<AdminBillingStatisticsResponse | UserBillingStatisticsResponse | null>(null)
const loading = ref(true)
const filterOptionsLoading = ref(true)
const errorMessage = ref('')
let statisticsController: AbortController | undefined
let catalogsController: AbortController | undefined
let statisticsGeneration = 0
let mounted = true

const isAdmin = computed(() => auth.isAdmin)
const dimensionTabs = computed<Array<{ value: Dimension; label: string }>>(() => [
  ...(isAdmin.value ? [{ value: 'provider' as const, label: '供应商' }] : []),
  { value: 'model' as const, label: '模型' },
  { value: 'apiKey' as const, label: 'API Key' },
])
const adminStatistics = computed(() => {
  const value = statistics.value
  return isAdmin.value && value !== null && 'provider_stats' in value ? value : null
})
const totals = computed(() => statistics.value?.totals ?? null)
const activeStats = computed<DimensionStat[]>(() => {
  if (statistics.value === null) return []
  if (selectedDimension.value === 'provider' && isAdmin.value) {
    return adminStatistics.value?.provider_stats ?? []
  }
  return selectedDimension.value === 'model'
    ? statistics.value.model_stats
    : statistics.value.api_key_stats
})
const pagedStats = computed(() => {
  const offset = (currentPage.value - 1) * pageSize
  return activeStats.value.slice(offset, offset + pageSize)
})

function apiKeyLabel(key: ApiKeyResponse): string {
  return isAdmin.value ? `${key.name} · #${String(key.id)}` : key.name
}

function modelLabel(model: ModelResponse): string {
  return model.display_name || model.canonical_name
}

function localRangeLabel(): string {
  return '所选时间按本地时区输入，服务端统一转换为 UTC 日进行统计。'
}

function dateRangeToIso(): { startAt: string; endAt: string } {
  const [startDate, endDate] = selectedRange.value
  return { startAt: startDate.toISOString(), endAt: endDate.toISOString() }
}

function isCurrentRequest(controller: AbortController, generation: number): boolean {
  return (
    mounted
    && !controller.signal.aborted
    && statisticsController === controller
    && statisticsGeneration === generation
  )
}

async function loadStatistics(): Promise<void> {
  statisticsController?.abort()
  const controller = new AbortController()
  statisticsController = controller
  const generation = ++statisticsGeneration
  loading.value = true
  errorMessage.value = ''
  const { startAt, endAt } = dateRangeToIso()
  try {
    const result = isAdmin.value
      ? await getAdminBillingStatistics({
        startAt,
        endAt,
        providerIds: selectedProviderIds.value,
        modelIds: selectedModelIds.value,
        apiKeyIds: selectedApiKeyIds.value,
      }, controller.signal)
      : await getUserBillingStatistics({
        startAt,
        endAt,
        modelIds: selectedModelIds.value,
        apiKeyIds: selectedApiKeyIds.value,
      }, controller.signal)
    if (!isCurrentRequest(controller, generation)) return
    statistics.value = result
    currentPage.value = 1
  } catch (error: unknown) {
    if (isCurrentRequest(controller, generation)) {
      statistics.value = null
      errorMessage.value = error instanceof Error ? error.message : '账单统计加载失败'
    }
  } finally {
    if (isCurrentRequest(controller, generation)) loading.value = false
    if (statisticsController === controller) statisticsController = undefined
  }
}

async function loadCatalogs(): Promise<void> {
  catalogsController?.abort()
  const controller = new AbortController()
  catalogsController = controller
  filterOptionsLoading.value = true
  try {
    if (isAdmin.value) {
      const [loadedProviders, loadedModels, loadedApiKeys] = await Promise.all([
        listProviders(controller.signal),
        listModels(controller.signal),
        listApiKeys(undefined, controller.signal),
      ])
      if (!mounted || controller.signal.aborted || catalogsController !== controller) return
      providers.value = loadedProviders
      models.value = loadedModels
      apiKeys.value = loadedApiKeys
    } else {
      const [loadedModels, loadedApiKeys] = await Promise.all([
        listAvailableModels(controller.signal),
        listOwnApiKeys(controller.signal),
      ])
      if (!mounted || controller.signal.aborted || catalogsController !== controller) return
      models.value = loadedModels
      apiKeys.value = loadedApiKeys
    }
  } finally {
    if (mounted && catalogsController === controller) filterOptionsLoading.value = false
    if (catalogsController === controller) catalogsController = undefined
  }
}

function applyFilters(): void {
  void loadStatistics()
}

function setQuickRange(days: number): void {
  const rangeEnd = new Date()
  const rangeStart = new Date(rangeEnd)
  rangeStart.setDate(rangeStart.getDate() - (days - 1))
  rangeStart.setHours(0, 0, 0, 0)
  selectedRange.value = [rangeStart, rangeEnd]
  void loadStatistics()
}

function changeDimension(dimension: Dimension): void {
  selectedDimension.value = dimension
  currentPage.value = 1
}

function chartForDimension(stats: DimensionStat[], title: string): ChartOption {
  const topStats = stats.slice(0, 20)
  return {
    aria: { enabled: true, decal: { show: true } },
    grid: { left: 48, right: 24, top: 42, bottom: 70 },
    legend: { top: 4 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: topStats.map((stat) => stat.name), axisLabel: { rotate: 30 } },
    yAxis: [{ type: 'value', name: '请求' }, { type: 'value', name: '费用' }],
    series: [
      { name: '请求', type: 'bar', data: topStats.map((stat) => stat.requests) },
      { name: '用户费用', type: 'line', yAxisIndex: 1, data: topStats.map((stat) => Number(stat.user_cost)) },
    ],
    title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
  }
}

const trendChart = computed<ChartOption>(() => {
  const points = statistics.value?.daily_usage ?? []
  const series: Array<BarSeriesOption | LineSeriesOption> = [
    { name: '请求', type: 'bar', data: points.map((point) => point.requests) },
    { name: '失败', type: 'bar', data: points.map((point) => point.failed_requests) },
    { name: '用户费用', type: 'line', yAxisIndex: 1, data: points.map((point) => Number(point.user_cost)) },
  ]
  if (isAdmin.value) {
    const adminPoints = adminStatistics.value?.daily_usage ?? []
    series.push(
      { name: '内部成本', type: 'line', yAxisIndex: 1, data: adminPoints.map((point) => Number(point.cost_amount)) },
      { name: '毛利', type: 'line', yAxisIndex: 1, data: adminPoints.map((point) => Number(point.gross_profit)) },
    )
  }
  return {
    aria: { enabled: true, decal: { show: true } },
    grid: { left: 48, right: 48, top: 42, bottom: 34 },
    legend: { top: 4 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: points.map((point) => point.date) },
    yAxis: [{ type: 'value', name: '请求' }, { type: 'value', name: '费用' }],
    series,
  }
})

const providerChart = computed(() => chartForDimension(adminStatistics.value?.provider_stats ?? [], '供应商分布'))
const modelChart = computed(() => chartForDimension(statistics.value?.model_stats ?? [], '模型分布'))
const apiKeyChart = computed(() => chartForDimension(statistics.value?.api_key_stats ?? [], 'API Key 分布'))

onMounted(() => {
  void Promise.all([loadCatalogs(), loadStatistics()])
})

onBeforeUnmount(() => {
  mounted = false
  statisticsController?.abort()
  catalogsController?.abort()
})
</script>

<template>
  <main class="route-page billing-statistics">
    <PageHeader title="账单统计" description="按时间范围、供应商、模型和 API Key 分析请求与费用。" />

    <ElCard class="filters-card" shadow="never">
      <ElForm class="filters" label-position="top">
        <div class="filters__primary" data-test="billing-date-range">
          <ElFormItem label="时间范围" class="filters__range">
            <ElDatePicker
              v-model="selectedRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              :clearable="false"
            />
            <p class="timezone-note">{{ localRangeLabel() }}</p>
          </ElFormItem>
          <div class="quick-ranges" aria-label="快捷时间范围">
            <ElButton data-test="billing-quick-range-today" size="small" plain @click="setQuickRange(1)">今天</ElButton>
            <ElButton data-test="billing-quick-range-7d" size="small" plain @click="setQuickRange(7)">近 7 天</ElButton>
            <ElButton data-test="billing-quick-range-30d" size="small" plain @click="setQuickRange(30)">近 30 天</ElButton>
          </div>
        </div>
        <div class="filters__secondary" data-test="billing-secondary-filters">
          <ElFormItem v-if="isAdmin" label="供应商" data-test="provider-filter">
            <FilterSelect v-model="selectedProviderIds" multiple filterable collapse-tags placeholder="选择供应商" :loading="filterOptionsLoading" :teleported="true" popper-class="billing-filter-popper">
              <FilterOption v-for="provider in providers" :key="provider.id" :label="provider.name" :value="provider.id" />
            </FilterSelect>
          </ElFormItem>
          <ElFormItem label="模型" data-test="model-filter">
            <FilterSelect v-model="selectedModelIds" multiple filterable collapse-tags placeholder="选择模型" :loading="filterOptionsLoading" :teleported="true" popper-class="billing-filter-popper">
              <FilterOption v-for="model in models" :key="model.id" :label="modelLabel(model)" :value="model.id" />
            </FilterSelect>
          </ElFormItem>
          <ElFormItem label="API Key" data-test="api-key-filter">
            <FilterSelect v-model="selectedApiKeyIds" multiple filterable collapse-tags placeholder="选择 API Key" :loading="filterOptionsLoading" :teleported="true" popper-class="billing-filter-popper">
              <FilterOption v-for="apiKey in apiKeys" :key="apiKey.id" :label="apiKeyLabel(apiKey)" :value="apiKey.id" />
            </FilterSelect>
          </ElFormItem>
          <ElFormItem class="filters__actions">
            <ElButton type="primary" :loading="loading" @click="applyFilters">查询</ElButton>
          </ElFormItem>
        </div>
      </ElForm>
    </ElCard>

    <section v-if="loading && statistics === null" class="loading-state" data-test="billing-statistics-skeleton" aria-label="正在加载账单统计">
      <ElSkeleton animated :rows="8"><template #template><ElSkeletonItem variant="rect" style="height: 18rem" /></template></ElSkeleton>
    </section>
    <ElResult v-else-if="errorMessage" icon="error" title="账单统计加载失败" :sub-title="errorMessage">
      <template #extra><ElButton type="primary" @click="loadStatistics">重试</ElButton></template>
    </ElResult>
    <template v-else-if="totals">
      <section class="kpi-grid" aria-label="账单汇总">
        <ElCard shadow="never"><span>请求</span><strong>{{ formatInteger(totals.requests) }}</strong><small>失败率 {{ formatPercent(totals.failed_requests, totals.requests) }}</small></ElCard>
        <ElCard shadow="never"><span>Tokens</span><strong>{{ formatInteger(totals.prompt_tokens + totals.completion_tokens + totals.cache_read_tokens + totals.cache_write_tokens) }}</strong><small>输入、输出与缓存</small></ElCard>
        <ElCard shadow="never"><span>用户费用</span><strong>{{ formatMoney(totals.user_cost) }}</strong><small>所选范围</small></ElCard>
        <ElCard v-if="isAdmin && adminStatistics" data-test="internal-cost-kpi" shadow="never"><span>内部成本</span><strong>{{ formatMoney(adminStatistics.totals.cost_amount) }}</strong><small>所选范围</small></ElCard>
        <ElCard v-if="isAdmin && adminStatistics" data-test="gross-profit-kpi" shadow="never"><span>毛利</span><strong>{{ formatMoney(adminStatistics.totals.gross_profit) }}</strong><small>收入减内部成本</small></ElCard>
        <ElCard shadow="never"><span>平均延迟</span><strong>{{ formatDuration(totals.average_latency_ms) }}</strong><small>所有请求</small></ElCard>
      </section>

      <section class="details-section">
        <div class="details-section__heading">
          <div><h2>维度明细</h2><p>图表仅展示前 20 项；表格保留完整结果并按用户费用降序。</p></div>
          <div class="dimension-tabs" role="tablist" aria-label="统计维度">
            <ElButton v-for="tab in dimensionTabs" :key="tab.value" :type="selectedDimension === tab.value ? 'primary' : 'default'" size="small" @click="changeDimension(tab.value)">{{ tab.label }}</ElButton>
          </div>
        </div>
        <ElTable :data="pagedStats" stripe>
          <ElTableColumn prop="name" label="名称" min-width="180" />
          <ElTableColumn prop="requests" label="请求" min-width="100" />
          <ElTableColumn label="失败率" min-width="110"><template #default="{ row }">{{ formatPercent(row.failed_requests, row.requests) }}</template></ElTableColumn>
          <ElTableColumn label="用户费用" min-width="140"><template #default="{ row }">{{ formatMoney(row.user_cost) }}</template></ElTableColumn>
          <ElTableColumn v-if="isAdmin" label="内部成本" min-width="140"><template #default="{ row }">{{ formatMoney(row.cost_amount) }}</template></ElTableColumn>
          <ElTableColumn v-if="isAdmin" label="毛利" min-width="140"><template #default="{ row }">{{ formatMoney(row.gross_profit) }}</template></ElTableColumn>
        </ElTable>
        <ElEmpty v-if="activeStats.length === 0" description="所选条件下暂无数据" />
        <ElPagination v-if="activeStats.length > pageSize" v-model:current-page="currentPage" background layout="prev, pager, next" :page-size="pageSize" :total="activeStats.length" />
      </section>

      <section class="charts-grid">
        <ElCard shadow="never" class="chart-card chart-card--wide"><h2>趋势</h2><VChart :option="trendChart" autoresize /></ElCard>
        <ElCard v-if="isAdmin" shadow="never" class="chart-card"><h2>供应商分布</h2><VChart :option="providerChart" autoresize /></ElCard>
        <ElCard shadow="never" class="chart-card"><h2>模型分布</h2><VChart :option="modelChart" autoresize /></ElCard>
        <ElCard shadow="never" class="chart-card"><h2>API Key 分布</h2><VChart :option="apiKeyChart" autoresize /></ElCard>
      </section>
    </template>
    <ElAlert v-else title="暂无账单数据" type="info" :closable="false" />
  </main>
</template>

<style scoped>
.billing-statistics { max-width: 1500px; margin: 0 auto; }
.filters-card { margin-bottom: 1.25rem; }
.filters-card :deep(.el-card__body) { padding: 1rem 1.25rem; }
.filters { display: grid; gap: .75rem; }
.filters__primary { display: grid; grid-template-columns: minmax(22rem, 42rem) auto; justify-content: start; gap: 1rem; min-width: 0; }
.filters__secondary { display: grid; grid-template-columns: repeat(3, minmax(11rem, 1fr)) auto; gap: 0 1rem; align-items: end; min-width: 0; padding-top: .75rem; border-top: 1px solid var(--gateway-border); }
.filters :deep(.el-form-item) { min-width: 0; margin-bottom: 0; }
.filters :deep(.el-select), .filters :deep(.el-date-editor) { width: 100%; min-width: 0; }
.filters__range { min-width: 0; }
.quick-ranges { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; align-self: start; margin-top: 1.8rem; }
.filters__actions { align-self: end; }
.timezone-note { margin: .4rem 0 0; color: var(--gateway-muted); font-size: .8125rem; line-height: 1.4; }
.loading-state { margin: 1.25rem 0; }
.kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin-bottom: 1rem; }
.kpi-grid :deep(.el-card__body) { display: grid; gap: .35rem; }
.kpi-grid span, .kpi-grid small { color: var(--gateway-muted); }
.kpi-grid strong { font-size: 1.5rem; line-height: 1.2; overflow-wrap: anywhere; }
.charts-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin-top: 1rem; }
.chart-card :deep(.el-card__body) { padding: 1rem; }
.chart-card--wide { grid-column: 1 / -1; }
.chart-card h2, .details-section h2 { margin: 0; font-size: 1rem; }
.chart-card :deep(.echarts) { height: 20rem; width: 100%; }
.details-section { margin-top: 1rem; padding: 1.25rem; background: var(--gateway-panel); border: 1px solid var(--gateway-border); border-radius: .75rem; }
.details-section__heading { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; margin-bottom: 1rem; }
.details-section p { margin: .35rem 0 0; color: var(--gateway-muted); }
.dimension-tabs { display: flex; flex-wrap: wrap; gap: .5rem; }
.details-section :deep(.el-pagination) { justify-content: flex-end; margin-top: 1rem; }
@media (max-width: 1100px) { .filters__secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); } .filters__actions { justify-self: end; } }
@media (max-width: 700px) { .filters__primary, .filters__secondary, .kpi-grid, .charts-grid { grid-template-columns: 1fr; } .quick-ranges { margin-top: 0; } .filters__actions { justify-self: stretch; } .filters__actions :deep(.el-button) { width: 100%; } .chart-card--wide { grid-column: auto; } .details-section__heading { flex-direction: column; } .chart-card :deep(.echarts) { height: 17rem; } }
</style>
