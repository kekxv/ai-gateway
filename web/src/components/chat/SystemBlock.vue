<template>
  <div class="system-block" :class="{ 'is-expanded': isExpanded }">
    <div class="system-header" @click="toggleExpand">
      <div class="system-icon">
        <el-icon><Setting /></el-icon>
      </div>
      <div class="system-meta">
        <span class="system-label">System Prompt</span>
        <span v-if="contentLength" class="system-length">{{ contentLength }} 字</span>
      </div>
      <el-icon class="expand-icon">
        <ArrowDown v-if="!isExpanded" />
        <ArrowUp v-else />
      </el-icon>
    </div>
    <div v-show="isExpanded" class="system-content">
      <div class="system-text">{{ content }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Setting, ArrowDown, ArrowUp } from '@element-plus/icons-vue'

const props = defineProps<{
  content: string
  defaultCollapsed?: boolean
}>()

const isExpanded = ref(!props.defaultCollapsed)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const contentLength = computed(() => {
  if (!props.content) return 0
  return props.content.length
})
</script>

<style scoped>
.system-block {
  width: 100%;
  max-width: 800px;
  margin: 8px auto;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  overflow: hidden;
}

.system-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.system-header:hover {
  background: rgba(245, 158, 11, 0.1);
}

.system-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.system-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.system-label {
  font-size: 13px;
  font-weight: 500;
  color: #b45309;
}

.system-length {
  font-size: 11px;
  color: #92400e;
  background: rgba(146, 64, 14, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.expand-icon {
  color: #f59e0b;
  transition: transform 0.2s;
}

.system-content {
  padding: 12px 16px;
  border-top: 1px solid #fde68a;
  background: rgba(255, 255, 255, 0.7);
}

.system-text {
  font-size: 13px;
  line-height: 1.7;
  color: #78350f;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>