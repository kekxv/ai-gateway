<template>
  <div class="markdown-content" v-html="renderedContent"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

const props = defineProps<{
  content: string
}>()

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true
})

// 自定义渲染器
const renderer = new marked.Renderer()

// 代码块渲染
renderer.code = function({ text, lang }) {
  const language = lang || ''
  const highlighted = language && hljs.getLanguage(language)
    ? hljs.highlight(text, { language }).value
    : hljs.highlightAuto(text).value

  return `<div class="code-block">
    <div class="code-header">
      <span class="code-lang">${language || 'code'}</span>
      <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-block').querySelector('code').textContent)">复制</button>
    </div>
    <pre><code class="hljs ${language ? 'language-' + language : ''}">${highlighted}</code></pre>
  </div>`
}

// 链接渲染 - 在新标签页打开
renderer.link = function({ href, text }) {
  return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`
}

marked.use({ renderer })

const renderedContent = computed(() => {
  if (!props.content) return ''
  try {
    return marked.parse(props.content) as string
  } catch {
    return props.content
  }
})
</script>

<style>
.markdown-content {
  line-height: 1.7;
  word-break: break-word;
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

/* 代码块样式 */
.markdown-content .code-block {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  background: #1e293b;
}

.markdown-content .code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #334155;
  color: #94a3b8;
  font-size: 12px;
}

.markdown-content .copy-btn {
  padding: 2px 8px;
  background: #475569;
  color: #e2e8f0;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.markdown-content .copy-btn:hover {
  background: #64748b;
}

.markdown-content pre {
  margin: 0;
  padding: 16px;
  overflow-x: auto;
}

.markdown-content code {
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.5;
}

.markdown-content :not(pre) > code {
  padding: 2px 6px;
  background: #f1f5f9;
  border-radius: 4px;
  color: #e11d48;
  font-size: 0.9em;
}

/* Highlight.js 主题调整 */
.markdown-content .hljs {
  background: transparent;
  color: #e2e8f0;
}

.markdown-content .hljs-keyword { color: #f472b6; }
.markdown-content .hljs-string { color: #a5f3fc; }
.markdown-content .hljs-number { color: #fbbf24; }
.markdown-content .hljs-function { color: #a78bfa; }
.markdown-content .hljs-comment { color: #64748b; }
.markdown-content .hljs-variable { color: #94a3b8; }
</style>