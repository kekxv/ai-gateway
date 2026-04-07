/**
 * 工具执行器
 * 执行内置工具并返回结果
 */

import type { ToolCallResult } from '@/types/tool'

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
    const output = await executeBuiltinTool(toolName, args)
    result.status = 'success'
    result.result = output
  } catch (error) {
    result.status = 'error'
    result.error = error instanceof Error ? error.message : String(error)
  }

  return result
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

    case 'execute_javascript':
      return executeJavaScript(args.code as string)

    case 'web_search':
      return webSearch(args.query as string)

    case 'draw_chart':
      return drawChart(
        args.type as string,
        args.labels as string[],
        args.data as number[],
        args.title as string | undefined
      )

    case 'save_note':
      return saveNote(args.title as string, args.content as string)

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
 * 网页搜索 (模拟)
 */
async function webSearch(query: string): Promise<object> {
  // 这是一个模拟实现，实际项目中可以集成真实的搜索 API
  return {
    query,
    results: [
      {
        title: `搜索结果: ${query}`,
        snippet: `这是关于 "${query}" 的搜索结果摘要。在实际实现中，这里会显示真实的搜索结果。`,
        url: `https://example.com/search?q=${encodeURIComponent(query)}`
      }
    ],
    note: '这是一个模拟的搜索结果。要启用真实搜索，请配置搜索 API。'
  }
}

/**
 * 绘制图表
 */
function drawChart(
  type: string,
  labels: string[],
  data: number[],
  title?: string
): object {
  // 返回图表配置，前端可以根据此配置渲染图表
  return {
    type,
    title: title || 'Chart',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: [
          'rgba(99, 102, 241, 0.8)',
          'rgba(34, 197, 94, 0.8)',
          'rgba(249, 115, 22, 0.8)',
          'rgba(236, 72, 153, 0.8)',
          'rgba(14, 165, 233, 0.8)',
          'rgba(168, 85, 247, 0.8)'
        ]
      }]
    },
    config: {
      responsive: true,
      plugins: {
        title: {
          display: !!title,
          text: title
        }
      }
    }
  }
}

/**
 * 保存笔记
 */
function saveNote(title: string, content: string): object {
  try {
    const notes = JSON.parse(localStorage.getItem('chat_notes') || '[]')
    const note = {
      id: Date.now(),
      title,
      content,
      createdAt: new Date().toISOString()
    }
    notes.push(note)
    localStorage.setItem('chat_notes', JSON.stringify(notes))
    return {
      success: true,
      message: `笔记 "${title}" 已保存`,
      noteId: note.id
    }
  } catch (error) {
    throw new Error(`保存笔记失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

/**
 * 获取所有笔记
 */
export function getNotes(): object[] {
  return JSON.parse(localStorage.getItem('chat_notes') || '[]')
}

/**
 * 删除笔记
 */
export function deleteNote(id: number): boolean {
  try {
    const notes = JSON.parse(localStorage.getItem('chat_notes') || '[]')
    const filtered = notes.filter((n: { id: number }) => n.id !== id)
    localStorage.setItem('chat_notes', JSON.stringify(filtered))
    return true
  } catch {
    return false
  }
}