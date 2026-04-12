import { defineStore } from 'pinia'
import { reactive, ref, computed } from 'vue'

export interface CanvasData {
  id: string
  width: number
  height: number
  dataUrl: string  // base64 图片数据
  createdAt: number
}

export const useCanvasStore = defineStore('canvas', () => {
  // 使用 reactive 创建响应式 Map
  const canvases = reactive(new Map<string, CanvasData>())
  const latestCanvasId = ref<string | null>(null)

  // 计算属性：所有 canvas 的数组（用于响应式遍历）
  const canvasList = computed(() => {
    return Array.from(canvases.values())
  })

  function addCanvas(data: CanvasData) {
    canvases.set(data.id, data)
    latestCanvasId.value = data.id
  }

  function getCanvas(id: string): CanvasData | undefined {
    return canvases.get(id)
  }

  function clearCanvas(id: string) {
    canvases.delete(id)
    if (latestCanvasId.value === id) {
      latestCanvasId.value = null
    }
  }

  function clearAll() {
    canvases.clear()
    latestCanvasId.value = null
  }

  return {
    canvases,
    canvasList,
    latestCanvasId,
    addCanvas,
    getCanvas,
    clearCanvas,
    clearAll
  }
})