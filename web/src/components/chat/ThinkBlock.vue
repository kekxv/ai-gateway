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
import 'highlight.js/styles/github.css'

const props = defineProps<{
  content: string
  tokens?: number
  defaultCollapsed?: boolean
  forceExpand?: boolean // New prop to force expansion
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
  return marked.parse(props.content, {
    breaks: true,
    gfm: true
  })
})
</script>

<style scoped>
.think-block {
  margin: 8px 0 12px 0;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  overflow: hidden;
}

.think-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.think-header:hover {
  background: rgba(99, 102, 241, 0.1);
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
}

.think-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.think-label {
  font-size: 13px;
  font-weight: 500;
  color: #4f46e5;
}

.think-tokens {
  font-size: 11px;
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.expand-icon {
  color: #6366f1;
  transition: transform 0.2s;
}

.think-content {
  padding: 12px 16px;
  border-top: 1px solid #c7d2fe;
  background: rgba(255, 255, 255, 0.5);
}

.think-markdown {
  font-size: 13px;
  line-height: 1.6;
  color: #3730a3;
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
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
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