<template>
  <div class="canvas-display">
    <div class="canvas-header">
      <span class="canvas-title">Canvas 绘图结果</span>
      <div class="canvas-actions">
        <el-button size="small" @click="downloadCanvas" title="下载图片">
          <el-icon><Download /></el-icon>
        </el-button>
        <el-button size="small" @click="copyDataUrl" title="复制图片">
          <el-icon><CopyDocument /></el-icon>
        </el-button>
      </div>
    </div>
    <div class="canvas-content">
      <canvas
        ref="canvasRef"
        :width="imageWidth"
        :height="imageHeight"
        class="canvas-element"
        v-show="imageUrl"
      ></canvas>
      <div v-if="!imageUrl && isRedrawing" class="canvas-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>重新绘制中...</span>
      </div>
      <div v-if="imageUrl" class="canvas-info">
        <span>{{ imageWidth }} x {{ imageHeight }} px</span>
        <span>{{ formatSize(imageUrl.length) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, CopyDocument, Loading } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'

const props = defineProps<{
  canvasId: string
  dataUrl?: string
  width?: number
  height?: number
  operations?: Array<Record<string, unknown>> | string  // 用于重新绘制，可能是数组或 JSON 字符串
  backgroundColor?: string
}>()

const canvasStore = useCanvasStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const isRedrawing = ref(false)

// 从 props 或 store 获取图片数据
const canvasData = computed(() => {
  if (props.dataUrl) {
    return {
      dataUrl: props.dataUrl,
      width: props.width || 400,
      height: props.height || 300
    }
  }
  const data = canvasStore.getCanvas(props.canvasId)
  if (data) {
    return data
  }
  // store 中没有，返回空
  return { dataUrl: '', width: props.width || 400, height: props.height || 300 }
})

const imageUrl = computed(() => canvasData.value.dataUrl)
const imageWidth = computed(() => canvasData.value.width)
const imageHeight = computed(() => canvasData.value.height)

// 重新绘制 Canvas
const redrawCanvas = async () => {
  if (!props.operations || !props.canvasId) return

  isRedrawing.value = true

  try {
    // 确保 operations 是数组
    let ops: Array<Record<string, unknown>> = []
    if (Array.isArray(props.operations)) {
      ops = props.operations
    } else if (typeof props.operations === 'string') {
      try {
        const parsed = JSON.parse(props.operations)
        if (Array.isArray(parsed)) {
          ops = parsed
        }
      } catch {
        // 解析失败，返回空数组
      }
    }

    if (ops.length === 0) {
      isRedrawing.value = false
      return
    }

    const canvasWidth = Math.max(1, Math.min(props.width || 400, 2000))
    const canvasHeight = Math.max(1, Math.min(props.height || 300, 2000))

    const canvas = document.createElement('canvas')
    canvas.width = canvasWidth
    canvas.height = canvasHeight
    const ctx = canvas.getContext('2d')

    if (!ctx) {
      throw new Error('无法创建 Canvas 上下文')
    }

    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    const bgColor = props.backgroundColor || '#ffffff'
    if (bgColor.toLowerCase() !== 'transparent') {
      ctx.fillStyle = bgColor
      ctx.fillRect(0, 0, canvasWidth, canvasHeight)
    }

    ctx.strokeStyle = '#000000'
    ctx.fillStyle = '#000000'
    ctx.lineWidth = 1

    for (const op of ops) {
      try {
        executeCanvasOperation(ctx, op)
      } catch (err) {
        console.warn(`Canvas 操作执行失败：${op.type}`, err)
      }
    }

    const dataUrl = canvas.toDataURL('image/png')

    // 保存到 store
    canvasStore.addCanvas({
      id: props.canvasId,
      width: canvasWidth,
      height: canvasHeight,
      dataUrl,
      createdAt: Date.now()
    })

    isRedrawing.value = false
  } catch (e) {
    console.error('重新绘制失败:', e)
    isRedrawing.value = false
  }
}

// Canvas 绘图操作函数（复制自 toolExecutor.ts）
function executeCanvasOperation(ctx: CanvasRenderingContext2D, op: Record<string, unknown>) {
  const { type, ...params } = op
  if (!type) return

  switch (type) {
    case 'clear':
      ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height)
      break
    case 'fill':
      ctx.fillStyle = (params.color as string) || (params.fillStyle as string) || '#000000'
      ctx.fillRect((params.x as number) ?? 0, (params.y as number) ?? 0,
        (params.width as number) ?? ctx.canvas.width, (params.height as number) ?? ctx.canvas.height)
      break
    case 'stroke':
      ctx.strokeStyle = (params.color as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
      ctx.strokeRect((params.x as number) ?? 0, (params.y as number) ?? 0,
        (params.width as number) ?? 100, (params.height as number) ?? 100)
      break
    case 'rect': {
      const rx = (params.x as number) ?? 0
      const ry = (params.y as number) ?? 0
      const rw = (params.width as number) ?? 100
      const rh = (params.height as number) ?? 100
      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || (params.fillStyle as string) || '#000000'
        ctx.fillRect(rx, ry, rw, rh)
      }
      if (params.stroke === true) {
        ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
        ctx.lineWidth = (params.lineWidth as number) ?? 1
        ctx.strokeRect(rx, ry, rw, rh)
      }
      break
    }
    case 'circle': {
      const cx = (params.x as number) ?? 0
      const cy = (params.y as number) ?? 0
      const radius = Math.max(0, (params.radius as number) ?? 50)
      ctx.beginPath()
      ctx.arc(cx, cy, radius, 0, Math.PI * 2)
      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || (params.fillStyle as string) || '#000000'
        ctx.fill()
      }
      if (params.stroke === true || (params.stroke !== false && params.fill !== true)) {
        ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
        ctx.lineWidth = (params.lineWidth as number) ?? 1
        ctx.stroke()
      }
      break
    }
    case 'line':
      ctx.beginPath()
      ctx.moveTo((params.x1 as number) ?? 0, (params.y1 as number) ?? 0)
      ctx.lineTo((params.x2 as number) ?? 100, (params.y2 as number) ?? 100)
      ctx.strokeStyle = (params.color as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
      ctx.stroke()
      break
    case 'text':
      ctx.font = (params.font as string) || '16px Arial'
      ctx.fillStyle = (params.color as string) || (params.fillStyle as string) || '#000000'
      ctx.textAlign = (params.align as CanvasTextAlign) || 'left'
      ctx.textBaseline = (params.baseline as CanvasTextBaseline) || 'top'
      ctx.fillText(String(params.text ?? ''), (params.x as number) ?? 0, (params.y as number) ?? 0)
      break
    case 'ellipse': {
      ctx.beginPath()
      ctx.ellipse((params.x as number) ?? 0, (params.y as number) ?? 0,
        Math.max(0, (params.radiusX as number) ?? 50), Math.max(0, (params.radiusY as number) ?? 30),
        (params.rotation as number) ?? 0, (params.startAngle as number) ?? 0, (params.endAngle as number) ?? Math.PI * 2)
      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || (params.fillStyle as string) || '#000000'
        ctx.fill()
      }
      if (params.stroke === true || (params.stroke !== false && params.fill !== true)) {
        ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
        ctx.lineWidth = (params.lineWidth as number) ?? 1
        ctx.stroke()
      }
      break
    }
    case 'polygon':
    case 'polyline': {
      const points = params.points as Array<{ x: number; y: number }> | undefined
      if (!points || points.length < 2) break
      ctx.beginPath()
      ctx.moveTo(points[0].x, points[0].y)
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y)
      }
      if (type === 'polygon') {
        ctx.closePath()
        if (params.fill === true) {
          ctx.fillStyle = (params.fillColor as string) || (params.fillStyle as string) || '#000000'
          ctx.fill()
        }
      }
      ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
      ctx.stroke()
      break
    }
    case 'arc': {
      ctx.beginPath()
      ctx.arc((params.x as number) ?? 0, (params.y as number) ?? 0,
        Math.max(0, (params.radius as number) ?? 50),
        (params.startAngle as number) ?? 0, (params.endAngle as number) ?? Math.PI)
      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || '#000000'
        ctx.fill()
      }
      ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
      ctx.stroke()
      break
    }
    case 'bezier':
      ctx.beginPath()
      ctx.moveTo((params.x1 as number) ?? 0, (params.y1 as number) ?? 0)
      if (params.cp2x !== undefined && params.cp2y !== undefined) {
        ctx.bezierCurveTo((params.cp1x as number) ?? 0, (params.cp1y as number) ?? 0,
          params.cp2x as number, params.cp2y as number,
          (params.x2 as number) ?? 100, (params.y2 as number) ?? 100)
      } else {
        ctx.quadraticCurveTo((params.cpx as number) ?? 50, (params.cpy as number) ?? 100,
          (params.x2 as number) ?? 100, (params.y2 as number) ?? 50)
      }
      ctx.strokeStyle = (params.color as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
      ctx.stroke()
      break
    case 'path': {
      const pathData = params.d as string | undefined
      if (!pathData) break
      const path = new Path2D(pathData)
      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || (params.fillStyle as string) || '#000000'
        ctx.fill(path)
      }
      if (params.stroke === true || params.stroke === undefined) {
        ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
        ctx.lineWidth = (params.lineWidth as number) ?? 1
        ctx.stroke(path)
      }
      break
    }
    case 'setStyle':
      if (params.fillStyle !== undefined) ctx.fillStyle = params.fillStyle as string
      if (params.strokeStyle !== undefined) ctx.strokeStyle = params.strokeStyle as string
      if (params.lineWidth !== undefined) ctx.lineWidth = params.lineWidth as number
      if (params.lineCap !== undefined) ctx.lineCap = params.lineCap as CanvasLineCap
      if (params.lineJoin !== undefined) ctx.lineJoin = params.lineJoin as CanvasLineJoin
      if (params.font !== undefined) ctx.font = params.font as string
      if (params.globalAlpha !== undefined) ctx.globalAlpha = params.globalAlpha as number
      break
    case 'translate':
      ctx.translate((params.x as number) ?? 0, (params.y as number) ?? 0)
      break
    case 'rotate':
      ctx.rotate((params.angle as number) ?? 0)
      break
    case 'scale':
      ctx.scale((params.x as number) ?? 1, (params.y as number) ?? 1)
      break
    case 'save':
      ctx.save()
      break
    case 'restore':
      ctx.restore()
      break
    default:
      console.warn(`未知的 Canvas 操作类型：${type}`)
  }
}

