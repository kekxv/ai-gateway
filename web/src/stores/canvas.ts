import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface CanvasData {
  id: string
  width: number
  height: number
  dataUrl: string  // base64 图片数据
  createdAt: number
}

export const useCanvasStore = defineStore('canvas', () => {
  const canvases = ref<Map<string, CanvasData>>(new Map())
  const latestCanvasId = ref<string | null>(null)

  function addCanvas(data: CanvasData) {
    canvases.value.set(data.id, data)
    latestCanvasId.value = data.id
  }

  function getCanvas(id: string): CanvasData | undefined {
    return canvases.value.get(id)
  }

  function clearCanvas(id: string) {
    canvases.value.delete(id)
    if (latestCanvasId.value === id) {
      latestCanvasId.value = null
    }
  }

  function clearAll() {
    canvases.value.clear()
    latestCanvasId.value = null
  }

  return {
    canvases,
    latestCanvasId,
    addCanvas,
    getCanvas,
    clearCanvas,
    clearAll
  }
})