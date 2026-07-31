<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import { ElIcon } from 'element-plus'
import type { ToolUseBlock } from './types'

const props = defineProps<{
  block: ToolUseBlock
}>()

const expanded = ref(false)

const formattedInput = computed(() => {
  try {
    return JSON.stringify(JSON.parse(props.block.input), null, 2)
  } catch {
    return props.block.input || '(空)'
  }
})
</script>

<template>
  <div class="chat-tool-call">
    <div class="tool-call-header" @click="expanded = !expanded">
      <ElIcon class="tool-call-chevron">
        <ArrowRight v-if="!expanded" />
        <ArrowDown v-else />
      </ElIcon>
      <span class="tool-call-icon">🔧</span>
      <span class="tool-call-name">{{ block.name || '未知函数' }}</span>
      <span v-if="block.id" class="tool-call-id">{{ block.id }}</span>
    </div>
    <div v-if="expanded" class="tool-call-body">
      <pre class="tool-call-json">{{ formattedInput }}</pre>
    </div>
  </div>
</template>

<style scoped>
.chat-tool-call {
  border: 1px solid var(--gateway-border);
  border-radius: 0.5rem;
  background: var(--gateway-soft, #f8fafc);
  overflow: hidden;
}

.tool-call-header {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.6rem 0.75rem;
  cursor: pointer;
  user-select: none;
  font-size: 0.85rem;
}

.tool-call-header:hover {
  background: rgb(0 0 0 / 3%);
}

.tool-call-chevron {
  color: var(--gateway-muted);
  flex-shrink: 0;
}

.tool-call-icon {
  flex-shrink: 0;
}

.tool-call-name {
  font-weight: 600;
  color: var(--gateway-text);
}

.tool-call-id {
  color: var(--gateway-muted);
  font-size: 0.75rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-body {
  border-top: 1px solid var(--gateway-border);
}

.tool-call-json {
  margin: 0;
  padding: 0.75rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--gateway-text);
  background: rgb(255 255 255 / 60%);
}
</style>
