<template>
  <div class="think-block" :class="{ 'is-expanded': isExpanded }">
    <div class="think-header" @click="toggleExpand">
      <div class="think-icon">
        <el-icon><Cpu /></el-icon>
      </div>
      <div class="think-meta">
        <span class="think-label">思考过程</span>
        <span v-if="tokens" class="think-tokens">~{{ tokens }} tokens</span>
      </div>
      <el-icon class="expand-icon">
        <ArrowDown v-if="!isExpanded" />
        <ArrowUp v-else />
      </el-icon>
    </div>
    <div v-show="isExpanded" class="think-content">
      <div class="think-markdown" v-html="renderedContent"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Cpu, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import { marked } from 'marked'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'

// 标准 HTML 标签白名单（不需要转义）
const STANDARD_HTML_TAGS = new Set([
  'a', 'abbr', 'acronym', 'address', 'article', 'aside', 'audio', 'b', 'bdi', 'bdo',
  'big', 'blockquote', 'body', 'br', 'button', 'canvas', 'caption', 'center', 'cite',
  'code', 'col', 'colgroup', 'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog',
  'div', 'dl', 'dt', 'em', 'embed', 'fieldset', 'figure', 'font', 'footer', 'form',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html', 'i', 'iframe',
  'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'link', 'main', 'map', 'mark',
  'meta', 'meter', 'nav', 'noscript', 'object', 'ol', 'optgroup', 'option', 'output',
  'p', 'param', 'picture', 'pre', 'progress', 'q', 'rp', 'rt', 'ruby', 's', 'samp',
  'script', 'section', 'select', 'small', 'source', 'span', 'strike', 'strong', 'style',
  'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'template', 'textarea', 'tfoot',
  'th', 'thead', 'time', 'title', 'tr', 'track', 'tt', 'u', 'ul', 'var', 'video', 'wbr',
  // SVG 标签
  'svg', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text', 'g'
])

/**
 * 转义伪 HTML 标签（非标准标签如 `段落`）
 */
const escapePseudoHtmlTags = (content: string): string => {
  return content.replace(/<\/?([a-zA-Z][a-zA-Z0-9_-]*)[^>]*>/g, (match, tagName) => {
    const lowerTagName = tagName.toLowerCase()
    if (STANDARD_HTML_TAGS.has(lowerTagName)) {
      return match
    }
    return match.replace(/</g, '&lt;').replace(/>/g, '&gt;')
  })
}

/**
 * 渲染 LaTeX 公式
 */
const renderLatex = (content: string): string => {
  // 块级公式 $$...$$
  content = content.replace(/\$\$([\s\S]+?)\$\$/g, (match, latex) => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: true,
        throwOnError: false,
        trust: true
      })
    } catch {
      return match
    }
  })

  // 行内公式 $...$
  content = content.replace(/\$([^\$\n]+?)\$/g, (match, latex) => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: false,
        throwOnError: false,
        trust: true
      })
    } catch {
      return match
    }
  })

  return content
}

const props = defineProps<{
  content: string
  tokens?: number
  defaultCollapsed?: boolean
  forceExpand?: boolean
}>()

const isExpanded = ref(props.forceExpand || !props.defaultCollapsed)

// Watch for forceExpand changes
watch(() => props.forceExpand, (newVal) => {
  if (newVal) {
    isExpanded.value = true
  } else if (props.defaultCollapsed) {
    // If we're no longer forcing expansion and the default is collapsed,
    // collapse it (e.g. when content or tools appear)
    isExpanded.value = false
  }
}, { immediate: true })

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

// Render markdown content
const renderedContent = computed(() => {
  if (!props.content) return ''
  return marked.parse(renderLatex(escapePseudoHtmlTags(props.content)), {
    breaks: true,
    gfm: true
  })
})
</script>

<style scoped>
.think-block {
	margin: 8px 0 12px 0;
	border: 1px solid rgba(99, 102, 241, 0.2);
	border-radius: 12px;
	background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
	overflow: hidden;
	box-shadow: 0 2px 8px rgba(99, 102, 241, 0.08);
}

.think-header {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 12px 14px;
	cursor: pointer;
	user-select: none;
	transition: background 0.2s;
}

.think-header:hover {
	background: rgba(99, 102, 241, 0.12);
}

.think-icon {
	width: 28px;
	height: 28px;
	border-radius: 50%;
	background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
	color: white;
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);
}

.think-meta {
	flex: 1;
	display: flex;
	align-items: center;
	gap: 10px;
}

.think-label {
	font-size: 13px;
	font-weight: 600;
	color: #4f46e5;
}

.think-tokens {
	font-size: 11px;
	color: #7c3aed;
	background: rgba(124, 58, 237, 0.15);
	padding: 3px 8px;
	border-radius: 6px;
	font-weight: 500;
}

.expand-icon {
	color: #6366f1;
	transition: transform 0.2s;
}

.think-content {
	padding: 14px 16px;
	border-top: 1px solid rgba(199, 210, 254, 0.5);
	background: rgba(255, 255, 255, 0.6);
}

.think-markdown {
	font-size: 13px;
	line-height: 1.6;
	color: #3730a3;
	overflow-wrap: anywhere;
}

.think-markdown :deep(p) {
	margin: 0.5em 0;
}

.think-markdown :deep(code) {
	background: rgba(0, 0, 0, 0.06);
	padding: 2px 6px;
	border-radius: 4px;
	font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
	font-size: 12px;
}

.think-markdown :deep(pre) {
	background: #f6f8fa;
	padding: 12px;
	border-radius: 8px;
	overflow-x: auto;
	margin: 8px 0;
	border: 1px solid rgba(99, 102, 241, 0.1);
}

.think-markdown :deep(pre code) {
	background: transparent;
	padding: 0;
}

.think-markdown :deep(ul),
.think-markdown :deep(ol) {
	padding-left: 20px;
	margin: 0.5em 0;
}

.think-markdown :deep(li) {
	margin: 4px 0;
}

.think-markdown :deep(blockquote) {
	border-left: 3px solid #c7d2fe;
	padding-left: 12px;
	margin: 8px 0;
	color: #6b7280;
}
</style>