<script setup lang="ts">
import type { TextBlock } from './types'

defineProps<{
  block: TextBlock
}>()
</script>

<template>
  <div class="chat-text-block" v-text="block.text" />
</template>

<style scoped>
.chat-text-block {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.6;
}
</style>
