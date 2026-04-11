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
          <el-icon v-if="toolCall.status === 'running'" class="is-loading ml-1"><Loading /></el-icon>
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
        <!-- Canvas 结果特殊显示 -->
        <div v-if="toolCall.toolName === 'web_canvas' && toolCall.result && getCanvasId(toolCall.result)" class="detail-section canvas-section">
          <CanvasDisplay
            :canvas-id="getCanvasId(toolCall.result) || ''"
            :data-url="getCanvasDataUrl(toolCall.result)"
            :width="getCanvasWidth(toolCall.result)"
            :height="getCanvasHeight(toolCall.result)"
            :operations="getOperations(toolCall)"
            :background-color="toolCall.arguments?.backgroundColor as string | undefined"
          />
        </div>
        <!-- YOLO 绘图结果特殊显示 -->
        <div v-else-if="toolCall.toolName === 'yolo_draw' && toolCall.result && getCanvasId(toolCall.result)" class="detail-section canvas-section">
          <CanvasDisplay
            :canvas-id="getCanvasId(toolCall.result) || ''"
            :data-url="getCanvasDataUrl(toolCall.result)"
            :width="getCanvasWidth(toolCall.result)"
            :height="getCanvasHeight(toolCall.result)"
          />
        </div>
        <div v-else-if="toolCall.result !== undefined" class="detail-section">
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
import { ref, h, watch } from 'vue'
import { Tools, Check, Close, Loading, ArrowDown, ArrowUp, Clock, Document, Picture } from '@element-plus/icons-vue'
import type { ToolCallResult } from '@/types/tool'
import CanvasDisplay from './CanvasDisplay.vue'
import { useCanvasStore } from '@/stores/canvas'
import * as Diff from 'diff'

const props = defineProps<{
  toolCalls: ToolCallResult[]
}>()

const canvasStore = useCanvasStore()

const expandedIds = ref(new Set<string>())

// Auto-expand specific tools (like web_canvas, yolo_draw) when they are successful or running
watch(() => props.toolCalls, (newCalls) => {
  newCalls.forEach(tc => {
    if ((tc.toolName === 'web_canvas' || tc.toolName === 'yolo_draw' || tc.status === 'running') && !expandedIds.value.has(tc.id)) {
      expandedIds.value.add(tc.id)
    }
  })
}, { deep: true, immediate: true })

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
    'get_location': '获取定位',
    'execute_javascript': '执行代码',
    'web_search': '网络搜索',
    'fetch_webpage': '获取网页',
    'web_canvas': 'Canvas 绘图',
    'yolo_draw': 'YOLO 绘图',
    'draw_chart': '绘制图表',
    'save_note': '保存笔记',
    'Edit': '编辑文件',
    'edit_file': '编辑文件'
  }
  return nameMap[toolName] || toolName
}

// 获取 Canvas ID（用于从 store 获取图片）
const getCanvasId = (result: unknown): string | null => {
  if (!result || typeof result !== 'object') return null
  const data = result as Record<string, unknown>
  // 如果结果里有 canvasId，使用它
  if (data.canvasId) return data.canvasId as string
  // 否则从 store 获取最新的 canvas
  return canvasStore.latestCanvasId
}

// 获取 Canvas dataUrl（可选，可能从 store 获取）
const getCanvasDataUrl = (result: unknown): string | undefined => {
  if (!result || typeof result !== 'object') return undefined
  const data = result as Record<string, unknown>
  return data.dataUrl as string | undefined
}

// 获取 Canvas 宽度
const getCanvasWidth = (result: unknown): number => {
  if (!result || typeof result !== 'object') return 400
  const data = result as Record<string, unknown>
  return (data.width as number) || 400
}

// 获取 Canvas 高度
const getCanvasHeight = (result: unknown): number => {
  if (!result || typeof result !== 'object') return 300
  const data = result as Record<string, unknown>
  return (data.height as number) || 300
}

