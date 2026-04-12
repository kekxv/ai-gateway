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
import hljs from 'highlight.js'
import { ElMessage } from 'element-plus'

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
  border-radius: 8px;
  overflow: hidden;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  width: 100%;
}

.code-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.code-header:hover {
  background: #e5e7eb;
}

.collapse-icon {
  margin-right: 6px;
  color: #6b7280;
}

.code-lang {
  font-weight: 500;
  color: #374151;
}

.code-meta {
  margin-left: 8px;
  color: #9ca3af;
  font-size: 11px;
}

.copy-btn {
  margin-left: auto;
  padding: 4px 8px;
  background: #e5e7eb;
  color: #374151;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.copy-btn:hover {
  background: #d1d5db;
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
  line-height: 1.5;
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
.code-content .hljs-comment { color: #6a737d; }
.code-content .hljs-variable { color: #e36209; }
.code-content .hljs-title { color: #6f42c1; }
.code-content .hljs-params { color: #24292e; }
.code-content .hljs-built_in { color: #005cc5; }
</style>