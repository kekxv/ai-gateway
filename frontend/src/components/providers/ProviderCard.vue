<script setup lang="ts">
import { Edit, Delete, Refresh } from '@element-plus/icons-vue'
import { ElButton, ElIcon, ElTag } from 'element-plus'
import type { Protocol, ProviderResponse } from '@/api/types'
import StatusTag from '@/components/common/StatusTag.vue'

defineProps<{
  provider: ProviderResponse
  loading?: boolean
  nonDeletable?: boolean
}>()

const emit = defineEmits<{
  edit: [provider: ProviderResponse]
  delete: [provider: ProviderResponse]
  sync: [provider: ProviderResponse]
}>()

const protocolLabels: Readonly<Record<Protocol, string>> = {
  openai: 'OpenAI',
  claude: 'Claude',
  gemini: 'Gemini',
}

function formatSyncTime(value: string | null): string {
  if (value === null) return '从未同步'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatInterval(seconds: number): string {
  if (seconds % 3600 === 0) return `${String(seconds / 3600)} 小时`
  if (seconds % 60 === 0) return `${String(seconds / 60)} 分钟`
  return `${String(seconds)} 秒`
}
</script>

<template>
  <div class="provider-card" :class="{ 'is-disabled': !provider.enabled }">
    <div class="card-header">
      <div class="provider-info">
        <h3 class="provider-name">{{ provider.name }}</h3>
        <StatusTag :status="provider.enabled ? 'enabled' : 'disabled'" />
      </div>
      <div class="card-actions">
        <ElButton
          size="small"
          type="primary"
          :data-test="`sync-provider-${String(provider.id)}`"
          :loading="loading"
          :disabled="loading"
          @click="emit('sync', provider)"
        >
          <ElIcon><Refresh /></ElIcon>
          同步
        </ElButton>
        <ElButton
          size="small"
          :data-test="`edit-provider-${String(provider.id)}`"
          :disabled="loading"
          @click="emit('edit', provider)"
        >
          <ElIcon><Edit /></ElIcon>
          编辑
        </ElButton>
        <ElButton
          size="small"
          type="danger"
          :data-test="`delete-provider-${String(provider.id)}`"
          :disabled="loading || nonDeletable"
          :title="nonDeletable ? '该供应商已有请求历史，请改为停用' : undefined"
          @click="emit('delete', provider)"
        >
          <ElIcon><Delete /></ElIcon>
          删除
        </ElButton>
      </div>
    </div>

    <div class="card-body">
      <div class="info-section">
        <div class="info-row">
          <span class="label">模型同步：</span>
          <StatusTag
            :status="provider.auto_load_models ? 'healthy' : 'disabled'"
            :label="provider.auto_load_models ? '自动同步' : '手动同步'"
          />
        </div>
        <div class="info-row">
          <span class="label">同步间隔：</span>
          <span class="value">{{ formatInterval(provider.model_sync_interval_seconds) }}</span>
        </div>
        <div class="info-row">
          <span class="label">上次同步：</span>
          <span class="value">{{ formatSyncTime(provider.last_model_sync_at) }}</span>
        </div>
      </div>

      <div v-if="provider.protocols.length > 0" class="protocols-section">
        <div class="section-title">协议配置</div>
        <div class="protocols-grid">
          <div
            v-for="protocol in provider.protocols"
            :key="protocol.id"
            class="protocol-item"
            :class="{ 'is-disabled': !protocol.enabled }"
          >
            <ElTag
              :type="protocol.enabled ? 'primary' : 'info'"
              effect="plain"
              size="small"
            >
              {{ protocolLabels[protocol.protocol] }}
            </ElTag>
            <div class="protocol-details">
              <div class="protocol-url">{{ protocol.base_url }}</div>
              <div v-if="protocol.websocket_url" class="protocol-ws">
                WS: {{ protocol.websocket_url }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-protocols">
        <span class="muted">未配置协议</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.provider-card {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid var(--gateway-border);
  border-radius: 16px;
  padding: 1.5rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.05);
}

.provider-card:hover {
  border-color: var(--gateway-brand);
  box-shadow: 0 8px 24px rgb(37 99 235 / 0.12), 0 2px 8px rgb(0 0 0 / 0.08);
  transform: translateY(-2px);
}

.provider-card.is-disabled {
  opacity: 0.65;
  background: #f1f5f9;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.25rem;
  gap: 1rem;
}

.provider-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
}

.provider-name {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--gateway-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.card-actions :deep(.el-button) {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.info-section {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 0.875rem;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.info-row .label {
  color: var(--gateway-muted);
  font-size: 0.8125rem;
  font-weight: 500;
  min-width: 5.5rem;
}

.info-row .value {
  color: var(--gateway-text);
  font-size: 0.875rem;
  font-weight: 600;
}

.protocols-section {
  border-top: 1px solid var(--gateway-border);
  padding-top: 1.25rem;
}

.section-title {
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--gateway-text);
  margin-bottom: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.7;
}

.protocols-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.protocol-item {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  padding: 1rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s;
}

.protocol-item:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgb(0 0 0 / 0.05);
}

.protocol-item.is-disabled {
  opacity: 0.6;
  background: #f1f5f9;
}

.protocol-details {
  flex: 1;
  min-width: 0;
}

.protocol-url {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.8125rem;
  color: var(--gateway-text);
  word-break: break-all;
}

.protocol-ws {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.75rem;
  color: var(--gateway-muted);
  margin-top: 0.25rem;
  word-break: break-all;
}

.empty-protocols {
  padding: 1rem;
  text-align: center;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px dashed var(--gateway-border);
}

.muted {
  color: var(--gateway-muted);
  font-size: 0.875rem;
}

@media (max-width: 640px) {
  .card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .card-actions {
    justify-content: flex-end;
  }
}
</style>
