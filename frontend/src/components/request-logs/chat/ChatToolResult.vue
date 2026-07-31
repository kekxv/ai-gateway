<script setup lang="ts">
import { computed } from 'vue'
import type { ToolResultBlock } from './types'

const props = defineProps<{
  block: ToolResultBlock
}>()

const formattedContent = computed(() => {
  const raw = props.block.content
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw || '(空)'
  }
})
</script>

<template>
  <div class="chat-tool-result" :class="{ 'chat-tool-result--error': block.isError }">
    <div class="tool-result-header">
      <span class="tool-result-icon">📋</span>
      <span class="tool-result-label">{{ block.isError ? '错误' : '结果' }}</span>
      <span v-if="block.name" class="tool-result-name">{{ block.name }}</span>
      <span v-if="block.id" class="tool-result-id">{{ block.id }}</span>
    </div>
    <pre class="tool-result-content">{{ formattedContent }}</pre>
  </div>
</template>

<style scoped>
.chat-tool-result {
  border: 1px solid #bbf7d0;
  border-radius: 0.5rem;
  background: #f0fdf4;
  overflow: hidden;
}

.chat-tool-result--error {
  border-color: #fecaca;
  background: #fef2f2;
}

.tool-result-header {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  font-size: 0.8rem;
  border-bottom: 1px solid #bbf7d0;
}

.chat-tool-result--error .tool-result-header {
  border-bottom-color: #fecaca;
}

.tool-result-icon {
  flex-shrink: 0;
}

.tool-result-label {
  font-weight: 600;
  color: #166534;
}

.chat-tool-result--error .tool-result-label {
  color: #991b1b;
}

.tool-result-name {
  font-weight: 500;
  color: var(--gateway-text);
}

.tool-result-id {
  color: var(--gateway-muted);
  font-size: 0.7rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-result-content {
  margin: 0;
  padding: 0.75rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--gateway-text);
  background: rgb(255 255 255 / 50%);
}
</style>
