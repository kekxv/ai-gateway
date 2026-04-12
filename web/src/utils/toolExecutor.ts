/**
 * 工具执行器
 * 执行内置工具和自定义工具并返回结果
 */

import type { ToolCallResult, ToolDefinition } from '@/types/tool'
import type { ChatContentPart } from '@/types/conversation'
import { useToolsStore } from '@/stores/tools'
import { useAuthStore } from '@/stores/auth'
import { useCanvasStore } from '@/stores/canvas'
import { useImageStore } from '@/stores/image'

// 消息类型，用于查找图片
interface MessageLike {
  role: string
  content: string | ChatContentPart[]
}

// 当前消息列表（由 ChatView 设置）
let currentMessages: MessageLike[] = []

// 设置当前消息列表（供 ChatView 调用）
export function setMessagesForToolExecution(messages: MessageLike[]) {
  currentMessages = messages
}

// 从工具调用之前的消息中获取最新图片
// 工具调用在助手消息中，所以要找助手消息之前的用户图片
function getLatestImageFromMessages(): { dataUrl: string; id: string } | null {
  // 从末尾往前查找，跳过助手消息（工具调用在助手消息中）
  // 找到最近的包含图片的用户消息
  for (let i = currentMessages.length - 1; i >= 0; i--) {
    const msg = currentMessages[i]
    // 跳过助手消息和 tool 消息，只找用户消息
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
            const imageId = `msg_image_${i}_${j}`
            return { dataUrl: part.image_url.url, id: imageId }
          }
        }
      }
    }
  }
  return null
}

/**
 * 执行工具调用
 */
