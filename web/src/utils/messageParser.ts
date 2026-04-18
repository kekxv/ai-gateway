import type { ToolCall } from '@/types/tool'

// Think tags
const THINK_START_TAG = '<think>'
const THINK_END_TAG = '</think>'

// Streaming parsed content
export interface StreamingParsedContent {
  text: string
  think: string
  inThinkBlock: boolean
}

/**
 * 解析消息内容，提取 Think 块
 * 只有开头的 think 标签才会被识别为思考内容，中间的不算
 */
export function parseMessageContent(content: string): {
  textContent: string
  thinkContent: string
  hasThink: boolean
} {
  if (!content) {
    return { textContent: '', thinkContent: '', hasThink: false }
  }

  // 查找第一个 think start 标签的位置
  const startIndex = content.indexOf(THINK_START_TAG)
  if (startIndex === -1) {
    return { textContent: content, thinkContent: '', hasThink: false }
  }

  // 检查 think 标签是否在开头（前面只有空白字符）
  const beforeThink = content.slice(0, startIndex)
  if (beforeThink.trim() !== '') {
    // think 标签不在开头，把整个内容当作普通文本
    return { textContent: content, thinkContent: '', hasThink: false }
  }

  // think 标签在开头，提取 think 内容
  const endSearchIndex = startIndex + THINK_START_TAG.length
  const endIndex = content.indexOf(THINK_END_TAG, endSearchIndex)

  let thinkContent = ''
  let textContent = ''

  if (endIndex !== -1) {
    // 找到了结束标签
    thinkContent = content.slice(endSearchIndex, endIndex).trim()
    // 结束标签后面的内容作为普通文本（不再解析其他 think 块）
    textContent = content.slice(endIndex + THINK_END_TAG.length).trim()
  } else {
    // 没找到结束标签，将剩余所有内容视为 think 内容
    thinkContent = content.slice(endSearchIndex).trim()
    textContent = ''
  }

  return {
    textContent,
    thinkContent,
    hasThink: thinkContent.length > 0
  }
}

/**
 * 流式解析 Think 内容
 * 只有开头的 think 标签才会被识别为思考内容，中间的不算
 */
export function parseStreamingThinkContent(content: string): StreamingParsedContent {
  if (!content) {
    return { text: '', think: '', inThinkBlock: false }
  }

  const thinkStartTags = ['<think>', '<|begin_of_thought|>', '<reasoning>']
  const thinkEndTags = ['</think>', '<|end_of_thought|>', '</reasoning>']

  // 查找最早的 think start 标签
  let earliestStart = -1
  let startTagLen = 0

  for (let i = 0; i < thinkStartTags.length; i++) {
    const idx = content.indexOf(thinkStartTags[i])
    if (idx !== -1 && (earliestStart === -1 || idx < earliestStart)) {
      earliestStart = idx
      startTagLen = thinkStartTags[i].length
    }
  }

  // 如果没有找到任何 think start 标签，全部作为普通文本
  if (earliestStart === -1) {
    return { text: content, think: '', inThinkBlock: false }
  }

  // 检查 think 标签是否在开头（前面只有空白字符）
  const beforeThink = content.slice(0, earliestStart)
  if (beforeThink.trim() !== '') {
    // think 标签不在开头，把整个内容当作普通文本
    return { text: content, think: '', inThinkBlock: false }
  }

  // think 标签在开头，提取 think 内容
  const thinkStartPos = earliestStart + startTagLen

  // 查找最早的 think end 标签
  let earliestEnd = -1
  let endTagLen = 0

  for (let i = 0; i < thinkEndTags.length; i++) {
    const idx = content.indexOf(thinkEndTags[i], thinkStartPos)
    if (idx !== -1 && (earliestEnd === -1 || idx < earliestEnd)) {
      earliestEnd = idx
      endTagLen = thinkEndTags[i].length
    }
  }

  if (earliestEnd !== -1) {
    // 找到了结束标签
    const thinkContent = content.slice(thinkStartPos, earliestEnd)
    const textContent = content.slice(earliestEnd + endTagLen)
    return {
      text: textContent,
      think: thinkContent,
      inThinkBlock: false
    }
  } else {
    // 没找到结束标签，还在思考块中，后面都是思考内容
    const thinkContent = content.slice(thinkStartPos)
    return {
      text: '',
      think: thinkContent,
      inThinkBlock: true
    }
  }
}