// 获取 operations 数组
const getOperations = (toolCall: ToolCallResult): Array<Record<string, unknown>> | string | undefined => {
  const ops = toolCall.arguments?.operations
  if (!ops) return undefined
  // 如果已经是数组，直接返回
  if (Array.isArray(ops)) {
    return ops
  }
  // 如果是字符串，尝试解析或直接返回
  return ops as string
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
    case 'get_location':
      return h('div', { class: 'tool-args-simple' }, [
        h('span', { class: 'arg-label' }, '高精度：'),
        h('span', { class: 'arg-value' }, args.enableHighAccuracy ? '是' : '否')
      ])
    case 'execute_javascript':
      return h('pre', { class: 'tool-args-code' }, String(args.code || ''))
    case 'Edit':
    case 'edit_file':
      return renderEditArgs(args)
    case 'web_search':
      return h('div', { class: 'tool-args-simple' }, [
        h('span', { class: 'arg-label' }, '搜索：'),
        h('span', { class: 'arg-value' }, String(args.query || ''))
      ])
    case 'fetch_webpage':
      return h('div', { class: 'tool-args-webpage' }, [
        h('div', { class: 'webpage-url' }, [
          h('span', { class: 'arg-label' }, 'URL：'),
          h('span', { class: 'arg-value' }, String(args.url || ''))
        ]),
        args.format ? h('div', { class: 'webpage-format' }, [
          h('span', { class: 'arg-label' }, '格式：'),
          h('span', { class: 'arg-value' }, String(args.format))
        ]) : null
      ])
    case 'web_canvas':
      return renderCanvasArgs(args)
    case 'yolo_draw':
      return renderYoloArgs(args)
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

// 渲染 Canvas 参数
const renderCanvasArgs = (args: Record<string, unknown>) => {
  const width = args.width || 400
  const height = args.height || 300
  const backgroundColor = args.backgroundColor
  let operations: Array<Record<string, unknown>> = []

  // 确保 operations 是数组
  if (Array.isArray(args.operations)) {
    operations = args.operations as Array<Record<string, unknown>>
  } else if (typeof args.operations === 'string') {
    try {
      const parsed = JSON.parse(args.operations)
      if (Array.isArray(parsed)) {
        operations = parsed
      }
    } catch {
      // 解析失败，保持空数组
    }
  }

  // 获取操作类型 - 支持 type 和 operation 字段
  const getOpType = (op: Record<string, unknown>): string => {
    return String(op.type || op.operation || 'unknown')
  }

  // 格式化单个操作的描述
  const formatOpDesc = (op: Record<string, unknown>): string => {
    const type = getOpType(op)
    switch (type) {
      case 'rect':
        return `矩形 (${op.x || 0}, ${op.y || 0}) ${op.width || 0}x${op.height || 0}`
      case 'circle':
        return `圆形 (${op.x || 0}, ${op.y || 0}) r=${op.radius || op.r || 0}`
      case 'ellipse':
        return `椭圆 (${op.x || 0}, ${op.y || 0})`
      case 'line':
        return `线条 (${op.x1 || 0},${op.y1 || 0}) → (${op.x2 || 0},${op.y2 || 0})`
      case 'text':
        return `文本: "${String(op.text || '').slice(0, 20)}"`
      case 'arc':
        return `弧形`
      case 'clear':
        return '清空画布'
      case 'setStyle':
        return '设置样式'
      default:
        return type
    }
  }

  const children: Array<ReturnType<typeof h>> = [
    h('div', { class: 'canvas-size' }, `画布尺寸：${width} x ${height}`),
    h('div', { class: 'canvas-ops' }, [
      h('span', { class: 'arg-label' }, '操作：'),
      h('span', { class: 'arg-value' }, `${operations.length} 个绘制操作`)
    ])
  ]

  // Add background color if specified
  if (backgroundColor) {
    children.push(h('div', { class: 'canvas-bg' }, `背景：${backgroundColor}`))
  }

  // 显示详细操作列表
  if (operations.length > 0) {
    children.push(h('div', { class: 'canvas-op-details' },
      operations.map((op, idx) =>
        h('div', { class: 'canvas-op-item', key: idx }, [
          h('span', { class: 'canvas-op-type' }, getOpType(op)),
          h('span', { class: 'canvas-op-desc' }, formatOpDesc(op))
        ])
      )
    ))
  }

  return h('div', { class: 'tool-args-canvas' }, children)
}

// 渲染 YOLO 绘图参数
const renderYoloArgs = (args: Record<string, unknown>) => {
  let boxes: Array<Record<string, unknown>> = []

  // 确保 boxes 是数组
  if (Array.isArray(args.boxes)) {
    boxes = args.boxes as Array<Record<string, unknown>>
  } else if (typeof args.boxes === 'string') {
    try {
      const parsed = JSON.parse(args.boxes)
      if (Array.isArray(parsed)) {
        boxes = parsed
      }
    } catch {
      // 解析失败，保持空数组
    }
  }

  const defaultColor = args.color || '#ff0000'
  const lineWidth = args.lineWidth || 2

  return h('div', { class: 'tool-args-yolo' }, [
    h('div', { class: 'yolo-header' }, [
      h('span', { class: 'arg-label' }, '边界框数量：'),
      h('span', { class: 'arg-value' }, String(boxes.length))
    ]),
    h('div', { class: 'yolo-options' }, [
      h('span', { class: 'arg-label' }, '默认颜色：'),
      h('span', { class: 'arg-value', style: { color: String(defaultColor) } }, String(defaultColor)),
      h('span', { class: 'arg-label ml-2' }, '线宽：'),
      h('span', { class: 'arg-value' }, String(lineWidth))
    ]),
    boxes.length > 0 ? h('div', { class: 'yolo-boxes-preview' }, [
      h('div', { class: 'yolo-boxes-header' }, '检测框列表：'),
      h('div', { class: 'yolo-boxes-list' }, [
        ...boxes.slice(0, 5).map((box, idx) =>
          h('div', { key: idx, class: 'yolo-box-item' }, [
            h('span', { class: 'box-label' }, String(box.label || `目标 ${idx + 1}`)),
            h('span', { class: 'box-coords' },
              `左上(${((box.x as number) || 0).toFixed(2)}, ${((box.y as number) || 0).toFixed(2)}) ${((box.width as number) || 0).toFixed(2)}x${((box.height as number) || 0).toFixed(2)}`
            ),
            box.confidence !== undefined ? h('span', { class: 'box-conf' },
              `${((box.confidence as number) * 100).toFixed(0)}%`
            ) : null
          ])
        ),
        boxes.length > 5 ? h('div', { class: 'yolo-more' }, `还有 ${boxes.length - 5} 个...`) : null
      ])
    ]) : null
  ])
}

// 渲染 Edit 参数
const renderEditArgs = (args: Record<string, unknown>) => {
  const filePath = String(args.file_path || args.path || '未知文件')
  const oldString = String(args.old_string || '')
  const newString = String(args.new_string || '')
  const replaceAll = args.replace_all === true

  // 计算差异
  const diff = Diff.diffLines(oldString, newString)

  return h('div', { class: 'tool-args-edit' }, [
    h('div', { class: 'edit-file-path' }, [
      h('span', { class: 'arg-label' }, '文件：'),
      h('span', { class: 'arg-value' }, filePath)
    ]),
    replaceAll ? h('div', { class: 'edit-replace-all' }, '替换全部匹配') : null,
    h('div', { class: 'edit-diff-preview' }, [
      h('div', { class: 'edit-diff-header' }, '内容差异预览：'),
      h('div', { class: 'edit-diff-content' },
        diff.map((part, idx) => {
          const lines = part.value.split('\n')
          if (lines[lines.length - 1] === '') lines.pop()

          return lines.map((line, lineIdx) =>
            h('div', {
              key: `${idx}-${lineIdx}`,
              class: ['edit-diff-line', part.added ? 'diff-added' : part.removed ? 'diff-removed' : 'diff-neutral']
            }, [
              h('span', { class: 'edit-line-sign' }, part.added ? '+' : part.removed ? '-' : ' '),
              h('span', { class: 'edit-line-text' }, line)
            ])
          )
        }).flat()
      )
    ])
  ])
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
    case 'get_location': {
      const locData = result as { latitude?: number; longitude?: number; accuracy?: number }
      return h('div', { class: 'tool-result-location' }, [
        h('div', { class: 'location-row' }, [
          h('span', { class: 'arg-label' }, '纬度：'),
          h('span', { class: 'arg-value' }, locData.latitude?.toFixed(6) || '未知')
        ]),
        h('div', { class: 'location-row' }, [
          h('span', { class: 'arg-label' }, '经度：'),
          h('span', { class: 'arg-value' }, locData.longitude?.toFixed(6) || '未知')
        ]),
        locData.accuracy ? h('div', { class: 'location-row' }, [
          h('span', { class: 'arg-label' }, '精度：'),
          h('span', { class: 'arg-value' }, `${locData.accuracy.toFixed(0)}m`)
        ]) : null
      ])
    }
    case 'execute_javascript':
      return h('div', { class: 'tool-result-code' }, [
        h('div', { class: 'result-label' }, '执行结果：'),
        h('pre', {}, typeof result === 'object' ? formatJson(result) : String(result))
      ])
    case 'Edit':
    case 'edit_file':
      return renderEditResult(result)
    case 'web_search':
      return renderWebSearchResult(result)
    case 'fetch_webpage':
      return renderWebpageResult(result)
    case 'web_canvas': {
      // Handle string result (JSON string from logs)
      let canvasData: { width?: number; height?: number; message?: string; success?: boolean; canvasId?: string }
      if (typeof result === 'string') {
        try {
          canvasData = JSON.parse(result)
        } catch {
          canvasData = { message: result }
        }
      } else {
        canvasData = result as { width?: number; height?: number; message?: string; success?: boolean; canvasId?: string }
      }
      return h('div', { class: 'tool-result-canvas' }, [
        h('el-icon', { class: 'canvas-icon' }, [h(Picture)]),
        h('span', {}, canvasData.message || `Canvas 绘制完成 (${canvasData.width ?? '?'}x${canvasData.height ?? '?'})`)
      ])
    }
    case 'yolo_draw': {
      // Handle string result (JSON string from logs)
      let yoloData: { width?: number; height?: number; message?: string; success?: boolean; boxCount?: number; canvasId?: string }
      if (typeof result === 'string') {
        try {
          yoloData = JSON.parse(result)
        } catch {
          yoloData = { message: result }
        }
      } else {
        yoloData = result as { width?: number; height?: number; message?: string; success?: boolean; boxCount?: number; canvasId?: string }
      }
      return h('div', { class: 'tool-result-yolo' }, [
        h('el-icon', { class: 'canvas-icon' }, [h(Picture)]),
        h('span', {}, yoloData.message || `YOLO 绘制完成，共 ${yoloData.boxCount ?? '?'} 个目标 (${yoloData.width ?? '?'}x${yoloData.height ?? '?'})`)
      ])
    }
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
      // For string results, preserve line breaks
      if (typeof result === 'string') {
        return h('pre', { class: 'detail-code' }, result)
      }
      return h('pre', { class: 'detail-code' }, formatJson(result))
  }
}

