<template>
  <div class="attachment-preview">
    <!-- 图片类型 -->
    <div v-if="part.type === 'image_url'" class="image-preview">
      <el-image
        :src="part.image_url?.url"
        :preview-src-list="[part.image_url?.url || '']"
        fit="cover"
        class="thumbnail"
      />
    </div>

    <!-- 文件类型（预留，当前主要是图片） -->
    <div v-else class="file-preview">
      <el-icon class="file-icon"><Document /></el-icon>
      <span class="filename">{{ filename }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'
import type { ChatContentPart } from '@/types/conversation'

interface Props {
  part: ChatContentPart
}

const props = defineProps<Props>()

const filename = computed(() => {
  // 从 data URL 中提取文件名信息，或使用默认名称
  if (props.part.image_url?.url) {
    const url = props.part.image_url.url
    // 尝试从 URL 中提取 mime 类型作为文件名提示
    if (url.startsWith('data:image/')) {
      const mimeMatch = url.match(/data:image\/([^;]+)/)
      if (mimeMatch) {
        return `image.${mimeMatch[1]}`
      }
    }
  }
  return 'file'
})
</script>

<style scoped>
.attachment-preview {
  display: inline-block;
}

.image-preview {
  width: 80px;
  height: 80px;
  border-radius: 8px;
  overflow: hidden;
  background-color: #f5f5f5;
}

.thumbnail {
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background-color: #f5f5f5;
  border-radius: 8px;
  max-width: 200px;
}

.file-icon {
  font-size: 24px;
  color: #409eff;
}

.filename {
  font-size: 13px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>