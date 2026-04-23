<template>
  <div class="code-block-wrapper" :class="{ 'is-collapsed': !isExpanded }">
    <div class="code-header" @click="toggleExpand">
      <el-icon class="collapse-icon">
        <ArrowDown v-if="isExpanded" />
        <ArrowRight v-else />
      </el-icon>
      <span class="code-lang">{{ language || 'code' }}</span>
      <span v-if="lineCount" class="code-meta">{{ lineCount }} 行</span>
      <button class="copy-btn" @click.stop="copyCode" title="复制代码">
        <el-icon><DocumentCopy /></el-icon>
      </button>
    </div>
    <div class="code-content">
      <pre><code :class="`hljs ${language ? 'language-' + language : ''}`" v-html="highlightedCode"></code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowDown, ArrowRight, DocumentCopy } from '@element-plus/icons-vue'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import diff from 'highlight.js/lib/languages/diff'
import go from 'highlight.js/lib/languages/go'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import php from 'highlight.js/lib/languages/php'
import plaintext from 'highlight.js/lib/languages/plaintext'
import python from 'highlight.js/lib/languages/python'
import rust from 'highlight.js/lib/languages/rust'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import { ElMessage } from '@/plugins/element-plus-services'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('diff', diff)
hljs.registerLanguage('go', go)
hljs.registerLanguage('golang', go)
hljs.registerLanguage('java', java)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('php', php)
hljs.registerLanguage('plaintext', plaintext)
hljs.registerLanguage('text', plaintext)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('rs', rust)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('vue', xml)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)

const props = defineProps<{
  code: string
  language?: string
  defaultCollapsed?: boolean
}>()

const isExpanded = ref(!props.defaultCollapsed)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const highlightedCode = computed(() => {
  if (!props.code) return ''
  if (props.language && hljs.getLanguage(props.language)) {
    return hljs.highlight(props.code, { language: props.language }).value
  }
  return hljs.highlightAuto(props.code).value
})

const lineCount = computed(() => {
  if (!props.code) return 0
  return props.code.split('\n').length
})

const copyCode = async () => {
  try {
    await navigator.clipboard.writeText(props.code)
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.code-block-wrapper {
	margin: 12px 0;
	border-radius: 12px;
	overflow: hidden;
	background: #f8fafc;
	border: 1px solid rgba(102, 126, 234, 0.2);
	width: 100%;
	box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
}

.code-header {
	display: flex;
	align-items: center;
	padding: 10px 14px;
	background: linear-gradient(90deg, #f3f4f6 0%, #e5e7eb 100%);
	color: #6b7280;
	font-size: 12px;
	cursor: pointer;
	user-select: none;
	transition: background 0.2s;
}

.code-header:hover {
	background: linear-gradient(90deg, #e5e7eb 0%, #d1d5db 100%);
}

.collapse-icon {
	margin-right: 8px;
	color: #6b7280;
	transition: transform 0.2s;
}

.code-lang {
	font-weight: 600;
	color: #374151;
	letter-spacing: 0.02em;
}

.code-meta {
	margin-left: 10px;
	color: #9ca3af;
	font-size: 11px;
}

.copy-btn {
	margin-left: auto;
	padding: 6px 10px;
	background: rgba(102, 126, 234, 0.1);
	color: #667eea;
	border: none;
	border-radius: 6px;
	cursor: pointer;
	display: flex;
	align-items: center;
	justify-content: center;
	transition: all 0.2s;
}

.copy-btn:hover {
	background: rgba(102, 126, 234, 0.2);
	color: #5a67d8;
}

.code-content {
	max-height: 500px;
	overflow-y: auto;
	transition: max-height 0.3s ease;
}

/* 折叠时用 max-height 控制，保持宽度 */
.is-collapsed .code-content {
	max-height: 0;
	overflow: hidden;
}

.code-content pre {
	margin: 0;
	padding: 16px;
	overflow-x: auto;
}

.code-content code {
	font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
	font-size: 14px;
	line-height: 1.6;
}

/* Highlight.js theme - light theme */
.code-content .hljs {
	background: transparent;
	color: #374151;
}

.code-content .hljs-keyword { color: #d73a49; }
.code-content .hljs-string { color: #032f62; }
.code-content .hljs-number { color: #005cc5; }
.code-content .hljs-function { color: #6f42c1; }
.code-content .hljs-comment { color: #6a737d; font-style: italic; }
.code-content .hljs-variable { color: #e36209; }
.code-content .hljs-title { color: #6f42c1; }
.code-content .hljs-params { color: #24292e; }
.code-content .hljs-built_in { color: #005cc5; }
.code-content .hljs-class { color: #d73a49; }
.code-content .hljs-property { color: #005cc5; }
</style>
