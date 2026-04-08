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
 */
export function parseMessageContent(content: string): {
  textContent: string
  thinkContent: string
  hasThink: boolean
} {
  if (!content) {
    return { textContent: '', thinkContent: '', hasThink: false }
  }

  if (!content.includes(THINK_START_TAG)) {
    return { textContent: content, thinkContent: '', hasThink: false }
  }

  let thinkContent = ''
  let textContent = ''
  let lastIndex = 0
  let hasThink = false

  // 循环查找所有的 think 块
  let startIndex = content.indexOf(THINK_START_TAG)
  while (startIndex !== -1) {
    // 将上一个块结束到当前 think 开始之间的内容添加到普通文本
    textContent += content.slice(lastIndex, startIndex)

    const endSearchIndex = startIndex + THINK_START_TAG.length
    let endIndex = content.indexOf(THINK_END_TAG, endSearchIndex)

    if (endIndex !== -1) {
      // 找到了结束标签
      thinkContent += content.slice(endSearchIndex, endIndex).trim() + '\n'
      lastIndex = endIndex + THINK_END_TAG.length
      hasThink = true
    } else {
      // 没找到结束标签，将剩余所有内容视为 think 内容
      thinkContent += content.slice(endSearchIndex).trim()
      lastIndex = content.length
      hasThink = true
      break
    }

    startIndex = content.indexOf(THINK_START_TAG, lastIndex)
  }

  // 添加最后剩余的普通文本
  if (lastIndex < content.length) {
    textContent += content.slice(lastIndex)
  }

  return {
    textContent: textContent.trim(),
    thinkContent: thinkContent.trim(),
    hasThink: hasThink
  }
}

/**
 * 流式解析 Think 内容
 * 优化版本：使用 indexOf 替代逐字符遍历
 */
export function parseStreamingThinkContent(content: string): StreamingParsedContent {
  if (!content) {
    return { text: '', think: '', inThinkBlock: false }
  }

  const thinkStartTags = ['<think>', '<|begin_of_thought|>', '<reasoning>']
  const thinkEndTags = ['</think>', '<|end_of_thought|>', '</reasoning>']

  let textContent = ''
  let thinkContent = ''
  let inThinkBlock = false
  let pos = 0

  while (pos < content.length) {
    if (!inThinkBlock) {
      // Look for any think start tag
      let foundStart = -1
      let startTagLen = 0

      for (let i = 0; i < thinkStartTags.length; i++) {
        const idx = content.indexOf(thinkStartTags[i], pos)
        if (idx !== -1 && (foundStart === -1 || idx < foundStart)) {
          foundStart = idx
          startTagLen = thinkStartTags[i].length
        }
      }

      if (foundStart !== -1) {
        // Add text before the tag
        textContent += content.slice(pos, foundStart)
        pos = foundStart + startTagLen
        inThinkBlock = true
      } else {
        // No more think tags, add rest as text
        textContent += content.slice(pos)
        break
      }
    } else {
      // Look for any think end tag
      let foundEnd = -1
      let endTagLen = 0

      for (let i = 0; i < thinkEndTags.length; i++) {
        const idx = content.indexOf(thinkEndTags[i], pos)
        if (idx !== -1 && (foundEnd === -1 || idx < foundEnd)) {
          foundEnd = idx
          endTagLen = thinkEndTags[i].length
        }
      }

      if (foundEnd !== -1) {
        // Add think content
        thinkContent += content.slice(pos, foundEnd)
        pos = foundEnd + endTagLen
        inThinkBlock = false
      } else {
        // No end tag found, rest is think content
        thinkContent += content.slice(pos)
        break
      }
    }
  }

  return {
    text: textContent.trim(),
    think: thinkContent.trim(),
    inThinkBlock
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