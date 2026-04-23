<template>
  <div class="input-area">
    <div class="input-container">
      <!-- Enabled Skills & Tools Display -->
      <div v-if="activeSkillName || enabledTools.length > 0" class="enabled-bar-container">
        <!-- Active Skill Display -->
        <div v-if="activeSkillName" class="enabled-skills-bar">
          <span class="skills-label">技能:</span>
          <el-tag
            size="small"
            type="warning"
            closable
            @close="handleDeactivateSkill"
          >
            {{ activeSkillDisplayName }}
          </el-tag>
        </div>

        <!-- Enabled Tools Display -->
        <div v-if="enabledTools.length > 0" class="enabled-tools-bar">
          <span class="tools-label">工具:</span>
          <el-tag
            v-for="tool in visibleTools"
            :key="tool.id"
            size="small"
            class="tool-tag"
          >
            {{ tool.name }}
          </el-tag>
          <el-tag v-if="hiddenToolsCount > 0" size="small" type="info" class="more-tools-tag">
            +{{ hiddenToolsCount }}
          </el-tag>
        </div>
        <!-- Empty state -->
        <div v-else class="add-tools-bar">
          <span class="add-tools-label">工具: 无</span>
        </div>
      </div>

      <!-- Input Box -->
      <div class="input-box" :class="{ disabled: !currentConversation || sending }">
        <!-- File upload button -->
        <button
          class="upload-btn"
          :disabled="!currentConversation || sending"
          @click="handleTriggerUpload"
          title="上传文件"
        >
          <el-icon>
            <Paperclip/>
          </el-icon>
        </button>
        <input
          ref="fileInputRef"
          type="file"
          accept="*/*"
          multiple
          @change="handleFileUpload"
          style="display: none"
        />

        <!-- Attached files preview -->
        <div v-if="attachedFiles.length > 0" class="attached-files">
          <div v-for="(file, idx) in attachedFiles" :key="idx" class="attached-file">
            <img v-if="file.isImage" :src="file.dataUrl" class="file-preview"/>
            <span v-else class="file-name">{{ file.filename }}</span>
            <button class="remove-file" @click="handleRemoveFile(idx)">×</button>
          </div>
        </div>

        <textarea
          ref="textareaRef"
          v-model="inputContent"
          placeholder="输入消息... (支持粘贴截图/文件)"
          :disabled="!currentConversation || sending"
          @keydown="handleKeydown"
          @input="handleAutoResize"
          @paste="handlePaste"
          rows="1"
        ></textarea>
        <!-- Stop button -->
        <button
          v-if="sending"
          class="stop-btn"
          @click="handleStopStreaming"
          title="停止生成"
        >
          <el-icon>
            <Close/>
          </el-icon>
        </button>
        <!-- Send button -->
        <button
          v-else
          class="send-btn"
          :class="{ active: canSend }"
          :disabled="!canSend"
          @click="handleSend"
        >
          <el-icon>
            <Promotion/>
          </el-icon>
        </button>
      </div>

      <div class="input-footer">
        <div class="input-actions">
          <el-dropdown trigger="click" @command="handleApplyPreset" v-if="currentConversation && !isMobile">
            <button class="action-btn">
              <el-icon>
                <MagicStick/>
              </el-icon>
              <span>预设</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="p in presets" :key="p.id" :command="p.id">
                  <span class="preset-name">{{ p.name }}</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-dropdown trigger="click" @command="handleSetThinkingMode" v-if="currentConversation">
            <button class="action-btn" :class="{ active: thinkingMode !== 'auto' }">
              <el-icon>
                <Cpu/>
              </el-icon>
              <span>思维链</span>
              <span class="mode-tag">{{ thinkingModeLabel }}</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="auto" :class="{ 'is-active': thinkingMode === 'auto' }">
                  <span class="option-label">自动</span>
                  <span class="option-desc">不设置参数</span>
                </el-dropdown-item>
                <el-dropdown-item command="high" :class="{ 'is-active': thinkingMode === 'high' }">
                  <span class="option-label">高</span>
                  <span class="option-desc">深度思考</span>
                </el-dropdown-item>
                <el-dropdown-item command="medium" :class="{ 'is-active': thinkingMode === 'medium' }">
                  <span class="option-label">中</span>
                  <span class="option-desc">适中思考</span>
                </el-dropdown-item>
                <el-dropdown-item command="low" :class="{ 'is-active': thinkingMode === 'low' }">
                  <span class="option-label">低</span>
                  <span class="option-desc">轻度思考</span>
                </el-dropdown-item>
                <el-dropdown-item command="minimal" :class="{ 'is-active': thinkingMode === 'minimal' }">
                  <span class="option-label">最小</span>
                  <span class="option-desc">Gemini MINIMAL</span>
                </el-dropdown-item>
                <el-dropdown-item command="none" :class="{ 'is-active': thinkingMode === 'none' }">
                  <span class="option-label">不开</span>
                  <span class="option-desc">禁用思考</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="input-hint" v-if="!isMobile">
          <span>{{ shortcutHint }} 发送</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Close, Paperclip, Promotion, MagicStick, Cpu } from '@element-plus/icons-vue'
