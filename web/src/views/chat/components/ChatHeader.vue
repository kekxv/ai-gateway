<template>
  <header class="chat-header">
    <div class="header-left">
      <button class="menu-btn" @click="handleToggleSidebar" v-if="isMobile && !sidebarOpen">
        <el-icon>
          <Menu/>
        </el-icon>
      </button>

      <div class="title-panel" v-if="currentConversation">
        <div class="title-copy">
          <div class="eyebrow">会话工作台</div>
          <div class="conversation-name">{{ currentConversation.title }}</div>
        </div>
        <div class="selector-cluster">
          <div class="model-selector">
            <el-select
              v-model="selectedModel"
              placeholder="选择模型"
              size="default"
              @change="handleModelChange"
            >
              <el-option
                v-for="model in models"
                :key="model.name"
                :label="model.alias || model.name"
                :value="model.name"
              />
            </el-select>
          </div>
        </div>
      </div>
      <div class="model-selector" v-else>
        <span class="placeholder-text">选择模型后开始新的会话</span>
      </div>
    </div>

    <div class="header-right">
      <!-- Skills & Tools row -->
      <div class="header-tools-row">
        <!-- Skills Dropdown -->
        <el-dropdown trigger="click" @command="handleActivateSkill" placement="bottom-end"
                     :disabled="!currentConversation || enabledSkills.length === 0">
          <button class="icon-btn" :class="{ active: activeSkillName }" title="技能">
            <el-icon>
              <Collection/>
            </el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="auto" :class="{ 'is-active': activeSkillName === 'auto' }">
                <div class="skill-option">
                  <span class="skill-name">自动选择技能</span>
                  <span class="skill-desc">根据对话内容自动使用合适的技能库</span>
                </div>
              </el-dropdown-item>
              <el-dropdown-item v-if="activeSkillName && activeSkillName !== 'auto'" command="">
                <div class="skill-option">
                  <span class="skill-name text-warning">取消当前技能</span>
                </div>
              </el-dropdown-item>
              <el-dropdown-item divided v-for="skill in enabledSkills" :key="skill.id"
                                :command="skill.name" :class="{ 'is-active': activeSkillName === skill.name }">
                <div class="skill-option">
                  <span class="skill-name">{{ skill.display_name || skill.name }}</span>
                  <span class="skill-desc">{{ skill.description }}</span>
                </div>
              </el-dropdown-item>
              <el-dropdown-item v-if="enabledSkills.length === 0" disabled>
                <span class="text-gray-400">暂无可用技能</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- Tools Button -->
        <button class="icon-btn" @click="showToolSelector = true" title="工具">
          <el-icon>
            <Operation/>
          </el-icon>
        </button>
      </div>
      <button class="icon-btn" @click="showSettings = true" :disabled="!currentConversation" title="设置">
        <el-icon>
          <Setting/>
        </el-icon>
      </button>
      <button class="primary-btn" @click="handleNewConversation(false)">
        <el-icon>
          <Plus/>
        </el-icon>
        <span class="hide-mobile">新对话</span>
      </button>
    </div>

    <!-- Tool Selector Dialog -->
    <el-dialog
      v-model="showToolSelector"
      title="选择工具"
      :width="isMobile ? '90%' : '400px'"
      class="tool-selector-dialog"
      append-to-body
      align-center
    >
      <div class="tool-selector-content">
        <div class="tool-selector-header">
          <span>点击切换工具启用状态</span>
          <el-button size="small" link type="primary" class="manage-tools-btn" @click="handleManageTools">
            <el-icon>
              <Setting/>
            </el-icon>
            管理自定义工具
          </el-button>
        </div>
        <div class="tool-list">
          <div
            v-for="tool in allTools"
            :key="tool.id"
            class="tool-item"
            :class="{ enabled: isToolEnabled(tool.id) }"
            @click="handleToggleTool(tool.id)"
          >
            <div class="tool-info">
              <span class="tool-name">{{ tool.name }}</span>
              <span class="tool-desc">{{ tool.description.slice(0, 50) }}{{ tool.description.length > 50 ? '...' : '' }}</span>
            </div>
            <el-icon v-if="isToolEnabled(tool.id)" class="tool-check">
              <Check/>
            </el-icon>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showToolSelector = false">完成</el-button>
      </template>
    </el-dialog>
  </header>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Menu, Collection, Operation, Setting, Plus, Check } from '@element-plus/icons-vue'
