<template>
  <el-dialog
    v-model="visible"
    title="工具详情"
    width="500px"
    class="tool-detail-dialog"
  >
    <div v-if="tool" class="tool-detail-content">
      <!-- 基本信息 -->
      <div class="detail-section">
        <div class="detail-row">
          <span class="detail-label">工具名称</span>
          <span class="detail-value tool-name-value">{{ tool.name }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">类型</span>
          <el-tag :type="tool.type === 'builtin' ? 'info' : 'success'" size="small">
            {{ tool.type === 'builtin' ? '内置工具' : '自定义工具' }}
          </el-tag>
        </div>
        <div class="detail-row">
          <span class="detail-label">描述</span>
          <span class="detail-value">{{ tool.description }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">状态</span>
          <el-tag :type="tool.enabled ? 'success' : 'info'" size="small">
            {{ tool.enabled ? '已启用' : '已禁用' }}
          </el-tag>
        </div>
      </div>

      <!-- 参数定义 -->
      <div class="detail-section">
        <div class="section-title">
          参数定义
          <el-tag v-if="tool.parameters.required?.length" type="warning" size="small">
            {{ tool.parameters.required.length }} 个必填
          </el-tag>
        </div>
        <div class="parameters-list">
          <div
            v-for="(prop, propName) in tool.parameters.properties"
            :key="propName"
            class="parameter-item"
          >
            <div class="param-header">
              <span class="param-name">{{ propName }}</span>
              <span class="param-type">{{ prop.type }}</span>
              <el-tag v-if="isRequired(propName)" type="danger" size="small">必填</el-tag>
            </div>
            <div v-if="prop.description" class="param-desc">{{ prop.description }}</div>
            <div v-if="prop.enum" class="param-enum">
              可选值: {{ prop.enum.join(', ') }}
            </div>
            <!-- 嵌套类型展示 -->
            <div v-if="prop.type === 'array' && prop.items" class="param-nested">
              <span class="nested-label">数组元素类型:</span>
              <span class="nested-type">{{ prop.items.type }}</span>
            </div>
          </div>
        </div>
        <div v-if="Object.keys(tool.parameters.properties).length === 0" class="no-params">
          此工具无需参数
        </div>
      </div>

      <!-- JSON Schema 原始数据（可折叠） -->
      <div class="detail-section collapsible">
        <div class="section-title clickable" @click="showSchema = !showSchema">
          JSON Schema
          <el-icon class="toggle-icon">
            <ArrowDown v-if="!showSchema" />
            <ArrowUp v-else />
          </el-icon>
        </div>
        <pre v-show="showSchema" class="schema-code">{{ formatSchema(tool.parameters) }}</pre>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="tool?.type === 'custom'"
        type="primary"
        @click="handleEdit"
      >
        编辑工具
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import type { ToolDefinition } from '@/types/tool'

const props = defineProps<{
  modelValue: boolean
  tool: ToolDefinition | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'edit'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const showSchema = ref(false)

const isRequired = (propName: string) => {
  return props.tool?.parameters.required?.includes(propName) ?? false
}

const formatSchema = (schema: ToolDefinition['parameters']) => {
  return JSON.stringify(schema, null, 2)
}

const handleEdit = () => {
  emit('edit')
  visible.value = false
}
</script>

<style scoped>
.tool-detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-section {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px 16px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 0;
}

.detail-row:not(:last-child) {
  border-bottom: 1px solid #e5e7eb;
}

.detail-label {
  min-width: 80px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
}

.detail-value {
  flex: 1;
  font-size: 13px;
  color: #374151;
}

.tool-name-value {
  font-family: 'SF Mono', 'Monaco', monospace;
  font-weight: 600;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12px;
}

.parameters-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.parameter-item {
  padding: 10px 12px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.param-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-name {
  font-family: 'SF Mono', 'Monaco', monospace;
  font-weight: 500;
  color: #374151;
}

.param-type {
  font-size: 12px;
  padding: 2px 6px;
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 4px;
}

.param-desc {
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
}

.param-enum {
  margin-top: 4px;
  font-size: 11px;
  color: #667eea;
}

.param-nested {
  margin-top: 4px;
  font-size: 11px;
}

.nested-label {
  color: #6b7280;
}

.nested-type {
  color: #667eea;
}

.no-params {
  text-align: center;
  color: #9ca3af;
  padding: 16px;
}

.schema-code {
  margin: 0;
  padding: 12px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 6px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  overflow-x: auto;
}

.collapsible .section-title.clickable {
  cursor: pointer;
}

.toggle-icon {
  margin-left: auto;
}
</style>