import type { PresetPrompt } from '@/types/conversation'
import type { AttachedFile } from '@/composables/useChatFiles'
import type { ThinkingMode } from '@/composables/useChatSettings'
import type { ToolDefinition } from '@/types/tool'

interface Props {
  currentConversation: { id: number } | null
  isMobile: boolean
  sending: boolean
  inputContent: string
  attachedFiles: AttachedFile[]
  activeSkillName: string | null
  activeSkillDisplayName: string
  enabledTools: ToolDefinition[]
  presets: PresetPrompt[]
  thinkingMode: ThinkingMode
  thinkingModeLabel: string
}

interface Emits {
  (e: 'update:inputContent', value: string): void
  (e: 'send'): void
  (e: 'stopStreaming'): void
  (e: 'triggerUpload'): void
  (e: 'fileUpload', event: Event): void
  (e: 'paste', event: ClipboardEvent): void
  (e: 'removeFile', index: number): void
  (e: 'deactivateSkill'): void
  (e: 'applyPreset', presetId: string): void
  (e: 'setThinkingMode', mode: ThinkingMode): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const MAX_VISIBLE_TOOLS = 3

const inputContent = computed({
  get: () => props.inputContent,
  set: (val) => emit('update:inputContent', val)
})

const visibleTools = computed(() => props.enabledTools.slice(0, MAX_VISIBLE_TOOLS))
const hiddenToolsCount = computed(() => Math.max(0, props.enabledTools.length - MAX_VISIBLE_TOOLS))

const canSend = computed(() =>
  (props.inputContent.trim() || props.attachedFiles.length > 0) && props.currentConversation
)

const shortcutHint = computed(() => {
  return navigator.platform.toUpperCase().indexOf('MAC') >= 0 ? '⌘ + Enter' : 'Ctrl + Enter'
})

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    handleSend()
  }
}

const handleAutoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 300) + 'px'
  }
}

const handlePaste = (e: ClipboardEvent) => {
  emit('paste', e)
}

const handleSend = () => {
  if (canSend.value && !props.sending) {
    emit('send')
  }
}

const handleStopStreaming = () => {
  emit('stopStreaming')
}

const handleTriggerUpload = () => {
  emit('triggerUpload')
}

const handleFileUpload = (event: Event) => {
  emit('fileUpload', event)
}

const handleRemoveFile = (index: number) => {
  emit('removeFile', index)
}

const handleDeactivateSkill = () => {
  emit('deactivateSkill')
}

const handleApplyPreset = (presetId: string) => {
  emit('applyPreset', presetId)
}

const handleSetThinkingMode = (mode: ThinkingMode) => {
  emit('setThinkingMode', mode)
}

// Focus textarea
const focusTextarea = () => {
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

// Expose for parent
defineExpose({ focusTextarea, textareaRef, fileInputRef })

// Watch inputContent to resize
watch(inputContent, () => {
  handleAutoResize()
})
</script>

<style scoped>
.input-area {
  padding: 16px 20px;
  border-top: 1px solid #e0e0e0;
  background: white;
}

.input-container {
  max-width: 800px;
  margin: 0 auto;
}

.enabled-bar-container {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 8px;
}

.enabled-skills-bar,
.enabled-tools-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.skills-label,
.tools-label,
.add-tools-label {
  font-size: 12px;
  color: #666;
}

.tool-tag {
  background: #e8f4fd;
  color: #667eea;
  border: none;
}

.more-tools-tag {
  background: #f0f0f0;
  color: #666;
  border: none;
}

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 12px;
  border: 1px solid #e0e0e0;
  transition: border-color 0.2s;
}

.input-box:focus-within {
  border-color: #667eea;
}

.input-box.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: #666;
  transition: background 0.2s;
}

.upload-btn:hover:not(:disabled) {
  background: #e0e0e0;
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.attached-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 200px;
}

.attached-file {
  position: relative;
  display: flex;
  align-items: center;
}

.file-preview {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.file-name {
  padding: 8px 12px;
  background: white;
  border-radius: 8px;
  font-size: 12px;
  color: #333;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-file {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 16px;
  height: 16px;
  background: #ff4d4f;
  color: white;
  border: none;
  border-radius: 50%;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

textarea {
  flex: 1;
  min-height: 36px;
  max-height: 300px;
  padding: 8px 0;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  color: #333;
}

textarea::placeholder {
  color: #999;
}

textarea:disabled {
  cursor: not-allowed;
}

.stop-btn,
.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.stop-btn {
  background: #ff4d4f;
  color: white;
}

.stop-btn:hover {
  background: #ff7875;
}

.send-btn {
  background: #e0e0e0;
  color: #666;
}

.send-btn.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #f0f0f0;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
  transition: background 0.2s;
}

.action-btn:hover {
  background: #e0e0e0;
}

.action-btn.active {
  background: #e8f4fd;
  color: #667eea;
}

.mode-tag {
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(102, 126, 234, 0.1);
  border-radius: 4px;
  color: #667eea;
}

.input-hint {
  font-size: 12px;
  color: #999;
}

.preset-name {
  font-size: 13px;
}

.option-label {
  font-weight: 500;
  color: #333;
}

.option-desc {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
}

.el-dropdown-menu .el-dropdown-item.is-active {
  background: #f0f7ff;
}
</style>