const drawCanvas = () => {
  if (!canvasRef.value || !imageUrl.value) return
  const ctx = canvasRef.value.getContext('2d')
  if (!ctx) return

  const img = new Image()
  img.onload = () => {
    if (canvasRef.value) {
      ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
      ctx.drawImage(img, 0, 0)
    }
  }
  img.src = imageUrl.value
}

onMounted(() => {
  // 检查是否有有效的 operations
  let hasOps = false
  if (Array.isArray(props.operations) && props.operations.length > 0) {
    hasOps = true
  } else if (typeof props.operations === 'string' && props.operations.trim().startsWith('[')) {
    hasOps = true
  }

  // 如果没有图片数据但有 operations，尝试重新绘制
  if (!imageUrl.value && hasOps && props.canvasId) {
    redrawCanvas()
  } else {
    drawCanvas()
  }
})

watch(imageUrl, async () => {
  await nextTick()
  drawCanvas()
})

// 监听 operations 变化，需要时重新绘制
watch(() => props.operations, async () => {
  // 检查是否有有效的 operations（非空数组）
  let hasOps = false
  if (Array.isArray(props.operations) && props.operations.length > 0) {
    hasOps = true
  } else if (typeof props.operations === 'string' && props.operations.trim().startsWith('[')) {
    hasOps = true
  }

  if (!imageUrl.value && hasOps && props.canvasId) {
    await nextTick()
    redrawCanvas()
  }
}, { immediate: true })

