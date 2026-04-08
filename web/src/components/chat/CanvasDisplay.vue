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
      <div v-if="!imageUrl" class="canvas-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
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
}>()

const canvasStore = useCanvasStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)

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
  return data || { dataUrl: '', width: 400, height: 300 }
})

const imageUrl = computed(() => canvasData.value.dataUrl)
const imageWidth = computed(() => canvasData.value.width)
const imageHeight = computed(() => canvasData.value.height)

const drawCanvas = () => {
  if (!canvasRef.value || !imageUrl.value) return
  const ctx = canvasRef.value.getContext('2d')
  if (!ctx) return

  const img = new Image()
  img.onload = () => {
    // Ensure canvas dimensions match image data
    if (canvasRef.value) {
      ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
      ctx.drawImage(img, 0, 0)
    }
  }
  img.src = imageUrl.value
}

onMounted(() => {
  drawCanvas()
})

watch(imageUrl, async () => {
  await nextTick()
  drawCanvas()
})

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