// 渲染网页获取结果
const renderWebpageResult = (result: unknown) => {
  if (!result) {
    return h('div', { class: 'tool-result-empty' }, '无结果')
  }
  const data = result as { title?: string; description?: string; textContent?: string; htmlContent?: string; url?: string; encoding?: string }

  return h('div', { class: 'webpage-result' }, [
    data.title ? h('div', { class: 'webpage-title' }, [
      h('span', { class: 'arg-label' }, '标题：'),
      h('span', { class: 'arg-value' }, data.title)
    ]) : null,
    data.url ? h('div', { class: 'webpage-url-row' }, [
      h('span', { class: 'arg-label' }, 'URL：'),
      h('a', { href: data.url, target: '_blank', class: 'webpage-link' }, data.url)
    ]) : null,
    data.encoding ? h('div', { class: 'webpage-encoding' }, [
      h('span', { class: 'arg-label' }, '编码：'),
      h('span', { class: 'arg-value' }, data.encoding)
    ]) : null,
    data.textContent ? h('div', { class: 'webpage-content' }, [
      h('div', { class: 'content-label' }, '内容预览：'),
      h('div', { class: 'content-text' }, String(data.textContent).slice(0, 500) + (String(data.textContent).length > 500 ? '...' : ''))
    ]) : null
  ])
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

// 渲染 Edit 结果
const renderEditResult = (result: unknown) => {
  if (!result) {
    return h('div', { class: 'tool-result-empty' }, '无结果')
  }

  // Handle string result
  let resultData: { success?: boolean; message?: string; file_path?: string; error?: string }
  if (typeof result === 'string') {
    try {
      resultData = JSON.parse(result)
    } catch {
      resultData = { message: result, success: true }
    }
  } else {
    resultData = result as { success?: boolean; message?: string; file_path?: string; error?: string }
  }

  if (resultData.error) {
    return h('div', { class: 'tool-result-error' }, [
      h('el-icon', { class: 'error-icon' }, [h(Close)]),
      h('span', {}, resultData.error)
    ])
  }

  return h('div', { class: 'tool-result-edit' }, [
    h('el-icon', { class: 'edit-success-icon' }, [h(Check)]),
    h('span', {}, resultData.message || '文件已成功更新')
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
  background: #f9fafb;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  color: #374151;
  border: 1px solid #e5e7eb;
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
  background: #f9fafb;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  color: #374151;
  border: 1px solid #e5e7eb;
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

/* Canvas 参数样式 */
.tool-args-canvas {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.canvas-size, .canvas-bg {
  color: #374151;
}

.canvas-ops {
  display: flex;
  align-items: center;
  gap: 8px;
}

.canvas-op-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  padding: 8px;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.canvas-op-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.canvas-op-type {
  padding: 2px 6px;
  background: #e0e7ff;
  color: #3730a3;
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 11px;
}

.canvas-op-desc {
  color: #4b5563;
}

.canvas-op-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.canvas-op-tag {
  padding: 2px 8px;
  background: #e0e7ff;
  color: #3730a3;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.canvas-op-more {
  padding: 2px 8px;
  background: #f3f4f6;
  color: #6b7280;
  border-radius: 4px;
  font-size: 11px;
}

/* Canvas 结果样式 */
.tool-result-canvas {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #fdf4ff 0%, #fae8ff 100%);
  border-radius: 8px;
}

.canvas-icon {
  font-size: 20px;
  color: #a21caf;
}

.canvas-section {
  padding: 0;
  background: transparent;
}

/* YOLO 参数样式 */
.tool-args-yolo {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.yolo-header, .yolo-options {
  color: #374151;
}

.yolo-boxes-preview {
  margin-top: 8px;
  padding: 8px;
  background: #fef3c7;
  border-radius: 6px;
  border: 1px solid #fcd34d;
}

.yolo-boxes-header {
  font-size: 12px;
  color: #92400e;
  margin-bottom: 6px;
}

.yolo-boxes-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.yolo-box-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.yolo-box-item .box-label {
  padding: 2px 6px;
  background: #dc2626;
  color: #fff;
  border-radius: 4px;
  font-weight: 500;
}

.yolo-box-item .box-coords {
  color: #78350f;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.yolo-box-item .box-conf {
  padding: 2px 6px;
  background: #10b981;
  color: #fff;
  border-radius: 4px;
  font-size: 11px;
}

.yolo-more {
  font-size: 11px;
  color: #92400e;
  padding: 4px 0;
}

/* YOLO 结果样式 */
.tool-result-yolo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-radius: 8px;
}

.tool-result-yolo .canvas-icon {
  color: #d97706;
}

/* 网页获取参数样式 */
.tool-args-webpage {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.webpage-url {
  display: flex;
  align-items: center;
  gap: 8px;
}

.webpage-format {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 网页获取结果样式 */
.webpage-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.webpage-title,
.webpage-url-row,
.webpage-encoding {
  display: flex;
  align-items: center;
  gap: 8px;
}

.webpage-link {
  color: #3b82f6;
  text-decoration: none;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
}

.webpage-link:hover {
  text-decoration: underline;
}

.webpage-content {
  margin-top: 8px;
}

.content-label {
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 4px;
}

.content-text {
  padding: 8px;
  background: #f9fafb;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #374151;
  max-height: 150px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
}

/* 定位结果样式 */
.tool-result-location {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border-radius: 8px;
}

.location-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Edit 工具参数样式 */
.tool-args-edit {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-file-path {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.edit-replace-all {
  padding: 4px 8px;
  background: #fef3c7;
  color: #92400e;
  border-radius: 4px;
  font-size: 12px;
}

.edit-diff-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.edit-diff-header {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}

.edit-diff-content {
  padding: 12px;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.edit-diff-line {
  display: flex;
  align-items: flex-start;
  white-space: pre;
  padding: 1px 0;
}

.edit-line-sign {
  width: 16px;
  text-align: center;
  color: #6b7280;
  user-select: none;
}

.edit-line-text {
  flex: 1;
  padding-left: 8px;
  word-break: break-all;
}

.edit-diff-line.diff-added {
  background: #dcfce7;
}

.edit-diff-line.diff-added .edit-line-sign {
  color: #16a34a;
}

.edit-diff-line.diff-added .edit-line-text {
  color: #166534;
}

.edit-diff-line.diff-removed {
  background: #fee2e2;
}

.edit-diff-line.diff-removed .edit-line-sign {
  color: #dc2626;
}

.edit-diff-line.diff-removed .edit-line-text {
  color: #991b1b;
}

.edit-diff-line.diff-neutral {
  background: transparent;
}

.edit-diff-line.diff-neutral .edit-line-text {
  color: #374151;
}

/* Edit 工具结果样式 */
.tool-result-edit {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border-radius: 8px;
}

.edit-success-icon {
  font-size: 18px;
  color: #16a34a;
}

.tool-result-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fef2f2;
  border-radius: 8px;
  color: #991b1b;
}

.error-icon {
  font-size: 18px;
  color: #dc2626;
}
</style>