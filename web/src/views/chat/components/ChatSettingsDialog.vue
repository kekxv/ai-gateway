<template>
  <el-dialog
    v-model="visible"
    title="对话设置"
    width="480px"
    class="settings-dialog"
  >
    <div class="settings-form">
      <div class="setting-item">
        <label>System Prompt</label>
        <el-input
          v-model="settingsForm.system_prompt"
          type="textarea"
          :rows="4"
          placeholder="设置系统提示词，定义 AI 的角色和行为..."
        />
      </div>

      <div class="setting-item">
        <label>
          Temperature
          <span class="setting-value">{{ settingsForm.temperature }}</span>
        </label>
        <el-slider v-model="settingsForm.temperature" :min="0" :max="2" :step="0.1"/>
      </div>

      <div class="setting-item">
        <label>
          Max Tokens
          <span class="setting-value">{{ settingsForm.max_tokens }}</span>
        </label>
        <el-input-number v-model="settingsForm.max_tokens" :min="100" :max="128000" :step="100" class="w-full"/>
      </div>

      <div class="setting-item">
        <label>
          Top P
          <span class="setting-value">{{ settingsForm.top_p }}</span>
        </label>
        <el-slider v-model="settingsForm.top_p" :min="0" :max="1" :step="0.05"/>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSave">保存设置</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { SettingsForm } from '@/composables/useChatSettings'

interface Props {
  modelValue: boolean
  settings: SettingsForm
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'save', settings: SettingsForm): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = ref(props.modelValue)
const settingsForm = ref<SettingsForm>({
  system_prompt: '',
  temperature: 1,
  max_tokens: 4096,
  top_p: 0.95
})

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

watch(() => props.settings, (val) => {
  settingsForm.value = { ...val }
}, { immediate: true, deep: true })

const handleSave = async () => {
  emit('save', settingsForm.value)
  visible.value = false
}
</script>

<style scoped>
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.setting-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.setting-item label {
  font-weight: 500;
  color: #333;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.setting-value {
  color: #666;
  font-size: 14px;
}

.w-full {
  width: 100%;
}
</style>