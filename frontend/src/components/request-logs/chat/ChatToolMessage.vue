<script setup lang="ts">
import type { ChatBlock } from './types'
import ChatToolResult from './ChatToolResult.vue'

defineProps<{
  blocks: ChatBlock[]
}>()
</script>

<template>
  <div class="chat-row chat-row--tool">
    <div class="chat-avatar chat-avatar--tool">T</div>
    <div class="chat-tool-container">
      <template v-for="(block, i) in blocks" :key="i">
        <ChatToolResult v-if="block.type === 'tool-result'" :block="block" />
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

.chat-row--tool {
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

.chat-avatar--tool {
  background: #16a34a;
}

.chat-tool-container {
  max-width: min(85%, 42rem);
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
</style>