import type { Conversation, ChatModelOption } from '@/types/conversation'
import type { Skill } from '@/types/skill'
import type { ToolDefinition } from '@/types/tool'

interface Props {
  currentConversation: Conversation | null
  isMobile: boolean
  sidebarOpen: boolean
  models: ChatModelOption[]
  selectedModel: string
  activeSkillName: string | null
  enabledSkills: Skill[]
  allTools: ToolDefinition[]
  enabledTools: ToolDefinition[]
}

interface Emits {
  (e: 'update:sidebarOpen', value: boolean): void
  (e: 'update:selectedModel', value: string): void
  (e: 'update:showSettings', value: boolean): void
  (e: 'newConversation', temporary: boolean): void
  (e: 'activateSkill', skillName: string): void
  (e: 'toggleTool', toolId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const router = useRouter()
const showToolSelector = ref(false)

const selectedModel = computed({
  get: () => props.selectedModel,
  set: (val) => emit('update:selectedModel', val)
})

const handleToggleSidebar = () => {
  emit('update:sidebarOpen', true)
}

const handleModelChange = (value: string) => {
  emit('update:selectedModel', value)
}

const handleNewConversation = (temporary: boolean) => {
  emit('newConversation', temporary)
}

const handleActivateSkill = (skillName: string) => {
  emit('activateSkill', skillName)
}

const showSettings = computed({
  get: () => false,
  set: () => emit('update:showSettings', true)
})

const handleManageTools = () => {
  router.push('/tools')
}

const isToolEnabled = (toolId: string) => {
  return props.enabledTools.some(t => t.id === toolId)
}

const handleToggleTool = (toolId: string) => {
  emit('toggleTool', toolId)
}
</script>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e0e0e0;
  background: white;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.menu-btn {
  background: none;
  border: none;
  padding: 8px;
  cursor: pointer;
  color: #666;
}

.title-panel {
  display: flex;
  align-items: center;
  gap: 20px;
}

.title-copy .eyebrow {
  font-size: 12px;
  color: #999;
  letter-spacing: 1px;
}

.conversation-name {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.selector-cluster {
  display: flex;
  align-items: center;
  gap: 12px;
}

.model-selector .el-select {
  width: 180px;
}

.placeholder-text {
  color: #999;
  font-size: 14px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-tools-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: #f0f0f0;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: #666;
  transition: background 0.2s;
}

.icon-btn:hover {
  background: #e0e0e0;
}

.icon-btn.active {
  background: #fff3cd;
  color: #856404;
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.primary-btn:hover {
  opacity: 0.9;
}

.hide-mobile {
  display: inline;
}

@media (max-width: 768px) {
  .hide-mobile {
    display: none;
  }

  .title-panel {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .model-selector .el-select {
    width: 140px;
  }
}

.skill-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.skill-name {
  font-weight: 500;
}

.skill-desc {
  font-size: 12px;
  color: #999;
}

.text-warning {
  color: #e6a23c;
}

.text-gray-400 {
  color: #999;
}

.tool-selector-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tool-selector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: #666;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.tool-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.tool-item:hover {
  background: #f0f0f0;
}

.tool-item.enabled {
  background: #e8f4fd;
}

.tool-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-name {
  font-weight: 500;
  color: #333;
}

.tool-desc {
  font-size: 12px;
  color: #666;
}

.tool-check {
  color: #667eea;
}
</style>