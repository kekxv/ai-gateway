<script setup lang="ts">
import type { ChatBlock } from './types'
import ChatImage from './ChatImage.vue'
import ChatTextBlock from './ChatTextBlock.vue'

defineProps<{
  blocks: ChatBlock[]
}>()
</script>

<template>
  <div class="chat-row chat-row--user">
    <div class="chat-avatar chat-avatar--user">U</div>
    <div class="chat-bubble chat-bubble--user">
      <template v-for="(block, i) in blocks" :key="i">
        <ChatTextBlock v-if="block.type === 'text'" :block="block" />
        <ChatImage v-else-if="block.type === 'image'" :block="block" />
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

.chat-row--user {
  justify-content: flex-end;
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

.chat-avatar--user {
  background: var(--gateway-brand, #1d4ed8);
  order: 2;
}

.chat-bubble {
  max-width: min(85%, 42rem);
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  font-size: 0.9rem;
  line-height: 1.6;
}

.chat-bubble--user {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: var(--gateway-text);
}
</style>
