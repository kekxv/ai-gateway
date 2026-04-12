<template>
  <div class="markdown-content">
    <template v-for="(segment, index) in renderedSegments" :key="index">
      <!-- Code block segment - render as Vue component -->
      <CodeBlock
        v-if="segment.type === 'code'"
        :code="segment.code"
        :language="segment.language"
        :default-collapsed="segment.defaultCollapsed"
      />
      <!-- HTML segment - render via v-html -->
      <div v-else-if="segment.type === 'html'" v-html="segment.html"></div>
      <!-- Incomplete segment - show as plain text during streaming -->
      <div v-else-if="segment.type === 'incomplete'" class="incomplete-text">{{ segment.text }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { marked } from 'marked'
import CodeBlock from './CodeBlock.vue'

interface CodeSegment {
  type: 'code'
  code: string
  language: string
  defaultCollapsed: boolean
}

interface HtmlSegment {
  type: 'html'
  html: string
}

interface IncompleteSegment {
  type: 'incomplete'
  text: string
}

type Segment = CodeSegment | HtmlSegment | IncompleteSegment

const props = defineProps<{
  content: string
  streaming?: boolean  // 是否在流式输出中
}>()

// Configure marked
marked.setOptions({
  breaks: true,
  gfm: true
})

// Custom renderer for links - open in new tab
const renderer = new marked.Renderer()

renderer.link = function({ href, text }) {
  return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`
}

// Inline code renderer
renderer.codespan = function({ text }) {
  return `<code>${text}</code>`
}

marked.use({ renderer })

// 缓存已渲染的内容（key是原始文本）
const renderedCache = ref(new Map<string, { type: 'code' | 'html', data: any }>())

// 检测完整代码块的结束位置
const findCompleteCodeBlocks = (content: string): { start: number, end: number, lang: string, code: string }[] => {
  // 只匹配完整的代码块（有开始和结束的 ```）
  const regex = /```(\w*)\n([\s\S]*?)```/g
  const blocks: { start: number, end: number, lang: string, code: string }[] = []
  let match

  while ((match = regex.exec(content)) !== null) {
    blocks.push({
      start: match.index,
      end: match.index + match[0].length,
      lang: match[1] || '',
      code: match[2].trimEnd()
    })
  }

  return blocks
}

// 检测是否有未闭合的代码块，返回其起始位置
const findUnclosedCodeBlock = (content: string): { start: number, lang: string } | null => {
  // 找最后一个 ``` 开始但未闭合的位置
  const lastCodeBlockStart = content.lastIndexOf('```')
  if (lastCodeBlockStart === -1) return null

  // 检查这个 ``` 后面是否有闭合的 ```
  // 需要检查从 lastCodeBlockStart 开始，后面是否有完整的闭合
  const afterStart = content.slice(lastCodeBlockStart)

  // 更精确的判断：从 lastCodeBlockStart 开始，找下一个 ```
  const nextTripleBackticks = afterStart.indexOf('```', 3) // 从 ``` 后面开始找
  if (nextTripleBackticks === -1) {
    // 没有找到闭合的 ```
    const langMatch = afterStart.match(/^```(\w*)\n?/)
    return {
      start: lastCodeBlockStart,
      lang: langMatch ? langMatch[1] || '' : ''
    }
  }

  return null
}

// 增量解析：将内容分为已完成和未完成部分
const parseIncremental = (content: string): Segment[] => {
  if (!content) return []

  const segments: Segment[] = []

  // 1. 先找出所有完整的代码块
  const completeBlocks = findCompleteCodeBlocks(content)

  // 2. 检测是否有未闭合的代码块
  const unclosedBlock = findUnclosedCodeBlock(content)

  // 3. 构建内容区间
  // 已完成区间：从 0 到最后一个完整代码块的结束位置（或未闭合代码块的开始位置）
  let completeEndIndex = content.length

  if (unclosedBlock) {
    // 有未闭合代码块，已完成部分截止到未闭合代码块开始前
    completeEndIndex = unclosedBlock.start
  } else if (completeBlocks.length > 0) {
    // 有完整代码块，检查最后一个完整代码块后面是否还有内容
    // 最后一个完整代码块后的内容也算已完成（因为没有未闭合的代码块）
    completeEndIndex = content.length
  }

  // 4. 解析已完成部分
  let lastIndex = 0

  for (const block of completeBlocks) {
    // 添加代码块之前的HTML内容
    if (block.start > lastIndex && block.start < completeEndIndex) {
      const htmlContent = content.slice(lastIndex, block.start)
      if (htmlContent.trim()) {
        // 检查缓存
        const cached = renderedCache.value.get(htmlContent)
        if (cached && cached.type === 'html') {
          segments.push({ type: 'html', html: cached.data })
        } else {
          const renderedHtml = marked.parse(htmlContent) as string
          if (renderedHtml.trim()) {
            renderedCache.value.set(htmlContent, { type: 'html', data: renderedHtml })
            segments.push({ type: 'html', html: renderedHtml })
          }
        }
      }
    }

    // 添加代码块
    segments.push({
      type: 'code',
      code: block.code,
      language: block.lang,
      defaultCollapsed: false
    })

    lastIndex = block.end
  }

  // 5. 添加最后一个完整代码块之后到 completeEndIndex 之间的HTML内容
  if (lastIndex < completeEndIndex) {
    const htmlContent = content.slice(lastIndex, completeEndIndex)
    if (htmlContent.trim()) {
      const cached = renderedCache.value.get(htmlContent)
      if (cached && cached.type === 'html') {
        segments.push({ type: 'html', html: cached.data })
      } else {
        const renderedHtml = marked.parse(htmlContent) as string
        if (renderedHtml.trim()) {
          renderedCache.value.set(htmlContent, { type: 'html', data: renderedHtml })
          segments.push({ type: 'html', html: renderedHtml })
        }
      }
    }
  }

  // 6. 添加未完成部分（纯文本显示）
  const incompleteContent = content.slice(completeEndIndex)
  if (incompleteContent.trim()) {
    segments.push({ type: 'incomplete', text: incompleteContent })
  }

  return segments
}

// 完整解析：非流式时正常渲染所有内容
const parseComplete = (content: string): Segment[] => {
  const segments: Segment[] = []

  const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g

  let lastIndex = 0
  let match

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add HTML content before this code block
    if (match.index > lastIndex) {
      const htmlContent = content.slice(lastIndex, match.index)
      const renderedHtml = marked.parse(htmlContent) as string
      if (renderedHtml.trim()) {
        segments.push({
          type: 'html',
          html: renderedHtml
        })
      }
    }

    // Add code block segment
    const language = match[1] || ''
    const code = match[2].trimEnd()
    segments.push({
      type: 'code',
      code,
      language,
      defaultCollapsed: false
    })

    lastIndex = match.index + match[0].length
  }

  // Add remaining HTML content after last code block
  if (lastIndex < content.length) {
    const htmlContent = content.slice(lastIndex)
    const renderedHtml = marked.parse(htmlContent) as string
    if (renderedHtml.trim()) {
      segments.push({
        type: 'html',
        html: renderedHtml
      })
    }
  }

  return segments
}

const renderedSegments = computed(() => {
  if (!props.content) return []
  try {
    // 流式输出时使用增量解析，非流式时使用完整解析
    if (props.streaming) {
      return parseIncremental(props.content)
    } else {
      return parseComplete(props.content)
    }
  } catch {
    return [{ type: 'html' as const, html: props.content }]
  }
})

// 当 streaming 变为 false 时，清空缓存（准备下次流式输出）
watch(() => props.streaming, (newVal) => {
  if (newVal === false) {
    renderedCache.value.clear()
  }
})
</script>

<style>
.markdown-content {
  line-height: 1.7;
  word-break: break-word;
}

.markdown-content > div:not(.code-block-wrapper) {
  /* Only apply to non-code-block divs */
}

.markdown-content p {
  margin: 0 0 12px 0;
}

.markdown-content p:last-child {
  margin-bottom: 0;
}

.markdown-content h1,
.markdown-content h2,
.markdown-content h3,
.markdown-content h4,
.markdown-content h5,
.markdown-content h6 {
  margin: 16px 0 8px 0;
  font-weight: 600;
  line-height: 1.4;
}

.markdown-content h1 { font-size: 1.5em; }
.markdown-content h2 { font-size: 1.3em; }
.markdown-content h3 { font-size: 1.15em; }

.markdown-content ul,
.markdown-content ol {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-content li {
  margin: 4px 0;
}

.markdown-content blockquote {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 4px solid #6366f1;
  background: #f8fafc;
  color: #475569;
}

.markdown-content table {
  width: 100%;
  margin: 12px 0;
  border-collapse: collapse;
  font-size: 14px;
}

.markdown-content th,
.markdown-content td {
  border: 1px solid #e5e7eb;
  padding: 8px 12px;
  text-align: left;
}

.markdown-content th {
  background: #f8fafc;
  font-weight: 600;
}

.markdown-content a {
  color: #6366f1;
  text-decoration: none;
}

.markdown-content a:hover {
  text-decoration: underline;
}

/* Inline code style */
.markdown-content :not(pre) > code {
  padding: 2px 6px;
  background: #f1f5f9;
  border-radius: 4px;
  color: #e11d48;
  font-size: 0.9em;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

/* Incomplete text style during streaming */
.incomplete-text {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>