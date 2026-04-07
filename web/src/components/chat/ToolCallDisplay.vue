<template>
  <div class="tool-calls">
    <div
      v-for="toolCall in props.toolCalls"
      :key="toolCall.id"
      class="tool-call-item"
      :class="getStatusClass(toolCall)"
    >
      <div class="tool-header" @click="toggleExpand(toolCall.id)">
        <div class="tool-icon">
          <el-icon v-if="toolCall.status === 'running'"><Loading /></el-icon>
          <el-icon v-else-if="toolCall.status === 'success'"><Check /></el-icon>
          <el-icon v-else-if="toolCall.status === 'error'"><Close /></el-icon>
          <el-icon v-else><Tools /></el-icon>
        </div>
        <div class="tool-info">
          <span class="tool-name">{{ getToolDisplayName(toolCall.toolName) }}</span>
          <span class="tool-status">{{ getStatusText(toolCall.status) }}</span>
        </div>
        <el-icon class="expand-icon">
          <ArrowDown v-if="!expandedIds.has(toolCall.id)" />
          <ArrowUp v-else />
        </el-icon>
      </div>
      <div v-show="expandedIds.has(toolCall.id)" class="tool-detail">
        <div class="detail-section">
          <div class="detail-label">参数</div>
          <div class="detail-content">
            <component :is="renderArguments(toolCall)" />
          </div>
        </div>
        <div v-if="toolCall.result !== undefined" class="detail-section">
          <div class="detail-label">结果</div>
          <div class="detail-content">
            <component :is="renderResult(toolCall)" />
          </div>
        </div>
        <div v-if="toolCall.error" class="detail-section error">
          <div class="detail-label">错误</div>
          <pre class="detail-code">{{ toolCall.error }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, h } from 'vue'
import { Tools, Check, Close, Loading, ArrowDown, ArrowUp, Clock, Document } from '@element-plus/icons-vue'
import type { ToolCallResult } from '@/types/tool'

const props = defineProps<{
  toolCalls: ToolCallResult[]
}>()

const expandedIds = ref(new Set<string>())

// Removed auto-expand all tool calls

