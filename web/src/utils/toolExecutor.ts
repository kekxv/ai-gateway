/**
 * 工具执行器
 * 执行内置工具和自定义工具并返回结果
 */

import type { ToolCallResult, ToolDefinition } from '@/types/tool'
import { useToolsStore } from '@/stores/tools'
import { useAuthStore } from '@/stores/auth'
import { useCanvasStore } from '@/stores/canvas'

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
 */
interface CanvasOperation {
  type?: string
  [key: string]: unknown
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
  for (const op of operations) {
    try {
      executeCanvasOperation(ctx, op)
      if (op.type) {
        executedOps.push(op.type)
      }
    } catch (err) {
      console.warn(`Canvas 操作执行失败: ${op.type}`, err)
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

  // 只返回成功状态，图片已在页面上显示
  return {
    success: true,
    message: `绘图完成，共执行 ${executedOps.length} 个操作，图片已在页面上显示`
  }
}

/**
 * 执行单个绑绑定绘图操作
 */
function executeCanvasOperation(ctx: CanvasRenderingContext2D, op: CanvasOperation) {
  const { type, ...params } = op

  if (!type) return

  switch (type) {
    case 'clear':
      ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height)
      break

    case 'fill':
      // 填充整个画布或指定区域
      ctx.fillStyle = (params.color as string) || (params.fillStyle as string) || '#000000'
      ctx.fillRect(
        (params.x as number) ?? 0,
        (params.y as number) ?? 0,
        (params.width as number) ?? ctx.canvas.width,
        (params.height as number) ?? ctx.canvas.height
      )
      break

    case 'stroke':
      ctx.strokeStyle = (params.color as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
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
      const startAngle = (params.startAngle as number) ?? 0
      const endAngle = (params.endAngle as number) ?? Math.PI * 2

      ctx.beginPath()
      ctx.arc(cx, cy, radius, startAngle, endAngle)

      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || (params.fillStyle as string) || '#000000'
        ctx.fill()
      }
      // 默认描边（除非只有填充）
      if (params.stroke === true || (params.stroke !== false && params.fill !== true)) {
        ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
        ctx.lineWidth = (params.lineWidth as number) ?? 1
        ctx.stroke()
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
      if (params.fill === true) {
        ctx.fillStyle = (params.fillColor as string) || '#000000'
        ctx.fill()
      }
      ctx.strokeStyle = (params.strokeColor as string) || (params.strokeStyle as string) || '#000000'
      ctx.lineWidth = (params.lineWidth as number) ?? 1
      ctx.stroke()
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

    case 'polyline':
    case 'polygon': {
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

    case 'text':
      ctx.font = (params.font as string) || '16px Arial'
      ctx.fillStyle = (params.color as string) || (params.fillStyle as string) || '#000000'
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

    case 'bezier':
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
      console.warn(`未知的 Canvas 操作类型: ${type}`)
  }
}
