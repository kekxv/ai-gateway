import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ImageData {
  id: string
  dataUrl: string  // base64 图片数据或 URL
  createdAt: number
}

export const useImageStore = defineStore('image', () => {
  const images = ref<Map<string, ImageData>>(new Map())
  const latestImageId = ref<string | null>(null)

  function addImage(data: ImageData) {
    images.value.set(data.id, data)
    latestImageId.value = data.id
  }

  function getImage(id: string): ImageData | undefined {
    return images.value.get(id)
  }

  function getLatestImage(): ImageData | undefined {
    if (!latestImageId.value) return undefined
    return images.value.get(latestImageId.value)
  }

  function removeImage(id: string) {
    images.value.delete(id)
    if (latestImageId.value === id) {
      // Find the next latest image
      const remaining = Array.from(images.value.entries())
      if (remaining.length > 0) {
        // Sort by createdAt descending and get the latest
        remaining.sort((a, b) => b[1].createdAt - a[1].createdAt)
        latestImageId.value = remaining[0][0]
      } else {
        latestImageId.value = null
      }
    }
  }

  function clearAll() {
    images.value.clear()
    latestImageId.value = null
  }

  return {
    images,
    latestImageId,
    addImage,
    getImage,
    getLatestImage,
    removeImage,
    clearAll
  }
})