const toggleExpand = (id: string) => {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

const getStatusClass = (toolCall: ToolCallResult) => {
  return `status-${toolCall.status}`
}

const getStatusText = (status: ToolCallResult['status']) => {
  switch (status) {
    case 'pending': return '等待执行'
    case 'running': return '执行中...'
    case 'success': return '执行成功'
    case 'error': return '执行失败'
  }
}

const getToolDisplayName = (toolName: string) => {
  const nameMap: Record<string, string> = {
    'get_current_time': '获取时间',
    'execute_javascript': '执行代码',
    'web_search': '网络搜索',
    'draw_chart': '绘制图表',
    'save_note': '保存笔记'
  }
  return nameMap[toolName] || toolName
}

// 渲染参数
const renderArguments = (toolCall: ToolCallResult) => {
  const toolName = toolCall.toolName || 'unknown'
  const args = toolCall.arguments || {}

  switch (toolName) {
    case 'get_current_time':
      return h('div', { class: 'tool-args-simple' }, [
        h('span', { class: 'arg-label' }, '时区：'),
        h('span', { class: 'arg-value' }, String(args.timezone || '本地时区'))
      ])
    case 'execute_javascript':
      return h('pre', { class: 'tool-args-code' }, String(args.code || ''))
    case 'web_search':
      return h('div', { class: 'tool-args-simple' }, [
        h('span', { class: 'arg-label' }, '搜索：'),
        h('span', { class: 'arg-value' }, String(args.query || ''))
      ])
    case 'draw_chart':
      return h('div', { class: 'tool-args-chart' }, [
        h('div', { class: 'chart-arg' }, `类型：${args.type || '未知'}`),
        h('div', { class: 'chart-arg' }, `标题：${args.title || '无'}`),
        h('div', { class: 'chart-arg' }, `数据：${Array.isArray(args.labels) ? (args.labels as string[]).join(', ') : '未知'}`)
      ])
    case 'save_note':
      return h('div', { class: 'tool-args-note' }, [
        h('div', { class: 'note-title' }, String(args.title || '无标题')),
        h('div', { class: 'note-preview' }, String(args.content || '').slice(0, 100) + (String(args.content || '').length > 100 ? '...' : ''))
      ])
    default:
      // For unknown tools, show JSON format
      if (Object.keys(args).length === 0) {
        return h('div', { class: 'tool-args-simple' }, '无参数')
      }
      return h('pre', { class: 'detail-code' }, formatJson(args))
  }
}

// 渲染结果
const renderResult = (toolCall: ToolCallResult) => {
  const toolName = toolCall.toolName || 'unknown'
  const result = toolCall.result

  // If no result available (loaded from server without result data)
  if (result === undefined || result === null) {
    return h('div', { class: 'tool-result-empty' }, '执行完成')
  }

  switch (toolName) {
    case 'get_current_time': {
      const timeData = result as { iso?: string; formatted?: string; timezone?: string; timestamp?: number }
      return h('div', { class: 'tool-result-time' }, [
        h('el-icon', { class: 'time-icon' }, [h(Clock)]),
        h('div', { class: 'time-content' }, [
          h('div', { class: 'time-value' }, timeData.formatted || '无法获取时间'),
          h('div', { class: 'time-extra' }, `${timeData.timezone || ''} | 时间戳：${timeData.timestamp || ''}`)
        ])
      ])
    }
    case 'execute_javascript':
      return h('div', { class: 'tool-result-code' }, [
        h('div', { class: 'result-label' }, '执行结果：'),
        h('pre', {}, typeof result === 'object' ? formatJson(result) : String(result))
      ])
    case 'web_search':
      return renderWebSearchResult(result)
    case 'draw_chart': {
      const chartData = result as { type?: string; title?: string; data?: unknown }
      return h('div', { class: 'tool-result-chart' }, [
        h('div', { class: 'chart-success' }, `图表已生成：${chartData.title || chartData.type || '图表'}`)
      ])
    }
    case 'save_note': {
      const noteResult = result as { success?: boolean; message?: string; noteId?: number }
      return h('div', { class: 'tool-result-note' }, [
        h('el-icon', { class: 'note-icon' }, [h(Document)]),
        h('span', {}, noteResult.message || '笔记已保存')
      ])
    }
    default:
      return h('pre', { class: 'detail-code' }, formatJson(result))
  }
}

// 渲染网络搜索结果
const renderWebSearchResult = (result: unknown) => {
  if (!result) {
    return h('div', { class: 'tool-result-empty' }, '无结果')
  }
  const resultData = result as { query?: string; results?: Array<{ title?: string; snippet?: string; url?: string }> }
  const results = resultData?.results || []

  if (results.length === 0) {
    return h('div', { class: 'tool-result-empty' }, resultData?.query ? `未找到关于"${resultData.query}"的结果` : '未找到相关结果')
  }

  return h('div', { class: 'web-search-results' }, [
    h('div', { class: 'search-query' }, [`搜索："${resultData.query || ''}"`]),
    h('div', { class: 'result-count' }, [`共 ${results.length} 条结果`]),
    ...results.map((item, idx) => h('div', { key: idx, class: 'search-result-item' }, [
      h('div', { class: 'result-title' }, [
        item.url ? h('a', { href: item.url, target: '_blank', class: 'result-link' }, item.title || '无标题') : h('span', {}, item.title || '无标题')
      ]),
      item.snippet ? h('div', { class: 'result-snippet' }, item.snippet) : null,
      item.url ? h('a', { href: item.url, target: '_blank', class: 'result-url' }, item.url) : null
    ]))
  ])
}

const formatJson = (obj: unknown) => {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}
</script>

<style scoped>
.tool-calls {
  margin: 8px 0 12px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-call-item {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  font-size: 13px;
}

.tool-call-item.status-pending {
  border-color: #d1d5db;
  background: #f9fafb;
}

.tool-call-item.status-running {
  border-color: #fcd34d;
  background: #fffbeb;
}

.tool-call-item.status-success {
  border-color: #86efac;
  background: #f0fdf4;
}

.tool-call-item.status-error {
  border-color: #fca5a5;
  background: #fef2f2;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
}

.tool-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-pending .tool-icon { background: #e5e7eb; color: #6b7280; }
.status-running .tool-icon { background: #fcd34d; color: #92400e; }
.status-success .tool-icon { background: #86efac; color: #166534; }
.status-error .tool-icon { background: #fca5a5; color: #991b1b; }

.tool-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-name {
  font-weight: 500;
  color: #374151;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.tool-status {
  font-size: 12px;
  color: #6b7280;
}

.expand-icon {
  color: #9ca3af;
}

.tool-detail {
  padding: 12px;
  border-top: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.5);
}

.detail-section {
  margin-bottom: 8px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section.error .detail-label {
  color: #dc2626;
}

.detail-section.error .detail-code {
  color: #991b1b;
}

.detail-label {
  font-size: 11px;
  font-weight: 500;
  color: #6b7280;
  margin-bottom: 4px;
  text-transform: uppercase;
}

.detail-content {
  padding: 8px 0;
}

.detail-code {
  margin: 0;
  padding: 8px;
  background: #f8fafc;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  color: #374151;
}

/* 参数样式 */
.tool-args-simple {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.arg-label {
  color: #6b7280;
  font-weight: 500;
}

.arg-value {
  color: #374151;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.tool-args-code {
  margin: 0;
  padding: 8px;
  background: #1e293b;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  color: #e2e8f0;
}

.tool-args-chart {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.chart-arg {
  color: #374151;
}

.tool-args-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.note-title {
  font-weight: 500;
  color: #374151;
}

.note-preview {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.4;
}

/* 结果样式 */
.tool-result-time {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-radius: 8px;
}

.time-icon {
  font-size: 20px;
  color: #0284c7;
}

.time-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.time-value {
  font-size: 14px;
  font-weight: 600;
  color: #0c4a6e;
}

.time-extra {
  font-size: 11px;
  color: #6b7280;
}

.tool-result-code {
  width: 100%;
}

.result-label {
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 4px;
  text-transform: uppercase;
}

.tool-result-code pre {
  margin: 0;
  padding: 8px;
  background: #1e293b;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  color: #e2e8f0;
}

/* 网络搜索结果样式 */
.web-search-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.search-query {
  font-size: 12px;
  color: #6b7280;
  font-style: italic;
}

.result-count {
  font-size: 11px;
  color: #9ca3af;
}

.search-result-item {
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 6px;
  border-left: 3px solid #3b82f6;
}

.result-title {
  font-weight: 500;
  color: #1e40af;
  margin-bottom: 4px;
}

.result-link {
  color: #1e40af;
  text-decoration: none;
}

.result-link:hover {
  text-decoration: underline;
}

.result-snippet {
  font-size: 12px;
  color: #4b5563;
  line-height: 1.4;
  margin-bottom: 4px;
}

.result-url {
  font-size: 11px;
  color: #9ca3af;
  text-decoration: none;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.result-url:hover {
  color: #3b82f6;
}

.tool-result-chart {
  padding: 16px;
  text-align: center;
  background: #f0fdf4;
  border-radius: 6px;
}

.chart-success {
  color: #166534;
  font-weight: 500;
}

.tool-result-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fef3c7;
  border-radius: 6px;
}

.note-icon {
  color: #92400e;
  font-size: 18px;
}

.tool-result-empty {
  padding: 16px;
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
}
</style>