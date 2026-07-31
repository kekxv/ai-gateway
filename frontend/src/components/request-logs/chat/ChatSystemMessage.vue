<script setup lang="ts">
import type { ChatBlock } from './types'
import ChatImage from './ChatImage.vue'
import ChatTextBlock from './ChatTextBlock.vue'

defineProps<{
  blocks: ChatBlock[]
}>()
</script>

<template>
  <div class="chat-system-message">
    <div class="system-label">
      <span class="system-icon">⚙️</span>
      系统提示
    </div>
    <div class="system-content">
      <template v-for="(block, i) in blocks" :key="i">
        <ChatTextBlock v-if="block.type === 'text'" :block="block" />
        <ChatImage v-else-if="block.type === 'image'" :block="block" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-system-message {
  margin: 0.5rem 0;
}

.system-label {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.4rem;
  color: var(--gateway-muted);
  font-size: 0.8rem;
  font-weight: 600;
}

.system-icon {
  font-size: 0.85rem;
}

.system-content {
  padding: 0.75rem 1rem;
  background: var(--gateway-soft, #f8fafc);
  border: 1px solid var(--gateway-border);
  border-radius: 0.6rem;
  color: var(--gateway-text);
  font-size: 0.88rem;
}
</style>
