<script setup lang="ts">
import { computed } from 'vue'
import { ElImage } from 'element-plus'
import 'element-plus/theme-chalk/el-image.css'

import type { ImageBlock } from './types'

const props = defineProps<{
  block: ImageBlock
}>()

const src = computed(() => props.block.url)
const previewList = computed(() => (props.block.url.startsWith('data:') ? [] : [props.block.url]))
</script>

<template>
  <div class="chat-image-block">
    <ElImage
      :src="src"
      fit="contain"
      :preview-src-list="previewList"
      class="chat-image"
    />
    <span v-if="block.mediaType" class="chat-image-media">{{ block.mediaType }}</span>
  </div>
</template>

<style scoped>
.chat-image-block {
  display: inline-flex;
  flex-direction: column;
  gap: 0.25rem;
}

.chat-image {
  max-width: 300px;
  max-height: 300px;
  border-radius: 0.5rem;
  border: 1px solid var(--gateway-border);
}

.chat-image-media {
  color: var(--gateway-muted);
  font-size: 0.7rem;
}
</style>
