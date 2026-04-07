/**
 * 消息内容解析工具
 * 用于解析 Think/Reasoning 内容和普通文本
 */

interface ParsedContent {
  textContent: string    // 非 Think 内容
  thinkContent: string   // Think 内容
  hasThink: boolean
}

interface StreamingParsedContent {
  text: string
  think: string
  inThinkBlock: boolean
}

/**
 * 解析消息中的 Think 内容
 */
export function parseMessageContent(content: string): ParsedContent {
  if (!content) {
    return { textContent: '', thinkContent: '', hasThink: false }
  }

  // 检查是否包含 think 标签
  const thinkStartTag = '<think>'
  const thinkEndTag = '</think>'
  
  if (!content.includes(thinkStartTag)) {
    return { textContent: content, thinkContent: '', hasThink: false }
  }

  let thinkContent = ''
  let textContent = ''
  let lastIndex = 0
  let hasThink = false

  // 循环查找所有的 think 块
  let startIndex = content.indexOf(thinkStartTag)
  while (startIndex !== -1) {
    // 将上一个块结束到当前 think 开始之间的内容添加到普通文本
    textContent += content.slice(lastIndex, startIndex)
    
    const endSearchIndex = startIndex + thinkStartTag.length
    let endIndex = content.indexOf(thinkEndTag, endSearchIndex)
    
    if (endIndex !== -1) {
      // 找到了结束标签
      thinkContent += content.slice(endSearchIndex, endIndex).trim() + '\n'
      lastIndex = endIndex + thinkEndTag.length
      hasThink = true
    } else {
      // 没找到结束标签，将剩余所有内容视为 think 内容
      thinkContent += content.slice(endSearchIndex).trim()
      lastIndex = content.length
      hasThink = true
      break
    }
    
    startIndex = content.indexOf(thinkStartTag, lastIndex)
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
 * 实时解析正在生成的内容
 */
export function parseStreamingThinkContent(content: string): StreamingParsedContent {
  if (!content) {
    return { text: '', think: '', inThinkBlock: false }
  }

  let thinkContent = ''
  let textContent = ''
  let inThinkBlock = false

  // 简单的状态机解析 - 逐个字符检查标签
  for (let i = 0; i < content.length; i++) {
    const remaining = content.slice(i)

    // 检查是否进入 think 块
    if (!inThinkBlock) {
      // 检查各种开始标签
      let tagLength = 0

      // <think> (7 chars)
      if (remaining.toLowerCase().startsWith('<think>')) {
        tagLength = 7
      }
      // <|begin_of_thought|> (20 chars)
      else if (remaining.toLowerCase().startsWith('<|begin_of_thought|>')) {
        tagLength = 20
      }
      // <reasoning> (11 chars)
      else if (remaining.toLowerCase().startsWith('<reasoning>')) {
        tagLength = 11
      }

      if (tagLength > 0) {
        inThinkBlock = true
        i += tagLength - 1 // -1 because loop will increment
        continue
      }

      // 不在 think 块内，添加到普通文本
      textContent += content[i]
    } else {
      // 在 think 块内，检查结束标签
      let tagLength = 0

      // </think> (8 chars)
      if (remaining.toLowerCase().startsWith('</think>')) {
        tagLength = 8
      }
      // <|end_of_thought|> (18 chars)
      else if (remaining.toLowerCase().startsWith('<|end_of_thought|>')) {
        tagLength = 18
      }
      // </reasoning> (12 chars)
      else if (remaining.toLowerCase().startsWith('</reasoning>')) {
        tagLength = 12
      }

      if (tagLength > 0) {
        inThinkBlock = false
        i += tagLength - 1 // -1 because loop will increment
        continue
      }

      // 仍在 think 块内，添加到思考内容
      thinkContent += content[i]
    }
  }

  return {
    text: textContent,
    think: thinkContent,
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