const downloadCanvas = () => {
  if (!imageUrl.value) return
  const link = document.createElement('a')
  link.download = `canvas_${props.canvasId}.png`
  link.href = imageUrl.value
  link.click()
  ElMessage.success('图片已下载')
}

const copyDataUrl = async () => {
  if (!imageUrl.value) return

  try {
    const response = await fetch(imageUrl.value)
    const blob = await response.blob()
    await navigator.clipboard.write([
      new ClipboardItem({ 'image/png': blob })
    ])
    ElMessage.success('已复制到剪贴板')
  } catch {
    try {
      await navigator.clipboard.writeText(imageUrl.value)
      ElMessage.success('Data URL 已复制')
    } catch {
      ElMessage.error('复制失败')
    }
  }
}

const formatSize = (length: number): string => {
  const kb = length / 1024
  if (kb < 1024) {
    return `${kb.toFixed(1)} KB`
  }
  return `${(kb / 1024).toFixed(1)} MB`
}
</script>

<style scoped>
.canvas-display {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  max-width: 100%;
}

.canvas-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.canvas-title {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.canvas-actions {
  display: flex;
  gap: 4px;
}

.canvas-content {
  padding: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.canvas-element {
  max-width: 100%;
  height: auto;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: repeating-conic-gradient(#f0f0f0 0% 25%, white 0% 50%) 50% / 16px 16px;
}

.canvas-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px;
  color: #6b7280;
}

.canvas-loading .el-icon {
  font-size: 24px;
  color: #667eea;
}

.canvas-info {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #6b7280;
}
</style>