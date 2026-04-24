import { ref, computed, type Ref } from 'vue'
import { ElMessage } from '@/plugins/element-plus-services'
import { compressImage, isImageFile, formatFileSize } from '@/utils/imageUtils'
import type { ChatContentPart } from '@/types/conversation'
import { useImageStore } from '@/stores/image'

export interface AttachedFile {
  dataUrl: string
  filename: string
  isImage: boolean
  part: { type: string; image_url?: { url: string } }
}

export function useChatFiles(
  fileInputRef: Ref<HTMLInputElement | null>,
  currentConversation: Ref<{ id: number } | null>,
  sending: Ref<boolean>
) {
  const attachedFiles = ref<AttachedFile[]>([])
  const imageStore = useImageStore()

  // Trigger file upload dialog
  const triggerUpload = () => {
    fileInputRef.value?.click()
  }

  // Convert file to base64
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  // Add file to attached files list
  const addFile = async (file: File) => {
    // Check file size (max 20MB)
    if (file.size > 20 * 1024 * 1024) {
      ElMessage.error('文件太大，最大支持20MB')
      return
    }

    const isImage = isImageFile(file)
    let dataUrl: string

    if (isImage) {
      // Compress image
      try {
        const result = await compressImage(file)
        dataUrl = result.dataUrl
        if (result.compressedSize < result.originalSize) {
          console.log(`图片压缩: ${formatFileSize(result.originalSize)} -> ${formatFileSize(result.compressedSize)}`)
        }
      } catch {
        // Compression failed, use original
        dataUrl = await fileToBase64(file)
      }
    } else {
      // Non-image file: convert directly
      dataUrl = await fileToBase64(file)
    }

    attachedFiles.value.push({
      dataUrl,
      filename: file.name,
      isImage,
      part: {
        type: isImage ? 'image_url' : 'text',
        image_url: isImage ? { url: dataUrl } : undefined
      }
    })

    // Save to imageStore for yolo-draw
    if (isImage) {
      const imageId = `image_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
      imageStore.addImage({
        id: imageId,
        dataUrl,
        createdAt: Date.now()
      })
    }
  }

  // Handle file upload from input element
  const handleFileUpload = async (event: Event) => {
    const target = event.target as HTMLInputElement
    const files = target.files
    if (!files) return

    for (const file of Array.from(files)) {
      await addFile(file)
    }
    // Reset input
    target.value = ''
  }

  // Handle paste event (for images)
  const handlePaste = async (e: ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return

    let hasFile = false
    const itemsArray = Array.from(items)
    
    // Check if there are any files first
    if (itemsArray.some(item => item.kind === 'file')) {
      hasFile = true
    }

    if (hasFile) {
      // If there are files, we handle them and prevent default text pasting
      // (which often includes the filename)
      e.preventDefault()
      
      for (const item of itemsArray) {
        if (item.kind === 'file') {
          const file = item.getAsFile()
          if (file) {
            await addFile(file)
          }
        }
      }
    }
  }

  // Remove file from attached files list
  const removeFile = (index: number) => {
    attachedFiles.value.splice(index, 1)
  }

  // Build parts array from input content and attached files
  const buildContentParts = (textContent: string): ChatContentPart[] => {
    const parts: ChatContentPart[] = []
    if (textContent) {
      parts.push({ type: 'text', text: textContent })
    }
    for (const file of attachedFiles.value) {
      if (file.part.image_url) {
        parts.push({ type: 'image_url', image_url: file.part.image_url })
      }
    }
    return parts
  }

  // Clear attached files
  const clearFiles = () => {
    attachedFiles.value = []
  }

  // Check if can upload
  const canUpload = computed(() => currentConversation.value && !sending.value)

  return {
    attachedFiles,
    triggerUpload,
    handleFileUpload,
    handlePaste,
    addFile,
    removeFile,
    fileToBase64,
    buildContentParts,
    clearFiles,
    canUpload
  }
}
