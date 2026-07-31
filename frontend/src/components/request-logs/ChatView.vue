<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Protocol } from '@/api/types'

import type { ChatMessage } from './chat/types'
import { getAssembledMessages } from './chat/assemble'
import ChatAssistantMessage from './chat/ChatAssistantMessage.vue'
import ChatSystemMessage from './chat/ChatSystemMessage.vue'
import ChatToolMessage from './chat/ChatToolMessage.vue'
import ChatUserMessage from './chat/ChatUserMessage.vue'

const props = defineProps<{
  requestDetail: Record<string, unknown> | null
  responseDetail: Record<string, unknown> | null
  protocol: Protocol
}>()

const messages = ref<ChatMessage[]>([])
const loading = ref(false)
let generation = 0

function scheduleAssembly(): void {
  const gen = ++generation
  loading.value = true

  // Defer to the next idle period so heavy payloads don't block the UI thread.
  const run = (): void => {
    if (gen !== generation) return
    try {
      const result = getAssembledMessages(props.requestDetail, props.responseDetail, props.protocol)
      if (gen !== generation) return
      messages.value = result
    } catch {
      if (gen === generation) messages.value = []
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 200 })
  } else {
    setTimeout(run, 0)
  }
}

watch(
  () => [props.requestDetail, props.responseDetail, props.protocol] as const,
  () => {
    scheduleAssembly()
  },
  { immediate: true, deep: true },
)
</script>

<template>
  <div class="chat-view">
    <div v-if="loading" class="chat-loading">
      <span class="chat-loading-spinner" />
      <span>正在解析聊天消息…</span>
    </div>
    <div v-else-if="messages.length === 0" class="chat-empty">
      未能从请求/响应中解析出聊天消息
    </div>
    <div v-else class="chat-messages">
      <template v-for="(msg, i) in messages" :key="i">
        <ChatSystemMessage v-if="msg.role === 'system'" :blocks="msg.blocks" />
        <ChatUserMessage v-else-if="msg.role === 'user'" :blocks="msg.blocks" />
        <ChatAssistantMessage v-else-if="msg.role === 'assistant'" :blocks="msg.blocks" />
        <ChatToolMessage v-else-if="msg.role === 'tool'" :blocks="msg.blocks" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
}

.chat-messages {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem 0;
}

.chat-empty {
  padding: 2rem;
  text-align: center;
  color: var(--gateway-muted);
  font-size: 0.9rem;
}

.chat-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 2rem;
  color: var(--gateway-muted);
  font-size: 0.9rem;
}

.chat-loading-spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--gateway-border);
  border-top-color: var(--gateway-brand);
  border-radius: 50%;
  animation: chat-spin 0.7s linear infinite;
}

@keyframes chat-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