/**
 * 移除 Think 内容
 * 用于发送请求时过滤掉之前的 Think 内容
 */
export function removeThinkContent(content: string): string {
  const { textContent } = parseMessageContent(content)
  return textContent
}

/**
 * 格式化 Think 时间
 */
export function formatThinkTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

/**
 * 估算 Think token 数量
 * 粗略估算：中文约 2 字符/token，英文约 4 字符/token
 */
export function estimateThinkTokens(content: string): number {
  if (!content) return 0
  const chineseChars = (content.match(/[\u4e00-\u9fa5]/g) || []).length
  const otherChars = content.length - chineseChars
  return Math.ceil(chineseChars / 2 + otherChars / 4)
}

/**
 * 解析 XML 格式的 Tool Call（必须在 ``` 标签内）
 * 支持格式：
 * ```
 * <web_canvas>
 * width: 375
 * height: 812
 * operations: [...]
 * ```
 */
export function parseXmlToolCalls(content: string): { toolCalls: ToolCall[]; cleanedContent: string } {
  const toolCalls: ToolCall[] = []
  let cleanedContent = content

  // 匹配 ``` 标签内的内容
  const toolCallPattern = /```([\s\S]*?)```/g

  let match
  while ((match = toolCallPattern.exec(content)) !== null) {
    const innerContent = match[1].trim()

    // 从内部内容提取工具名称和参数
    // 格式：<tool_name>args...</tool_name>
    const innerPattern = /^<([a-z_][a-z0-9_]*)>([\s\S]*)$/i
    const innerMatch = innerContent.match(innerPattern)

    if (innerMatch) {
      const toolName = innerMatch[1]
      const toolContent = innerMatch[2].trim()

      // 跳过 think 相关标签
      if (toolName.toLowerCase().includes('think')) {
        continue
      }

      // 解析参数
      let args: Record<string, unknown> = {}
      if (toolContent.startsWith('{') || toolContent.startsWith('[')) {
        try {
          args = JSON.parse(toolContent)
        } catch {
          args = parseYamlStyleArgs(toolContent)
        }
      } else {
        args = parseYamlStyleArgs(toolContent)
      }

      toolCalls.push({
        id: `xml_tool_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        type: 'function',
        function: {
          name: toolName,
          arguments: JSON.stringify(args)
        }
      })
    }
  }

  // 移除 ``` 标签
  if (toolCalls.length > 0) {
    cleanedContent = content.replace(toolCallPattern, '').trim()
  }

  return { toolCalls, cleanedContent }
}

function parseYamlStyleArgs(content: string): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  const lines = content.split('\n')

  for (const line of lines) {
    const trimmedLine = line.trim()
    if (!trimmedLine || trimmedLine.startsWith('#')) continue

    const colonIndex = trimmedLine.indexOf(':')
    if (colonIndex === -1) continue

    const key = trimmedLine.slice(0, colonIndex).trim()
    let value = trimmedLine.slice(colonIndex + 1).trim()
    args[key] = parseYamlValue(value)
  }

  return args
}

function parseYamlValue(value: string): unknown {
  if (value === '' || value === 'null') return null
  if (value === 'true') return true
  if (value === 'false') return false
  if (!isNaN(Number(value)) && value !== '') {
    const num = Number(value)
    if (Number.isInteger(num) && !value.includes('.')) return num
    return num
  }
  if (value.startsWith('[') || value.startsWith('{')) {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  if ((value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1)
  }
  return value
}