export async function executeToolCall(
  toolName: string,
  args: Record<string, unknown>
): Promise<ToolCallResult> {
  const id = `tool_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

  const result: ToolCallResult = {
    id,
    toolName,
    arguments: args,
    status: 'running'
  }

  try {
    // 先检查是否是自定义工具
    const toolsStore = useToolsStore()
    const customTool = toolsStore.customTools.find(t => t.name === toolName)

    if (customTool && customTool.executionCode) {
      // 执行自定义工具代码
      const output = await executeCustomTool(customTool, args)
      result.status = 'success'
      result.result = output
    } else {
      // 执行内置工具
      const output = await executeBuiltinTool(toolName, args)
      result.status = 'success'
      result.result = output
    }
  } catch (error) {
    result.status = 'error'
    result.error = error instanceof Error ? error.message : String(error)
  }

  return result
}

/**
 * 执行自定义工具代码
 */
async function executeCustomTool(
  tool: ToolDefinition,
  args: Record<string, unknown>
): Promise<unknown> {
  if (!tool.executionCode) {
    throw new Error(`自定义工具 "${tool.name}" 没有定义执行代码`)
  }

  try {
    // 创建一个安全的执行环境，将参数传入
    const safeExec = new Function('args', `
      "use strict";
      ${tool.executionCode}
    `)
    const output = await safeExec(args)
    return output
  } catch (error) {
    throw new Error(`工具 "${tool.name}" 执行错误: ${error instanceof Error ? error.message : String(error)}`)
  }
}

/**
 * 执行内置工具
 */
async function executeBuiltinTool(
  toolName: string,
  args: Record<string, unknown>
): Promise<unknown> {
  switch (toolName) {
    case 'get_current_time':
      return getCurrentTime(args.timezone as string | undefined)

    case 'get_location':
      return getLocation(args.enableHighAccuracy as boolean | undefined)

    case 'web_search':
      return webSearch(
        args.query as string,
        args.location as string | undefined,
        args.hl as string | undefined,
        args.gl as string | undefined
      )

    case 'fetch_webpage':
      return fetchWebpage(
        args.url as string,
        args.selector as string | undefined,
        args.format as string | undefined
      )

    case 'web_canvas':
      return executeCanvas(
        args.operations as Array<Record<string, unknown>>,
        args.width as number | undefined,
        args.height as number | undefined,
        args.backgroundColor as string | undefined
      )

    case 'execute_javascript':
      return executeJavaScript(
        args.code as string,
        args.timeout as number | undefined
      )

    case 'yolo_draw':
      return executeYoloDraw(
        args.boxes as Array<Record<string, unknown>>,
        args.color as string | undefined,
        args.lineWidth as number | undefined,
        args.fontSize as number | undefined,
        args.showConfidence as boolean | undefined
      )

    default:
      throw new Error(`Unknown tool: ${toolName}`)
  }
}

/**
 * 获取当前时间
 */
function getCurrentTime(timezone?: string): object {
  const now = new Date()
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    weekday: 'long',
    timeZone: timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
  }

  return {
    iso: now.toISOString(),
    formatted: now.toLocaleString('zh-CN', options),
    timezone: timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
    timestamp: now.getTime()
  }
}

/**
 * 获取当前地理位置
 */
function getLocation(enableHighAccuracy?: boolean): Promise<object> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('浏览器不支持地理位置功能'))
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          altitude: position.coords.altitude,
          altitudeAccuracy: position.coords.altitudeAccuracy,
          heading: position.coords.heading,
          speed: position.coords.speed,
          timestamp: new Date(position.timestamp).toISOString()
        })
      },
      (error) => {
        const errorMessages: Record<number, string> = {
          1: '用户拒绝了地理位置请求',
          2: '无法获取位置信息',
          3: '获取位置超时'
        }
        reject(new Error(errorMessages[error.code] || `定位错误: ${error.message}`))
      },
      {
        enableHighAccuracy: enableHighAccuracy ?? false,
        timeout: 10000,
        maximumAge: 60000
      }
    )
  })
}

/**
 * 执行 JavaScript 代码
 */
function executeJavaScript(code: string, timeout?: number): unknown {
  const logs: Array<{ type: string; message: string }> = []
  const maxTimeout = Math.min(timeout || 5000, 30000)

  // 创建捕获 console 输出的代理
  const createConsoleProxy = (type: string) => {
    return (...args: unknown[]) => {
      const message = args.map(arg => {
        if (typeof arg === 'object') {
          try {
            return JSON.stringify(arg, null, 2)
          } catch {
            return String(arg)
          }
        }
        return String(arg)
      }).join(' ')
      logs.push({ type, message })
    }
  }

  const mockConsole = {
    log: createConsoleProxy('log'),
    info: createConsoleProxy('info'),
    warn: createConsoleProxy('warn'),
    error: createConsoleProxy('error'),
    debug: createConsoleProxy('debug'),
    trace: createConsoleProxy('trace'),
    dir: createConsoleProxy('dir'),
    table: createConsoleProxy('table'),
    time: () => {},
    timeEnd: () => {},
    group: () => {},
    groupEnd: () => {},
    clear: () => {}
  }

  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error(`执行超时 (${maxTimeout}ms)`))
    }, maxTimeout)

    try {
      // 创建带 console 代理的执行环境
      const safeEval = new Function('console', `
        "use strict";
        ${code}
      `)

      const result = safeEval(mockConsole)

      // 处理 Promise 结果
      Promise.resolve(result).then(resolvedResult => {
        clearTimeout(timeoutId)
        resolve({
          success: true,
          result: resolvedResult,
          logs: logs.length > 0 ? logs : undefined,
          logOutput: logs.length > 0 ? logs.map(l => `[${l.type}] ${l.message}`).join('\n') : undefined
        })
      }).catch(err => {
        clearTimeout(timeoutId)
        reject(new Error(`执行错误: ${err instanceof Error ? err.message : String(err)}`))
      })
    } catch (error) {
      clearTimeout(timeoutId)
      throw new Error(`JavaScript 执行错误: ${error instanceof Error ? error.message : String(error)}`)
    }
  })
}

/**
 * 网页搜索 (通过后端代理)
 */
async function webSearch(
  query: string,
  location?: string,
  hl?: string,
  gl?: string
): Promise<object> {
  const authStore = useAuthStore()
  const token = authStore.token

  if (!token) {
    throw new Error('请先登录后再使用搜索功能')
  }

  try {
    const response = await fetch('/api/tools/web-search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        query,
        location: location || 'Austin, Texas, United States',
        hl: hl || 'en',
        gl: gl || 'us'
      })
    })

    if (response.status === 401) {
      throw new Error('登录已过期，请重新登录')
    }

    if (response.status === 403) {
      throw new Error('没有权限执行此操作')
    }

    if (response.status === 429) {
      throw new Error('请求过于频繁，请稍后再试')
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: '请求失败' }))
      throw new Error(errorData.error || `搜索失败: ${response.status}`)
    }

    return await response.json()
  } catch (error) {
    if (error instanceof Error) {
      throw error
    }
    throw new Error(`搜索失败: ${String(error)}`)
  }
}

/**
 * 获取网页内容 (通过后端代理)
 */
async function fetchWebpage(url: string, selector?: string, format?: string): Promise<object> {
  const authStore = useAuthStore()
  const token = authStore.token

  if (!token) {
    throw new Error('请先登录后再使用网页获取功能')
  }

  try {
    const response = await fetch('/api/tools/fetch-webpage', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        url,
        selector,
        format: format || 'text'
      })
    })

    if (response.status === 401) {
      throw new Error('登录已过期，请重新登录')
    }

    if (response.status === 403) {
      throw new Error('没有权限执行此操作')
    }

    if (response.status === 429) {
      throw new Error('请求过于频繁，请稍后再试')
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: '请求失败' }))
      throw new Error(errorData.error || `获取网页失败: ${response.status}`)
    }

    return await response.json()
  } catch (error) {
    if (error instanceof Error) {
      throw error
    }
    throw new Error(`获取网页失败: ${String(error)}`)
  }
}

/**
 * Canvas 绘图操作类型
 * 支持两种字段名：type 和 operation（AI 可能使用不同的字段名）
 * 使用单个 [key: string] 索引签名来支持所有可能的参数
 */
interface CanvasOperation {
  type?: string
  operation?: string
  // 使用索引签名支持所有参数，避免重复定义
  [key: string]: unknown
}

/**
 * 从操作参数中提取填充颜色
 * 支持多种格式：
 * - fill 直接作为颜色值（如 fill: "#38761d"）
 * - fillColor, fillStyle 作为颜色字段
 * - style.fill, style.fillStyle 嵌套格式
 */
function getFillColor(params: Record<string, unknown>, defaultColor = '#000000'): string {
  // Check if fill is directly a color string (not boolean)
  const fill = params.fill
  if (typeof fill === 'string' && fill !== '') {
    return fill
  }
  if (params.fillColor) return params.fillColor as string
  if (params.fillStyle) return params.fillStyle as string
  if (params.style && typeof params.style === 'object') {
    const style = params.style as { fill?: string; fillStyle?: string }
    if (style?.fill) return style.fill
    if (style?.fillStyle) return style.fillStyle
  }
  return defaultColor
}

/**
 * 检查是否需要填充
 * fill 为 true 或 fill 为颜色字符串时都返回 true
 */
function shouldFill(params: Record<string, unknown>): boolean {
  const fill = params.fill
  return fill === true || (typeof fill === 'string' && fill !== '')
}

/**
 * 检查是否需要描边
 * stroke 为 true 或 stroke 为颜色字符串时都返回 true
 */
function shouldStroke(params: Record<string, unknown>): boolean {
  const stroke = params.stroke
  return stroke === true || (typeof stroke === 'string' && stroke !== '')
}

/**
 * 从操作参数中提取描边颜色
 * 支持多种格式：stroke（直接颜色），strokeColor, strokeStyle, style.stroke, style.strokeStyle
 */
function getStrokeColor(params: Record<string, unknown>, defaultColor = '#000000'): string {
  // Check if stroke is directly a color string (not boolean)
  const stroke = params.stroke
  if (typeof stroke === 'string' && stroke !== '') {
    return stroke
  }
  if (params.strokeColor) return params.strokeColor as string
  if (params.strokeStyle) return params.strokeStyle as string
  if (params.style && typeof params.style === 'object') {
    const style = params.style as { stroke?: string; strokeStyle?: string }
    if (style?.stroke) return style.stroke
    if (style?.strokeStyle) return style.strokeStyle
  }
  return defaultColor
}

/**
 * 从操作参数中提取线宽
 */
function getLineWidth(params: Record<string, unknown>, defaultWidth = 1): number {
  if (params.lineWidth) return params.lineWidth as number
  if (params.style && typeof params.style === 'object') {
    const style = params.style as { lineWidth?: number }
    if (style?.lineWidth) return style.lineWidth
  }
  return defaultWidth
}

/**
 * 执行 Canvas 绘图
 */
function executeCanvas(
  operations: CanvasOperation[],
  width?: number,
  height?: number,
  backgroundColor?: string
): object {
  const canvasWidth = Math.max(1, Math.min(width || 400, 2000))
  const canvasHeight = Math.max(1, Math.min(height || 300, 2000))

  // 扁平化嵌套的 operations（AI 可能返回 {"operations:[{"operations":[...]}]}）
  let flatOperations: CanvasOperation[] = []
  if (Array.isArray(operations)) {
    for (const op of operations) {
      if (op && typeof op === 'object' && Array.isArray(op.operations)) {
        // 嵌套结构：{"operations": [...]}
        flatOperations = flatOperations.concat(op.operations as CanvasOperation[])
      } else if (op && (op.type || op.operation)) {
        // 直接操作：{"type": "rect", ...}
        flatOperations.push(op as CanvasOperation)
      }
    }
  }

  // 创建 Canvas 元素
  const canvas = document.createElement('canvas')
  canvas.width = canvasWidth
  canvas.height = canvasHeight
  const ctx = canvas.getContext('2d')

  if (!ctx) {
    throw new Error('无法创建 Canvas 上下文')
  }

  // 设置默认样式
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  // 先填充背景（如果指定了背景色且不是透明）
  const bgColor = backgroundColor || '#ffffff'
  if (bgColor.toLowerCase() !== 'transparent') {
    ctx.fillStyle = bgColor
    ctx.fillRect(0, 0, canvasWidth, canvasHeight)
  }

  // 设置默认绘图样式
  ctx.strokeStyle = '#000000'
  ctx.fillStyle = '#000000'
  ctx.lineWidth = 1

  // 执行绘图操作
  const executedOps: string[] = []
  for (const op of flatOperations) {
    try {
      executeCanvasOperation(ctx, op)
      const opType = op.type || op.operation
      if (opType) {
        executedOps.push(opType)
      }
    } catch (err) {
      const opType = op.type || op.operation
      console.warn(`Canvas 操作执行失败: ${opType}`, err)
    }
  }

  // 获取图片数据
  const dataUrl = canvas.toDataURL('image/png')
  const canvasId = `canvas_${Date.now()}`

  // 保存到 store（用于页面显示）
  const canvasStore = useCanvasStore()
  canvasStore.addCanvas({
    id: canvasId,
    width: canvasWidth,
    height: canvasHeight,
    dataUrl,
    createdAt: Date.now()
  })

  // 只返回成功状态和 canvasId，图片已在页面上显示
  return {
    success: true,
    canvasId,
    width: canvasWidth,
    height: canvasHeight,
    message: `绘图完成，共执行 ${executedOps.length} 个操作，图片已在页面上显示`
  }
}

/**
 * 执行单个绑绑定绘图操作
 */
function executeCanvasOperation(ctx: CanvasRenderingContext2D, op: CanvasOperation) {
  // 兼容两种字段名：type 和 operation
  const opType = op.type || op.operation
  const { type, operation, ...params } = op

  if (!opType) return

  switch (opType) {
    // ========== 基础操作 ==========
    case 'clear':
      ctx.clearRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? ctx.canvas.width,
        (params.height as number) ?? ctx.canvas.height
      )
      break

    case 'clearRect':
      ctx.clearRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? ctx.canvas.width,
        (params.height as number) ?? ctx.canvas.height
      )
      break

    // ========== 形状绘制 ==========
    case 'fill':
      // 填充整个画布或指定区域
      ctx.fillStyle = getFillColor(params)
      ctx.fillRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? ctx.canvas.width,
        (params.height as number) ?? ctx.canvas.height
      )
      break

    case 'fillRect':
      ctx.fillStyle = getFillColor(params)
      ctx.fillRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? 100,
        (params.height as number) ?? 100
      )
      break

    case 'stroke':
      ctx.strokeStyle = getStrokeColor(params)
      ctx.lineWidth = getLineWidth(params)
      ctx.strokeRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? 100,
        (params.height as number) ?? 100
      )
      break

    case 'strokeRect':
      ctx.strokeStyle = getStrokeColor(params)
      ctx.lineWidth = getLineWidth(params)
      ctx.strokeRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? 100,
        (params.height as number) ?? 100
      )
      break

    case 'rect': {
      const rx = (params.x as number) ?? 0
      const ry = (params.y as number) ?? 0
      const rw = (params.width as number) ?? 100
      const rh = (params.height as number) ?? 100

      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fillRect(rx, ry, rw, rh)
      }
      if (shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.strokeRect(rx, ry, rw, rh)
      }
      // If no fill/stroke specified, default to fill with default color
      if (!shouldFill(params) && !shouldStroke(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fillRect(rx, ry, rw, rh)
      }
      break
    }

    case 'roundRect': {
      const rx = (params.x as number) ?? 0
      const ry = (params.y as number) ?? 0
      const rw = (params.width as number) ?? 100
      const rh = (params.height as number) ?? 100
      const radii = params.radii as number | number[] | undefined
      const radius = (params.radius as number) ?? 10

      ctx.beginPath()
      // roundRect 是较新的 API，需要检查兼容性
      if (typeof ctx.roundRect === 'function') {
        if (radii !== undefined) {
          ctx.roundRect(rx, ry, rw, rh, Array.isArray(radii) ? radii : radii)
        } else {
          ctx.roundRect(rx, ry, rw, rh, radius)
        }
      } else {
        // 手动绘制圆角矩形
        const r = Array.isArray(radii) ? radii[0] : (radii ?? radius)
        ctx.moveTo(rx + r, ry)
        ctx.lineTo(rx + rw - r, ry)
        ctx.arcTo(rx + rw, ry, rx + rw, ry + r, r)
        ctx.lineTo(rx + rw, ry + rh - r)
        ctx.arcTo(rx + rw, ry + rh, rx + rw - r, ry + rh, r)
        ctx.lineTo(rx + r, ry + rh)
        ctx.arcTo(rx, ry + rh, rx, ry + rh - r, r)
        ctx.lineTo(rx, ry + r)
        ctx.arcTo(rx, ry, rx + r, ry, r)
        ctx.closePath()
      }

      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      if (shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      if (!shouldFill(params) && !shouldStroke(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      break
    }

    case 'circle': {
      const cx = (params.x as number) ?? 0
      const cy = (params.y as number) ?? 0
      const radius = Math.max(0, (params.radius as number) ?? 50)
      const startAngle = (params.startAngle as number) ?? 0
      const endAngle = (params.endAngle as number) ?? Math.PI * 2

      ctx.beginPath()
      ctx.arc(cx, cy, radius, startAngle, endAngle)

      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      if (shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      // If no fill/stroke specified, default to fill with the fill color (or default)
      if (!shouldFill(params) && !shouldStroke(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      break
    }

    case 'arc': {
      ctx.beginPath()
      ctx.arc(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        Math.max(0, (params.radius as number) ?? 50),
        (params.startAngle as number) ?? 0,
        (params.endAngle as number) ?? Math.PI
      )
      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      if (shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      if (!shouldFill(params) && !shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      break
    }

    case 'arcTo': {
      ctx.beginPath()
      ctx.moveTo((params.x1 as number) ?? 0, (params.y1 as number) ?? 0)
      ctx.arcTo(
        (params.x2 as number) ?? 50,
        (params.y2 as number) ?? 50,
        (params.x3 as number) ?? 100,
        (params.y3 as number) ?? 100,
        (params.radius as number) ?? 20
      )
      if (shouldStroke(params) || !shouldFill(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      break
    }

    case 'ellipse': {
      ctx.beginPath()
      ctx.ellipse(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        Math.max(0, (params.radiusX as number) ?? 50),
        Math.max(0, (params.radiusY as number) ?? 30),
        (params.rotation as number) ?? 0,
        (params.startAngle as number) ?? 0,
        (params.endAngle as number) ?? Math.PI * 2
      )
      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill()
      }
      if (shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      if (!shouldFill(params) && !shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      break
    }

    // ========== 线条绘制 ==========
    case 'line':
      ctx.beginPath()
      ctx.moveTo((params.x1 as number) ?? 0, (params.y1 as number) ?? 0)
      ctx.lineTo((params.x2 as number) ?? 100, (params.y2 as number) ?? 100)
      ctx.strokeStyle = getStrokeColor(params)
      ctx.lineWidth = getLineWidth(params)
      ctx.stroke()
      break

    case 'moveTo':
      ctx.moveTo((params.x as number) ?? 0, (params.y as number) ?? 0)
      break

    case 'lineTo':
      ctx.lineTo((params.x as number) ?? 0, (params.y as number) ?? 0)
      break

    case 'polyline':
    case 'polygon': {
      const points = params.points as Array<{ x: number; y: number }> | undefined
      if (!points || points.length < 2) break

      ctx.beginPath()
      ctx.moveTo(points[0].x, points[0].y)
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y)
      }

      if (opType === 'polygon') {
        ctx.closePath()
        if (shouldFill(params)) {
          ctx.fillStyle = getFillColor(params)
          ctx.fill()
        }
      }
      if (shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      if (!shouldFill(params) && !shouldStroke(params)) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke()
      }
      break
    }

    case 'bezier':
    case 'bezierCurveTo': {
      ctx.beginPath()
      ctx.moveTo((params.x1 as number) ?? 0, (params.y1 as number) ?? 0)
      if (params.cp2x !== undefined && params.cp2y !== undefined) {
        // Cubic bezier
        ctx.bezierCurveTo(
          (params.cp1x as number) ?? 0,
          (params.cp1y as number) ?? 0,
          params.cp2x as number,
          params.cp2y as number,
          (params.x2 as number) ?? 100,
          (params.y2 as number) ?? 100
        )
      } else {
        // Quadratic bezier
        ctx.quadraticCurveTo(
          (params.cpx as number) ?? 50,
          (params.cpy as number) ?? 100,
          (params.x2 as number) ?? 100,
          (params.y2 as number) ?? 50
        )
      }
      ctx.strokeStyle = getStrokeColor(params)
      ctx.lineWidth = getLineWidth(params)
      ctx.stroke()
      break
    }

    case 'quadraticCurveTo': {
      ctx.quadraticCurveTo(
        (params.cpx as number) ?? 50,
        (params.cpy as number) ?? 50,
        (params.x as number) ?? 100,
        (params.y as number) ?? 100
      )
      break
    }

    // ========== 路径操作 ==========
    case 'beginPath':
      ctx.beginPath()
      break

    case 'closePath':
      ctx.closePath()
      break

    case 'fillPath':
      ctx.fillStyle = getFillColor(params)
      ctx.fill()
      break

    case 'strokePath':
      ctx.strokeStyle = getStrokeColor(params)
      ctx.lineWidth = getLineWidth(params)
      ctx.stroke()
      break

    case 'clip':
      ctx.clip()
      break

    case 'path': {
      const pathData = params.d as string | undefined
      if (!pathData) break
      const path = new Path2D(pathData)
      if (shouldFill(params)) {
        ctx.fillStyle = getFillColor(params)
        ctx.fill(path)
      }
      if (shouldStroke(params) || (!shouldFill(params) && !shouldStroke(params))) {
        ctx.strokeStyle = getStrokeColor(params)
        ctx.lineWidth = getLineWidth(params)
        ctx.stroke(path)
      }
      break
    }

    // ========== 文字绘制 ==========
    case 'text':
    case 'fillText': {
      ctx.font = (params.font as string) || '16px Arial'
      ctx.fillStyle = getFillColor(params, '#000000')
      ctx.textAlign = (params.align as CanvasTextAlign) || 'left'
      ctx.textBaseline = (params.baseline as CanvasTextBaseline) || 'top'
      const text = String(params.text ?? '')
      const textX = (params.x as number) ?? 0
      const textY = (params.y as number) ?? 0
      if (params.maxWidth !== undefined) {
        ctx.fillText(text, textX, textY, params.maxWidth as number)
      } else {
        ctx.fillText(text, textX, textY)
      }
      break
    }

    case 'strokeText': {
      ctx.font = (params.font as string) || '16px Arial'
      ctx.strokeStyle = getStrokeColor(params, '#000000')
      ctx.lineWidth = getLineWidth(params)
      ctx.textAlign = (params.align as CanvasTextAlign) || 'left'
      ctx.textBaseline = (params.baseline as CanvasTextBaseline) || 'top'
      const text = String(params.text ?? '')
      const textX = (params.x as number) ?? 0
      const textY = (params.y as number) ?? 0
      if (params.maxWidth !== undefined) {
        ctx.strokeText(text, textX, textY, params.maxWidth as number)
      } else {
        ctx.strokeText(text, textX, textY)
      }
      break
    }

    // ========== 图像操作 ==========
    case 'drawImage': {
      const src = params.src as string | undefined
      const imageId = params.imageId as string | undefined
      if (!src && !imageId) break

      // 获取图片数据
      let imageSrc = src
      if (imageId) {
        const canvasStore = useCanvasStore()
        const canvasData = canvasStore.canvases.get(imageId)
        if (canvasData) {
          imageSrc = canvasData.dataUrl
        }
      }

      if (!imageSrc) break

      // 创建图片并绘制
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        const dx = (params.dx as number) ?? (params.x as number) ?? 0
        const dy = (params.dy as number) ?? (params.y as number) ?? 0
        const dWidth = (params.dWidth as number) ?? (params.width as number) ?? img.width
        const dHeight = (params.dHeight as number) ?? (params.height as number) ?? img.height

        // 支持裁剪参数
        if (params.sx !== undefined) {
          ctx.drawImage(
            img,
            (params.sx as number) ?? 0,
            (params.sy as number) ?? 0,
            (params.sWidth as number) ?? img.width,
            (params.sHeight as number) ?? img.height,
            dx, dy, dWidth, dHeight
          )
        } else {
          ctx.drawImage(img, dx, dy, dWidth, dHeight)
        }
      }
      img.src = imageSrc
      break
    }

    // ========== 渐变与图案 ==========
    case 'linearGradient': {
      const x0 = (params.x0 as number) ?? 0
      const y0 = (params.y0 as number) ?? 0
      const x1 = (params.x1 as number) ?? 100
      const y1 = (params.y1 as number) ?? 100
      const stops = params.stops as Array<{ offset: number; color: string }> | undefined

      const gradient = ctx.createLinearGradient(x0, y0, x1, y1)
      if (stops && Array.isArray(stops)) {
        for (const stop of stops) {
          gradient.addColorStop(stop.offset, stop.color)
        }
      }

      // 应用渐变到后续操作
      if (params.applyTo === 'fill' || !params.applyTo) {
        ctx.fillStyle = gradient
      }
      if (params.applyTo === 'stroke') {
        ctx.strokeStyle = gradient
      }
      break
    }

    case 'radialGradient': {
      const x0 = (params.x0 as number) ?? 50
      const y0 = (params.y0 as number) ?? 50
      const r0 = (params.r0 as number) ?? 0
      const x1 = (params.x1 as number) ?? 50
      const y1 = (params.y1 as number) ?? 50
      const r1 = (params.r1 as number) ?? 50
      const stops = params.stops as Array<{ offset: number; color: string }> | undefined

      const gradient = ctx.createRadialGradient(x0, y0, r0, x1, y1, r1)
      if (stops && Array.isArray(stops)) {
        for (const stop of stops) {
          gradient.addColorStop(stop.offset, stop.color)
        }
      }

      if (params.applyTo === 'fill' || !params.applyTo) {
        ctx.fillStyle = gradient
      }
      if (params.applyTo === 'stroke') {
        ctx.strokeStyle = gradient
      }
      break
    }

    // ========== 样式设置 ==========
    case 'setStyle':
      if (params.fillStyle !== undefined) ctx.fillStyle = params.fillStyle as string
      if (params.strokeStyle !== undefined) ctx.strokeStyle = params.strokeStyle as string
      if (params.lineWidth !== undefined) ctx.lineWidth = params.lineWidth as number
      if (params.lineCap !== undefined) ctx.lineCap = params.lineCap as CanvasLineCap
      if (params.lineJoin !== undefined) ctx.lineJoin = params.lineJoin as CanvasLineJoin
      if (params.font !== undefined) ctx.font = params.font as string
      if (params.globalAlpha !== undefined) ctx.globalAlpha = params.globalAlpha as number
      if (params.globalCompositeOperation !== undefined) ctx.globalCompositeOperation = params.globalCompositeOperation as GlobalCompositeOperation
      if (params.textAlign !== undefined) ctx.textAlign = params.textAlign as CanvasTextAlign
      if (params.textBaseline !== undefined) ctx.textBaseline = params.textBaseline as CanvasTextBaseline
      if (params.direction !== undefined) ctx.direction = params.direction as CanvasDirection
      // 阴影设置
      if (params.shadowBlur !== undefined) ctx.shadowBlur = params.shadowBlur as number
      if (params.shadowColor !== undefined) ctx.shadowColor = params.shadowColor as string
      if (params.shadowOffsetX !== undefined) ctx.shadowOffsetX = params.shadowOffsetX as number
      if (params.shadowOffsetY !== undefined) ctx.shadowOffsetY = params.shadowOffsetY as number
      // 线条虚线
      if (params.lineDash !== undefined) ctx.setLineDash(params.lineDash as number[])
      if (params.lineDashOffset !== undefined) ctx.lineDashOffset = params.lineDashOffset as number
      // 也支持 style 对象中的值
      if (params.style && typeof params.style === 'object') {
        const style = params.style as { fill?: string; fillStyle?: string; stroke?: string; strokeStyle?: string; lineWidth?: number; font?: string }
        if (style?.fill) ctx.fillStyle = style.fill
        if (style?.fillStyle) ctx.fillStyle = style.fillStyle
        if (style?.stroke) ctx.strokeStyle = style.stroke
        if (style?.strokeStyle) ctx.strokeStyle = style.strokeStyle
        if (style?.lineWidth) ctx.lineWidth = style.lineWidth
        if (style?.font) ctx.font = style.font
      }
      break

    // ========== 变形操作 ==========
    case 'translate':
      ctx.translate((params.x as number) ?? 0, (params.y as number) ?? 0)
      break

    case 'rotate':
      ctx.rotate((params.angle as number) ?? 0)
      break

    case 'scale':
      ctx.scale((params.x as number) ?? 1, (params.y as number) ?? 1)
      break

    case 'transform':
      ctx.transform(
        (params.a as number) ?? 1,
        (params.b as number) ?? 0,
        (params.c as number) ?? 0,
        (params.d as number) ?? 1,
        (params.e as number) ?? 0,
        (params.f as number) ?? 0
      )
      break

    case 'setTransform':
      if (params.matrix !== undefined) {
        const m = params.matrix as number[]
        ctx.setTransform(m[0] ?? 1, m[1] ?? 0, m[2] ?? 0, m[3] ?? 1, m[4] ?? 0, m[5] ?? 0)
      } else {
        ctx.setTransform(
          (params.a as number) ?? 1,
          (params.b as number) ?? 0,
          (params.c as number) ?? 0,
          (params.d as number) ?? 1,
          (params.e as number) ?? 0,
          (params.f as number) ?? 0
        )
      }
      break

    case 'resetTransform':
      ctx.resetTransform()
      break

    // ========== 状态保存/恢复 ==========
    case 'save':
      ctx.save()
      break

    case 'restore':
      ctx.restore()
      break

    default:
      console.warn(`未知的 Canvas 操作类型: ${opType}`)
  }
}

/**
 * 边界框格式
 */
interface YoloBox {
  x: number       // 左上角 x 坐标比例 (0-1)
  y: number       // 左上角 y 坐标比例 (0-1)
  width: number   // 宽度比例 (0-1)
  height: number  // 高度比例 (0-1)
  label?: string
  color?: string
  confidence?: number
}

/**
 * 执行 YOLO 绘图
 * 在用户上传的最后一张图片上绘制边界框
 */
function executeYoloDraw(
  boxes: Array<Record<string, unknown>>,
  defaultColor?: string,
  lineWidth?: number,
  fontSize?: number,
  showConfidence?: boolean
): object {
  const imageStore = useImageStore()
  const canvasStore = useCanvasStore()

  // 先从消息列表查找最新图片，再从 imageStore 查找
  let latestImage = getLatestImageFromMessages()
  if (!latestImage) {
    const storeImage = imageStore.getLatestImage()
    if (storeImage) {
      latestImage = { dataUrl: storeImage.dataUrl, id: storeImage.id }
    }
  }

  if (!latestImage) {
    throw new Error('没有找到用户上传的图片。请先上传一张图片后再使用 yolo_draw。')
  }

  const boxesArray = Array.isArray(boxes) ? boxes : []

  // 允许空 boxes - 表示没有检测到任何对象
  if (boxesArray.length === 0) {
    return {
      success: true,
      canvasId: null,
      width: 0,
      height: 0,
      boxCount: 0,
      message: '没有检测到任何目标对象',
      sourceImage: latestImage.id
    }
  }

  // 转换为 YoloBox 格式并验证
  const validBoxes: YoloBox[] = boxesArray.map(box => ({
    x: typeof box.x === 'number' ? box.x : 0,
    y: typeof box.y === 'number' ? box.y : 0,
    width: typeof box.width === 'number' ? box.width : 0.1,
    height: typeof box.height === 'number' ? box.height : 0.1,
    label: typeof box.label === 'string' ? box.label : undefined,
    color: typeof box.color === 'string' ? box.color : undefined,
    confidence: typeof box.confidence === 'number' ? box.confidence : undefined
  }))

  // 创建 Canvas 并加载图片
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    throw new Error('无法创建 Canvas 上下文')
  }

  // 加载图片并绘制
  const img = new Image()
  img.crossOrigin = 'anonymous'

  // 设置默认样式
  const boxColor = defaultColor || '#ff0000'
  const boxLineWidth = lineWidth || 2
  const labelFontSize = fontSize || 14
  const showConf = showConfidence !== false // 默认显示

  return new Promise((resolve, reject) => {
    img.onload = () => {
      // 设置 Canvas 尺寸与图片相同
      canvas.width = img.width
      canvas.height = img.height

      // 先绘制原图
      ctx.drawImage(img, 0, 0)

      // 设置绘图样式
      ctx.lineWidth = boxLineWidth
      ctx.font = `${labelFontSize}px Arial`
      ctx.textBaseline = 'top'

      // 绘制每个边界框
      for (const box of validBoxes) {
        // 将比例坐标转换为像素坐标
        // 格式: x,y 为左上角坐标比例，width,height 为宽高比例
        const left = box.x * canvas.width
        const top = box.y * canvas.height
        const boxWidth = box.width * canvas.width
        const boxHeight = box.height * canvas.height

        // 获取框的颜色
        const color = box.color || boxColor

        // 绘制边界框
        ctx.strokeStyle = color
        ctx.strokeRect(left, top, boxWidth, boxHeight)

        // 绘制标签背景和文字
        if (box.label || (showConf && box.confidence !== undefined)) {
          const labelText = box.label || ''
          const confText = showConf && box.confidence !== undefined
            ? ` ${(box.confidence * 100).toFixed(0)}%`
            : ''
          const fullText = labelText + confText

          // 计算文字宽度
          const textWidth = ctx.measureText(fullText).width

          // 绘制标签背景
          ctx.fillStyle = color
          ctx.fillRect(left, top - labelFontSize - 4, textWidth + 8, labelFontSize + 4)

          // 绘制标签文字（白色）
          ctx.fillStyle = '#ffffff'
          ctx.fillText(fullText, left + 4, top - labelFontSize - 2)
        }
      }

      // 获取绘制后的图片数据
      const dataUrl = canvas.toDataURL('image/png')
      const canvasId = `yolo_${Date.now()}`

      // 保存到 canvas store（用于页面显示）
      canvasStore.addCanvas({
        id: canvasId,
        width: canvas.width,
        height: canvas.height,
        dataUrl,
        createdAt: Date.now()
      })

      // 返回成功结果（不回传给 AI）
      resolve({
        success: true,
        canvasId,
        width: canvas.width,
        height: canvas.height,
        boxCount: boxesArray.length,
        message: `YOLO 绘图完成，共绘制 ${boxesArray.length} 个边界框，结果已显示在页面上`,
        sourceImage: latestImage.id
      })
    }

    img.onerror = () => {
      reject(new Error('无法加载图片，请检查图片格式'))
    }

    // 设置图片源
    img.src = latestImage.dataUrl
  })
}
