<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { CopyDocument } from '@element-plus/icons-vue'
import { ElButton, ElIcon } from 'element-plus'
import 'element-plus/theme-chalk/el-button.css'

const props = defineProps<{
  title: string
  value: Record<string, unknown> | null
}>()

type CopyState = 'idle' | 'copied' | 'failed'

const copyState = ref<CopyState>('idle')
let mounted = true
let copyGeneration = 0

const jsonText = computed(() => {
  try {
    return JSON.stringify(props.value, null, 2)
  } catch {
    return '[无法序列化 JSON]'
  }
})

watch(
  () => props.value,
  () => {
    copyGeneration += 1
    copyState.value = 'idle'
  },
)

async function copyJson(): Promise<void> {
  const generation = ++copyGeneration
  try {
    await navigator.clipboard.writeText(jsonText.value)
    if (mounted && generation === copyGeneration) copyState.value = 'copied'
  } catch {
    if (mounted && generation === copyGeneration) copyState.value = 'failed'
  }
}

onBeforeUnmount(() => {
  mounted = false
  copyGeneration += 1
})
</script>

<template>
  <details class="json-section">
    <summary>{{ title }}</summary>
    <div class="json-toolbar">
      <span>{{ value === null ? '没有可显示的详情' : '内容已格式化并自动换行' }}</span>
      <ElButton data-test="copy-json" size="small" @click="copyJson">
        <ElIcon><CopyDocument /></ElIcon>
        {{ copyState === 'copied' ? '已复制' : copyState === 'failed' ? '复制失败' : '复制 JSON' }}
      </ElButton>
    </div>
    <pre>{{ jsonText }}</pre>
  </details>
</template>

<style scoped>
.json-section {
  overflow: hidden;
  border: 1px solid var(--gateway-border);
  border-radius: 0.75rem;
}

.json-section summary {
  padding: 0.85rem 1rem;
  font-weight: 600;
  cursor: pointer;
  background: rgb(248 250 252 / 80%);
}

.json-toolbar {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  padding: 0.7rem 1rem;
  color: var(--gateway-muted);
  font-size: 0.8rem;
  border-top: 1px solid var(--gateway-border);
}

pre {
  overflow: auto;
  max-height: 28rem;
  margin: 0;
  padding: 1rem;
  color: var(--gateway-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--gateway-soft, #f8fafc);
  border-top: 1px solid var(--gateway-border);
}
</style>
