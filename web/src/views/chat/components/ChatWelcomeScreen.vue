<template>
  <div class="welcome-screen">
    <div class="welcome-content">
      <div class="welcome-hero">
        <div class="welcome-icon">
          <el-icon :size="48">
            <Promotion/>
          </el-icon>
        </div>
        <div class="hero-copy">
          <span class="hero-kicker">AI Gateway Chat</span>
          <h2>统一聊天入口，按模型自动切换协议</h2>
          <p>支持多种模型，自动适配协议。选择模型后开始对话。</p>
        </div>
      </div>

      <div class="quick-start">
        <div class="model-select-row">
          <span class="label">模型</span>
          <el-select v-model="selectedModel" placeholder="选择模型" size="large" @change="handleModelChange">
            <el-option
              v-for="model in models"
              :key="model.name"
              :label="model.alias || model.name"
              :value="model.name"
            />
          </el-select>
        </div>
        <div class="welcome-model-meta">
          <div class="welcome-model-card">
            <span class="meta-label">当前模型</span>
            <strong>{{ currentModelLabel }}</strong>
          </div>
        </div>
        <div class="feature-grid">
          <div class="feature-card">
            <span class="feature-title">智能对话</span>
            <span class="feature-desc">支持多种 AI 模型，自动适配最佳协议进行对话。</span>
          </div>
          <div class="feature-card">
            <span class="feature-title">多模态输入</span>
            <span class="feature-desc">继续支持图片粘贴、文件上传、工具与技能联动。</span>
          </div>
        </div>
        <div class="start-buttons">
          <button class="start-btn" @click="handleNewConversation(false)">
            <el-icon>
              <ChatLineRound/>
            </el-icon>
            <span>开始对话</span>
          </button>
          <button class="start-btn temp" @click="handleNewConversation(true)" title="临时对话不保存到数据库">
            <el-icon>
              <Timer/>
            </el-icon>
            <span>临时对话</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Promotion, ChatLineRound, Timer } from '@element-plus/icons-vue'
import type { ChatModelOption } from '@/types/conversation'

interface Props {
  models: ChatModelOption[]
  selectedModel: string
}

interface Emits {
  (e: 'update:selectedModel', value: string): void
  (e: 'newConversation', temporary: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const selectedModel = computed({
  get: () => props.selectedModel,
  set: (val) => emit('update:selectedModel', val)
})

const currentModelLabel = computed(() => {
  const model = props.models.find(m => m.name === props.selectedModel)
  return model?.alias || model?.name || '未选择模型'
})

const handleModelChange = (value: string) => {
  emit('update:selectedModel', value)
}

const handleNewConversation = (temporary: boolean) => {
  emit('newConversation', temporary)
}
</script>

<style scoped>
.welcome-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 20px;
}

.welcome-content {
  max-width: 600px;
  width: 100%;
}

.welcome-hero {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 30px;
}

.welcome-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  color: white;
}

.hero-copy {
  flex: 1;
}

.hero-kicker {
  display: block;
  font-size: 12px;
  color: #667eea;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.hero-copy h2 {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #333;
}

.hero-copy p {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.quick-start {
  background: #f8f9fa;
  border-radius: 16px;
  padding: 24px;
}

.model-select-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.model-select-row .label {
  font-weight: 500;
  color: #333;
  min-width: 60px;
}

.model-select-row .el-select {
  flex: 1;
}

.welcome-model-meta {
  margin-bottom: 20px;
}

.welcome-model-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: white;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.meta-label {
  color: #666;
  font-size: 13px;
}

.welcome-model-card strong {
  color: #333;
  font-size: 14px;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.feature-card {
  background: white;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid #e0e0e0;
}

.feature-title {
  display: block;
  font-weight: 500;
  color: #333;
  margin-bottom: 8px;
}

.feature-desc {
  font-size: 13px;
  color: #666;
}

.start-buttons {
  display: flex;
  gap: 12px;
}

.start-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.start-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.start-btn.temp {
  background: #f0f0f0;
  color: #666;
}

.start-btn.temp:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

@media (max-width: 600px) {
  .welcome-hero {
    flex-direction: column;
    text-align: center;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }

  .start-buttons {
    flex-direction: column;
  }
}
</style>