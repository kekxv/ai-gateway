<template>
  <div class="tools-panel" :class="{ open: props.isOpen }">
    <div class="tools-panel-header">
      <span class="tools-panel-title">工具</span>
      <div class="tools-panel-actions">
        <button class="add-tool-btn" @click="openAddDialog" title="添加自定义工具">
          <el-icon><Plus /></el-icon>
        </button>
        <button class="tools-panel-close" @click="emit('close')">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </div>
    <div class="tools-panel-content">
      <!-- 内置工具 -->
      <div class="tools-section">
        <div class="tools-section-title">内置工具</div>
        <div class="tools-list">
          <div
            v-for="tool in toolsStore.builtinTools"
            :key="tool.id"
            class="tool-item"
            :class="{ enabled: tool.enabled }"
          >
            <div class="tool-main" @click="toolsStore.toggleTool(tool.id)">
              <div class="tool-info">
                <span class="tool-name">{{ tool.name }}</span>
                <span class="tool-desc">{{ tool.description }}</span>
              </div>
              <el-switch :model-value="tool.enabled" size="small" />
            </div>
            <div class="tool-actions">
              <button class="tool-action-btn" @click="viewTool(tool)" title="查看详情">
                <el-icon><View /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 自定义工具 -->
      <div class="tools-section">
        <div class="tools-section-title">
          自定义工具
          <span class="count-badge" v-if="toolsStore.customTools.length">{{ toolsStore.customTools.length }}</span>
        </div>
        <div class="tools-list">
          <div
            v-for="tool in toolsStore.customTools"
            :key="tool.id"
            class="tool-item"
            :class="{ enabled: tool.enabled }"
          >
            <div class="tool-main" @click="toolsStore.toggleTool(tool.id)">
              <div class="tool-info">
                <span class="tool-name">{{ tool.name }}</span>
                <span class="tool-desc">{{ tool.description }}</span>
              </div>
              <el-switch :model-value="tool.enabled" size="small" />
            </div>
            <div class="tool-actions">
              <button class="tool-action-btn" @click="viewTool(tool)" title="查看详情">
                <el-icon><View /></el-icon>
              </button>
              <button class="tool-action-btn" @click="editTool(tool)" title="编辑">
                <el-icon><EditPen /></el-icon>
              </button>
              <button class="tool-action-btn danger" @click="deleteTool(tool)" title="删除">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
          <div v-if="toolsStore.customTools.length === 0" class="empty-tools">
            <p>暂无自定义工具</p>
            <button class="add-first-btn" @click="openAddDialog">
              <el-icon><Plus /></el-icon>
              添加第一个工具
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <ToolDetailDialog
      v-model="showDetailDialog"
      :tool="selectedTool"
      @edit="openEditDialogFromDetail"
    />

    <!-- 表单弹窗 -->
    <ToolFormDialog
      v-model="showFormDialog"
      :tool="editingTool"
      :is-edit="isEditing"
      @save="handleSaveTool"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Plus, Close, View, EditPen, Delete } from '@element-plus/icons-vue'
import { useToolsStore } from '@/stores/tools'
import type { ToolDefinition } from '@/types/tool'
import ToolDetailDialog from './ToolDetailDialog.vue'
import ToolFormDialog from './ToolFormDialog.vue'

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const toolsStore = useToolsStore()

const showDetailDialog = ref(false)
const showFormDialog = ref(false)
const selectedTool = ref<ToolDefinition | null>(null)
const editingTool = ref<ToolDefinition | null>(null)
const isEditing = ref(false)

const viewTool = (tool: ToolDefinition) => {
  selectedTool.value = tool
  showDetailDialog.value = true
}

const editTool = (tool: ToolDefinition) => {
  editingTool.value = tool
  isEditing.value = true
  showFormDialog.value = true
}

const openEditDialogFromDetail = () => {
  if (selectedTool.value) {
    editTool(selectedTool.value)
    selectedTool.value = null
  }
}

const deleteTool = (tool: ToolDefinition) => {
  ElMessageBox.confirm(
    `确定要删除工具 "${tool.name}" 吗？删除后无法恢复。`,
    '删除工具',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    toolsStore.deleteTool(tool.id)
    ElMessage.success('工具已删除')
  }).catch(() => {
    // 用户取消
  })
}

const openAddDialog = () => {
  editingTool.value = null
  isEditing.value = false
  showFormDialog.value = true
}

const handleSaveTool = (toolData: Omit<ToolDefinition, 'id' | 'type'>) => {
  if (isEditing.value && editingTool.value) {
    toolsStore.updateTool(editingTool.value.id, toolData)
    ElMessage.success('工具已更新')
  } else {
    toolsStore.addTool(toolData)
    ElMessage.success('工具已创建')
  }
}
</script>

<style scoped>
/* Tools Panel - 浮动面板 */
.tools-panel {
  position: fixed;
  top: 60px;
  right: 0;
  width: 320px;
  max-height: calc(100vh - 80px);
  background: #fff;
  border-left: 1px solid #e5e7eb;
  border-radius: 12px 0 0 12px;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
  z-index: 100;
  transform: translateX(100%);
  transition: transform 0.3s ease;
  display: flex;
  flex-direction: column;
}

.tools-panel.open {
  transform: translateX(0);
}

.tools-panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tools-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tools-panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #374151;
}

.tools-panel-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: #6b7280;
  cursor: pointer;
  border-radius: 6px;
}

.tools-panel-close:hover {
  background: #f3f4f6;
  color: #374151;
}

.add-tool-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #667eea;
  border: none;
  color: #fff;
  cursor: pointer;
  border-radius: 6px;
}

.add-tool-btn:hover {
  background: #5a67d8;
}

.tools-panel-content {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}

.tools-section {
  margin-bottom: 16px;
}

.tools-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
}

.count-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: #667eea;
  color: #fff;
  border-radius: 10px;
  margin-left: 4px;
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tool-item {
  display: flex;
  align-items: stretch;
  padding: 0;
  background: #f9fafb;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
}

.tool-item:hover {
  background: #f3f4f6;
}

.tool-item.enabled {
  background: #eef2ff;
}

.tool-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  cursor: pointer;
}

.tool-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.tool-desc {
  font-size: 11px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-actions {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-left: 1px solid #e5e7eb;
  background: #f3f4f6;
  gap: 4px;
}

.tool-action-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: #6b7280;
  cursor: pointer;
  border-radius: 4px;
}

.tool-action-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.tool-action-btn.danger:hover {
  background: #fee2e2;
  color: #dc2626;
}

.empty-tools {
  padding: 24px;
  text-align: center;
  color: #9ca3af;
}

.empty-tools p {
  margin-bottom: 8px;
}

.add-first-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  background: #667eea;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.add-first-btn:hover {
  background: #5a67d8;
}

@media (max-width: 768px) {
  .tools-panel {
    width: 100%;
    max-width: 320px;
    border-radius: 12px;
    right: auto;
    left: 50%;
    transform: translateX(-50%) translateY(100vh);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
  }

  .tools-panel.open {
    transform: translateX(-50%) translateY(60px);
  }
}
</style>