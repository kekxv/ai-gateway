/**
 * 图片压缩工具
 * 用于在前端压缩大图片，减少上传大小
 */

interface CompressionOptions {
  maxWidth: number      // 最大宽度
  maxHeight: number     // 最大高度
  quality: number       // JPEG 质量 (0-1)
  maxSizeMB: number     // 最大文件大小 MB
}

interface CompressionResult {
  dataUrl: string       // 压缩后的 base64 Data URL
  originalSize: number  // 原始文件大小 (bytes)
  compressedSize: number // 压缩后大小 (bytes)
  width: number         // 压缩后宽度
  height: number        // 压缩后高度
}

const DEFAULT_OPTIONS: CompressionOptions = {
  maxWidth: 1024,
  maxHeight: 1024,
  quality: 0.8,
  maxSizeMB: 1
}

/**
 * 压缩图片
 * @param file 图片文件
 * @param options 压缩选项
 * @returns 压缩结果
 */
export async function compressImage(
  file: File,
  options?: Partial<CompressionOptions>
): Promise<CompressionResult> {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const originalSize = file.size

  // 如果图片较小（< 200KB）且尺寸不大，不压缩
  if (originalSize < 200 * 1024) {
    const dataUrl = await fileToBase64(file)
    const img = await loadImage(dataUrl)
    return {
      dataUrl,
      originalSize,
      compressedSize: originalSize,
      width: img.width,
      height: img.height
    }
  }

  // 加载图片
  const dataUrl = await fileToBase64(file)
  const img = await loadImage(dataUrl)

  // 计算缩放后的尺寸
  let width = img.width
  let height = img.height

  if (width > opts.maxWidth || height > opts.maxHeight) {
    const ratio = Math.min(opts.maxWidth / width, opts.maxHeight / height)
    width = Math.round(width * ratio)
    height = Math.round(height * ratio)
  }

  // 创建 Canvas 并绘制缩放后的图片
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')

  if (!ctx) {
    throw new Error('无法创建 Canvas context')
  }

  // 使用平滑缩放
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(img, 0, 0, width, height)

  // 压缩为 JPEG
  let quality = opts.quality
  let compressedDataUrl = canvas.toDataURL('image/jpeg', quality)
  let compressedSize = getDataUrlSize(compressedDataUrl)

  // 如果仍然超过最大大小，递归降低质量
  const maxSizeBytes = opts.maxSizeMB * 1024 * 1024
  while (compressedSize > maxSizeBytes && quality > 0.1) {
    quality -= 0.1
    compressedDataUrl = canvas.toDataURL('image/jpeg', quality)
    compressedSize = getDataUrlSize(compressedDataUrl)
  }

  return {
    dataUrl: compressedDataUrl,
    originalSize,
    compressedSize,
    width,
    height
  }
}

/**
 * 将 File 转换为 base64 Data URL
 */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/**
 * 加载图片
 */
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

/**
 * 计算 Data URL 的文件大小（字节）
 */
function getDataUrlSize(dataUrl: string): number {
  // Data URL 格式: data:[mime];base64,[data]
  const base64 = dataUrl.split(',')[1] || ''
  // Base64 编码后大小约为原始大小的 4/3
  return Math.round(base64.length * 0.75)
}

/**
 * 判断文件是否为图片
 */
export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/')
}

/**
 * 格式化文件大小显示
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  } else if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  } else {
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }
}