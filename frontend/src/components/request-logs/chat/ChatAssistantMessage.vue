<script setup lang="ts">
import type { ChatBlock } from './types'
import ChatImage from './ChatImage.vue'
import ChatTextBlock from './ChatTextBlock.vue'
import ChatToolCall from './ChatToolCall.vue'
import ChatToolResult from './ChatToolResult.vue'

defineProps<{
  blocks: ChatBlock[]
}>()
</script>

<template>
  <div class="chat-row chat-row--assistant">
    <div class="chat-avatar chat-avatar--assistant">A</div>
    <div class="chat-bubble chat-bubble--assistant">
      <template v-for="(block, i) in blocks" :key="i">
        <ChatTextBlock v-if="block.type === 'text'" :block="block" />
        <ChatImage v-else-if="block.type === 'image'" :block="block" />
        <ChatToolCall v-else-if="block.type === 'tool-use'" :block="block" />
        <ChatToolResult v-else-if="block.type === 'tool-result'" :block="block" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-row {
  display: flex;
  gap: 0.75rem;
  margin: 0.6rem 0;
}

.chat-row--assistant {
  justify-content: flex-start;
}

.chat-avatar {
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 700;
  color: #fff;
}

.chat-avatar--assistant {
  background: #475569;
}

.chat-bubble {
  max-width: min(85%, 42rem);
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  font-size: 0.9rem;
  line-height: 1.6;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.chat-bubble--assistant {
  background: #fff;
  border: 1px solid var(--gateway-border);
  color: var(--gateway-text);
}
</style>
