/**
 * 工具执行器
 * 执行内置工具和自定义工具并返回结果
 */

import type { ToolCallResult, ToolDefinition } from '@/types/tool'
import { useToolsStore } from '@/stores/tools'

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

    case 'execute_javascript':
      return executeJavaScript(args.code as string)

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
        args.selector as string | undefined
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
function executeJavaScript(code: string): unknown {
  try {
    // 支持执行完整的语句块，代码中需要使用 return 返回结果
    const safeEval = new Function(`
      "use strict";
      ${code}
    `)
    return safeEval()
  } catch (error) {
    throw new Error(`JavaScript 执行错误: ${error instanceof Error ? error.message : String(error)}`)
  }
}

/**
 * 网页搜索 (使用 SerpAPI)
 */
async function webSearch(
  query: string,
  location?: string,
  hl?: string,
  gl?: string
): Promise<object> {
  const params = new URLSearchParams({
    q: query,
    location: location || 'Austin, Texas, United States',
    hl: hl || 'en',
    gl: gl || 'us',
    google_domain: 'google.com'
  })

  const url = `https://serpapi.com/search.json?${params.toString()}`

  try {
    const response = await fetch(
      `https://corsproxy.io/?${encodeURIComponent(url)}`
    )

    if (!response.ok) {
      throw new Error(`搜索请求失败: ${response.status}`)
    }

    const data = await response.json()

    // 提取有机搜索结果
    const results = (data.organic_results || []).map((item: {
      title: string
      snippet: string
      link: string
    }) => ({
      title: item.title,
      snippet: item.snippet || '',
      url: item.link
    }))

    return {
      query,
      location: location || 'Austin, Texas, United States',
      total_results: data.search_information?.total_results || results.length,
      results: results.slice(0, 10)
    }
  } catch (error) {
    throw new Error(`搜索失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

/**
 * 获取网页内容
 */
async function fetchWebpage(url: string, selector?: string): Promise<object> {
  try {
    // 使用 CORS 代理
    const proxyUrl = `https://corsproxy.io/?${encodeURIComponent(url)}`
    const response = await fetch(proxyUrl)

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    const html = await response.text()

    // 如果指定了选择器，尝试提取内容
    if (selector) {
      const parser = new DOMParser()
      const doc = parser.parseFromString(html, 'text/html')
      const elements = doc.querySelectorAll(selector)
      const contents = Array.from(elements).map(el => ({
        text: el.textContent?.trim() || '',
        html: el.innerHTML
      }))

      return {
        url,
        selector,
        matched: contents.length,
        contents
      }
    }

    // 提取页面标题和主要内容
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, 'text/html')
    const title = doc.querySelector('title')?.textContent || ''
    const description = doc.querySelector('meta[name="description"]')?.getAttribute('content') || ''

    // 获取 body 文本内容（去除脚本和样式）
    const body = doc.body
    const scripts = body.querySelectorAll('script, style, nav, footer, header')
    scripts.forEach(el => el.remove())
    const textContent = body.textContent?.replace(/\s+/g, ' ').trim().slice(0, 5000) || ''

    return {
      url,
      title,
      description,
      textContent,
      htmlLength: html.length
    }
  } catch (error) {
    throw new Error(`获取网页失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}