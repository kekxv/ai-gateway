<template>
  <div class="yolo-redraw-display">
    <div class="yolo-header">
      <span class="yolo-title">YOLO 绘图结果</span>
    </div>
    <div class="yolo-content">
      <canvas
        ref="canvasRef"
        class="yolo-canvas"
        v-show="hasImage"
      ></canvas>
      <div v-if="!hasImage" class="yolo-no-image">
        <el-icon><Picture /></el-icon>
        <span>无法找到原图</span>
      </div>
      <div v-if="hasImage && imageWidth" class="yolo-info">
        <span>{{ imageWidth }} x {{ imageHeight }} px</span>
        <span>{{ boxCount }} 个目标</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Picture } from '@element-plus/icons-vue'

interface YoloBox {
  x: number       // 左上角 x 坐标比例 (0-1)
  y: number       // 左上角 y 坐标比例 (0-1)
  width: number   // 宽度比例 (0-1)
  height: number  // 高度比例 (0-1)
  label?: string
  color?: string
  confidence?: number
}

const props = defineProps<{
  requestMessages?: Array<{ role: string; content: string | unknown }>
  boxes?: YoloBox[]
  defaultColor?: string
  lineWidth?: number
  fontSize?: number
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const hasImage = ref(false)
const imageWidth = ref(0)
const imageHeight = ref(0)
const boxCount = ref(0)

// 从请求消息中找到最新的图片
function findLatestImage(): string | null {
  if (!props.requestMessages) return null

  // 从后往前查找最新的用户图片消息
  for (let i = props.requestMessages.length - 1; i >= 0; i--) {
    const msg = props.requestMessages[i]
    if (msg.role === 'user') {
      let content = msg.content

      // content 可能是 JSON 字符串（多模态格式），需要解析
      if (typeof content === 'string') {
        try {
          const parsed = JSON.parse(content)
          if (Array.isArray(parsed)) {
            content = parsed
          }
        } catch {
          // 解析失败，说明是纯文本，继续
        }
      }

      if (Array.isArray(content)) {
        // 查找图片部分（从后往前，找这张消息中最后一张图片）
        for (let j = content.length - 1; j >= 0; j--) {
          const part = content[j]
          if (part.type === 'image_url' && part.image_url?.url) {
            return part.image_url.url
          }
        }
      }
    }
  }
  return null
}

const redrawYolo = async () => {
  const imageUrl = findLatestImage()
  if (!imageUrl || !props.boxes || props.boxes.length === 0) {
    hasImage.value = false
    return
  }

  const boxes = props.boxes
  const defaultColor = props.defaultColor || '#ff0000'
  const lineWidth = props.lineWidth || 2
  const fontSize = props.fontSize || 14

  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // 加载图片
  const img = new Image()
  img.crossOrigin = 'anonymous'

  img.onload = () => {
    canvas.width = img.width
    canvas.height = img.height
    imageWidth.value = img.width
    imageHeight.value = img.height

    // 先绘制原图
    ctx.drawImage(img, 0, 0)

    // 设置绘图样式
    ctx.lineWidth = lineWidth
    ctx.font = `${fontSize}px Arial`
    ctx.textBaseline = 'top'

    // 绘制每个边界框
    for (const box of boxes) {
      // 将比例坐标转换为像素坐标
      const left = box.x * canvas.width
      const top = box.y * canvas.height
      const boxWidth = box.width * canvas.width
      const boxHeight = box.height * canvas.height

      const color = box.color || defaultColor

      // 绘制边界框
      ctx.strokeStyle = color
      ctx.strokeRect(left, top, boxWidth, boxHeight)

      // 绘制标签
      if (box.label || box.confidence !== undefined) {
        const labelText = box.label || ''
        const confText = box.confidence !== undefined
          ? ` ${(box.confidence * 100).toFixed(0)}%`
          : ''
        const fullText = labelText + confText

        const textWidth = ctx.measureText(fullText).width

        // 绘制标签背景
        ctx.fillStyle = color
        ctx.fillRect(left, top - fontSize - 4, textWidth + 8, fontSize + 4)

        // 绘制标签文字（白色）
        ctx.fillStyle = '#ffffff'
        ctx.fillText(fullText, left + 4, top - fontSize - 2)
      }
    }

    hasImage.value = true
    boxCount.value = boxes.length
  }

  img.onerror = () => {
    hasImage.value = false
  }

  img.src = imageUrl
}

onMounted(() => {
  redrawYolo()
})

watch(() => [props.requestMessages, props.boxes], () => {
  redrawYolo()
}, { deep: true })
</script>

<style scoped>
.yolo-redraw-display {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  max-width: 100%;
}

.yolo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-bottom: 1px solid #fcd34d;
}

.yolo-title {
  font-size: 13px;
  font-weight: 500;
  color: #92400e;
}

.yolo-content {
  padding: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.yolo-canvas {
  max-width: 100%;
  height: auto;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
}

.yolo-no-image {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px;
  color: #6b7280;
}

.yolo-no-image .el-icon {
  font-size: 24px;
}

.yolo-info {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #6b7280;
}
</style>