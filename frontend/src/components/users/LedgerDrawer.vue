<script setup lang="ts">
import { computed } from 'vue'
import { ElAlert, ElButton, ElDrawer, ElEmpty, ElSkeleton, ElSkeletonItem, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-empty.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-skeleton.css'
import 'element-plus/theme-chalk/el-skeleton-item.css'
import 'element-plus/theme-chalk/el-tag.css'

import type { LedgerEntryResponse, LedgerKind, UserResponse } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  user: UserResponse | null
  entries: LedgerEntryResponse[]
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const sortedEntries = computed(() => [...props.entries].sort((left, right) => right.id - left.id))

const kindLabels: Readonly<Record<LedgerKind, string>> = {
  reservation: '预留',
  reservation_release: '释放预留',
  usage: '用量扣费',
  adjustment: '人工调整',
}

function metadataText(metadata: Record<string, unknown>): string {
  try {
    return JSON.stringify(metadata, null, 2)
  } catch {
    return '[无法序列化的元数据]'
  }
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    size="min(96vw, 64rem)"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div>
        <h2 class="drawer-heading">账本记录</h2>
        <p class="drawer-description">{{ user?.email }} · 账本记录不可编辑</p>
      </div>
    </template>

    <ElAlert v-if="error !== ''" :title="error" type="error" :closable="false" show-icon />
    <ElSkeleton v-else-if="loading" animated :rows="6">
      <template #template><ElSkeletonItem variant="rect" class="ledger-skeleton" /></template>
    </ElSkeleton>
    <ElEmpty v-else-if="sortedEntries.length === 0" description="暂无账本记录" />
    <div v-else class="ledger-list">
      <article
        v-for="entry in sortedEntries"
        :key="entry.id"
        class="ledger-row"
        :data-test="`ledger-row-${String(entry.id)}`"
      >
        <div class="ledger-row__heading">
          <ElTag effect="plain">{{ kindLabels[entry.kind] }}</ElTag>
          <strong>{{ entry.amount }}</strong>
          <time :datetime="entry.created_at">{{ formatTime(entry.created_at) }}</time>
        </div>
        <dl class="ledger-fields">
          <div><dt>余额结余</dt><dd>{{ entry.balance_after }}</dd></div>
          <div><dt>请求 ID</dt><dd>{{ entry.request_id ?? '—' }}</dd></div>
          <div><dt>幂等键</dt><dd>{{ entry.idempotency_key }}</dd></div>
        </dl>
        <details>
          <summary>元数据 JSON</summary>
          <pre class="metadata-json">{{ metadataText(entry.metadata) }}</pre>
        </details>
      </article>
    </div>

    <template #footer>
      <ElButton data-test="ledger-close" @click="emit('update:modelValue', false)">关闭</ElButton>
    </template>
  </ElDrawer>
</template>

<style scoped>
.drawer-heading {
  margin: 0;
  font-size: 1.25rem;
}

.drawer-description {
  margin: 0.35rem 0 0;
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

.ledger-skeleton {
  height: 24rem;
}

.ledger-list {
  display: grid;
  gap: 1rem;
}

.ledger-row {
  padding: 1rem;
  border: 1px solid var(--gateway-border);
  border-radius: 0.75rem;
}

.ledger-row__heading {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}

.ledger-row__heading time {
  margin-left: auto;
  color: var(--gateway-muted);
}

.ledger-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 1rem 0;
}

.ledger-fields div {
  min-width: 0;
}

.ledger-fields dt {
  color: var(--gateway-muted);
  font-size: 0.75rem;
}

.ledger-fields dd {
  overflow-wrap: anywhere;
  margin: 0.2rem 0 0;
}

.metadata-json {
  overflow: auto;
  padding: 0.75rem;
  color: var(--gateway-text);
  background: var(--gateway-soft);
  border-radius: 0.5rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 767px) {
  .ledger-fields {
    grid-template-columns: 1fr;
  }

  .ledger-row__heading time {
    width: 100%;
    margin-left: 0;
  }
}
</style>
