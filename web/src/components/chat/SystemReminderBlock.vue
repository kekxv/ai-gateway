<template>
  <div class="system-reminder-block" :class="{ 'is-expanded': isExpanded }">
    <div class="reminder-header" @click="toggleExpand">
      <div class="reminder-icon">
        <el-icon><InfoFilled /></el-icon>
      </div>
      <div class="reminder-meta">
        <span class="reminder-label">System Reminder</span>
        <span v-if="reminderCount > 1" class="reminder-count">{{ reminderCount }} 条</span>
      </div>
      <el-icon class="expand-icon">
        <ArrowDown v-if="!isExpanded" />
        <ArrowUp v-else />
      </el-icon>
    </div>
    <div v-show="isExpanded" class="reminder-content">
      <div v-for="(text, idx) in reminders" :key="idx" class="reminder-item">
        <div class="reminder-item-icon">
          <el-icon><Document /></el-icon>
        </div>
        <div class="reminder-item-text">{{ text }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { InfoFilled, ArrowDown, ArrowUp, Document } from '@element-plus/icons-vue'

const props = defineProps<{
  content: string
  defaultCollapsed?: boolean
}>()

const isExpanded = ref(props.defaultCollapsed !== false)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

// Parse system-reminder tags from content
const reminders = computed(() => {
  if (!props.content) return []
  const list: string[] = []
  // Match <system-reminder>...</system-reminder> tags
  const regex = /<system-reminder>\s*([\s\S]*?)\s*<\/system-reminder>/gi
  let match
  while ((match = regex.exec(props.content)) !== null) {
    const text = match[1].trim()
    if (text) {
      list.push(text)
    }
  }
  return list
})

const reminderCount = computed(() => reminders.value.length)
</script>

<style scoped>
.system-reminder-block {
  margin: 0 0 8px 0;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  overflow: hidden;
}

.reminder-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.reminder-header:hover {
  background: rgba(245, 158, 11, 0.1);
}

.reminder-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.reminder-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.reminder-label {
  font-size: 12px;
  font-weight: 500;
  color: #b45309;
}

.reminder-count {
  font-size: 11px;
  color: #92400e;
  background: rgba(146, 64, 14, 0.1);
  padding: 1px 5px;
  border-radius: 4px;
}

.expand-icon {
  color: #f59e0b;
  font-size: 14px;
  transition: transform 0.2s;
}

.reminder-content {
  padding: 8px 12px;
  border-top: 1px solid #fde68a;
  background: rgba(255, 255, 255, 0.5);
}

.reminder-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px;
  background: #fffbeb;
  border-radius: 6px;
  margin-bottom: 6px;
}

.reminder-item:last-child {
  margin-bottom: 0;
}

.reminder-item-icon {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  background: #f59e0b;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.reminder-item-text {
  font-size: 12px;
  line-height: 1.5;
  color: #78350f;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>