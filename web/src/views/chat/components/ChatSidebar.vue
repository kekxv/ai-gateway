<template>
  <!-- Mobile Sidebar Overlay -->
  <div
    v-if="sidebarOpen && isMobile"
    class="sidebar-overlay"
    @click="sidebarOpen = false"
  ></div>

  <!-- Sidebar - Conversation List -->
  <aside class="sidebar" :class="{ open: sidebarOpen || !isMobile }">
    <div class="sidebar-header">
      <span class="sidebar-title">对话历史</span>
      <button class="sidebar-close" @click="sidebarOpen = false" v-if="isMobile">
        <el-icon>
          <Close/>
        </el-icon>
      </button>
    </div>

    <div class="sidebar-content">
      <div class="new-chat-buttons">
        <button class="new-chat-btn" @click="handleNewConversation(false)">
          <el-icon>
            <Plus/>
          </el-icon>
          <span>新对话</span>
        </button>
        <button class="temp-chat-btn" @click="handleNewConversation(true)" title="临时对话不会保存到数据库">
          <el-icon>
            <Timer/>
          </el-icon>
          <span>临时</span>
        </button>
      </div>

      <!-- Show temporary conversation indicator -->
      <div v-if="isTemporaryConversation && currentConversation" class="temporary-indicator">
        <el-icon>
          <Timer/>
        </el-icon>
        <span>临时对话</span>
        <span class="temp-hint">（不保存）</span>
      </div>

      <div class="conversation-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conversation-item"
          :class="{ active: currentConversation?.id === conv.id }"
          @click="handleSelectConversation(conv)"
        >
          <div class="conv-icon">
            <el-icon>
              <ChatLineRound/>
            </el-icon>
          </div>
          <div class="conv-info">
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-meta">
              <span class="conv-model">{{ conv.model }}</span>
            </div>
          </div>
          <el-dropdown trigger="click" @command="handleAction($event, conv)">
            <button class="conv-more" @click.stop>
              <el-icon>
                <MoreFilled/>
              </el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">
                  <el-icon>
                    <Edit/>
                  </el-icon>
                  重命名
                </el-dropdown-item>
                <el-dropdown-item command="delete">
                  <el-icon>
                    <Delete/>
                  </el-icon>
                  删除对话
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div v-if="conversations.length === 0" class="empty-state">
          <el-icon :size="32">
            <ChatLineRound/>
          </el-icon>
          <p>暂无对话记录</p>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Plus, Close, Timer, ChatLineRound, MoreFilled, Edit, Delete } from '@element-plus/icons-vue'
import type { Conversation } from '@/types/conversation'

interface Props {
  sidebarOpen: boolean
  isMobile: boolean
  conversations: Conversation[]
  currentConversation: Conversation | null
  isTemporaryConversation: boolean
}

interface Emits {
  (e: 'update:sidebarOpen', value: boolean): void
  (e: 'newConversation', temporary: boolean): void
  (e: 'selectConversation', conv: Conversation): void
  (e: 'conversationAction', action: string, conv: Conversation): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const sidebarOpen = computed({
  get: () => props.sidebarOpen,
  set: (val) => emit('update:sidebarOpen', val)
})

import { computed } from 'vue'

const handleNewConversation = (temporary: boolean) => {
  emit('newConversation', temporary)
}

const handleSelectConversation = (conv: Conversation) => {
  emit('selectConversation', conv)
}

const handleAction = (action: string, conv: Conversation) => {
  emit('conversationAction', action, conv)
}
</script>

<style scoped>
.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
}

.sidebar {
  width: 280px;
  background: #f8f9fa;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  height: 100%;
  position: fixed;
  left: -280px;
  top: 0;
  z-index: 101;
  transition: left 0.3s ease;
}

.sidebar.open {
  left: 0;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.sidebar-title {
  font-weight: 600;
  color: #333;
}

.sidebar-close {
  background: none;
  border: none;
  padding: 8px;
  cursor: pointer;
  color: #666;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.new-chat-buttons {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.new-chat-btn,
.temp-chat-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.new-chat-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.new-chat-btn:hover {
  opacity: 0.9;
}

.temp-chat-btn {
  background: #e0e0e0;
  color: #666;
}

.temp-chat-btn:hover {
  background: #d0d0d0;
}

.temporary-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fff3cd;
  border-radius: 8px;
  margin-bottom: 16px;
  color: #856404;
}

.temp-hint {
  font-size: 12px;
  opacity: 0.7;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.conversation-item:hover {
  background: #f0f0f0;
}

.conversation-item.active {
  background: #e8f4fd;
  border-color: #667eea;
}

.conv-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: #f0f0f0;
  border-radius: 8px;
  color: #666;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-weight: 500;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-meta {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.conv-more {
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: #666;
  opacity: 0;
  transition: opacity 0.2s;
}

.conversation-item:hover .conv-more {
  opacity: 1;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #999;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}

@media (min-width: 768px) {
  .sidebar {
    position: static;
    left: 0;
  }

  .sidebar-overlay {
    display: none;
  }
}
</style>