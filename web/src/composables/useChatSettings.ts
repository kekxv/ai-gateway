import { ref, computed, type Ref } from 'vue'
import type { ConversationSettings, OpenAIReasoningEffort, GeminiThinkingLevel, PresetPrompt, ChatRequest } from '@/types/conversation'
import { PRESET_PROMPTS } from '@/types/conversation'
import type { Conversation } from '@/types/conversation'

// Thinking/reasoning effort mode
export type ThinkingMode = 'auto' | 'high' | 'medium' | 'low' | 'minimal' | 'none'

export interface SettingsForm extends ConversationSettings {
  system_prompt: string
}

export function useChatSettings(
  currentConversation: Ref<Conversation | null>,
  isTemporaryConversation: Ref<boolean>,
  selectedModel: Ref<string>,
  updateConversation?: (id: number, data: Partial<Conversation>) => Promise<void>
) {
  // Settings form state
  const settingsForm = ref<SettingsForm>({
    temperature: 1,
    max_tokens: 4096,
    top_p: 0.95,
    system_prompt: ''
  })

  // Thinking mode state
  const thinkingMode = ref<ThinkingMode>('auto')

  // Preset prompts
  const presets = ref<PresetPrompt[]>(PRESET_PROMPTS)

  // Thinking mode label
  const thinkingModeLabel = computed(() => {
    const labels: Record<ThinkingMode, string> = {
      auto: '自动',
      high: '高',
      medium: '中',
      low: '低',
      minimal: '最小',
      none: '不开'
    }
    return labels[thinkingMode.value]
  })

  // Set thinking mode
  const setThinkingMode = (mode: ThinkingMode) => {
    thinkingMode.value = mode
  }

  // Get thinking config for API request
  const getThinkingConfig = (): {
    think?: boolean
    reasoning_effort?: OpenAIReasoningEffort
    generationConfig?: { thinkingConfig?: { thinkingLevel?: GeminiThinkingLevel } }
  } | undefined => {
    if (thinkingMode.value === 'auto') return undefined

    // DeepSeek/Ollama format: think (boolean)
    const thinkMap: Record<ThinkingMode, boolean | undefined> = {
      auto: undefined,
      high: undefined,
      medium: undefined,
      low: undefined,
      minimal: undefined,
      none: false
    }

    // OpenAI format: reasoning_effort
    const reasoningEffortMap: Record<ThinkingMode, OpenAIReasoningEffort | undefined> = {
      auto: undefined,
      high: 'high',
      medium: 'medium',
      low: 'low',
      minimal: undefined,
      none: 'none'
    }

    // Gemini format: thinkingLevel
    const thinkingLevelMap: Record<ThinkingMode, GeminiThinkingLevel | undefined> = {
      auto: undefined,
      high: 'HIGH',
      medium: 'MEDIUM',
      low: 'LOW',
      minimal: 'MINIMAL',
      none: 'NONE'
    }

    const thinkValue = thinkMap[thinkingMode.value]
    const effort = reasoningEffortMap[thinkingMode.value]
    const level = thinkingLevelMap[thinkingMode.value]

    return {
      think: thinkValue,
      reasoning_effort: effort,
      generationConfig: level ? { thinkingConfig: { thinkingLevel: level } } : undefined
    }
  }

  // Build request with thinking config
  const buildRequestWithThinking = (baseRequest: ChatRequest): ChatRequest => {
    const thinkingConfig = getThinkingConfig()
    if (!thinkingConfig) return baseRequest

    return {
      ...baseRequest,
      think: thinkingConfig.think,
      reasoning_effort: thinkingConfig.reasoning_effort,
      generationConfig: thinkingConfig.generationConfig
    }
  }

  // Save settings to conversation
  const saveSettings = async () => {
    if (!currentConversation.value) return false

    // Skip API update for temporary conversations
    if (isTemporaryConversation.value) {
      currentConversation.value.model = selectedModel.value
      currentConversation.value.system_prompt = settingsForm.value.system_prompt
      return true
    }

    try {
      if (updateConversation) {
        await updateConversation(currentConversation.value.id, {
          model: selectedModel.value,
          system_prompt: settingsForm.value.system_prompt,
          settings: {
            temperature: settingsForm.value.temperature,
            max_tokens: settingsForm.value.max_tokens,
            top_p: settingsForm.value.top_p
          }
        })
      }
      currentConversation.value.model = selectedModel.value
      currentConversation.value.system_prompt = settingsForm.value.system_prompt
      return true
    } catch {
      return false
    }
  }

  // Apply preset prompt
  const applyPreset = (presetId: string, inputContent: Ref<string>, focusTextarea?: () => void) => {
    const preset = presets.value.find(p => p.id === presetId)
    if (preset) {
      inputContent.value = preset.content
      if (focusTextarea) {
        focusTextarea()
      }
    }
  }

  // Initialize settings from conversation
  const initSettingsFromConversation = (conv: Conversation) => {
    if (conv.settings) {
      settingsForm.value.temperature = conv.settings.temperature || 0.7
      settingsForm.value.max_tokens = conv.settings.max_tokens || 4096
      settingsForm.value.top_p = conv.settings.top_p || 0.9
    }
    settingsForm.value.system_prompt = conv.system_prompt || ''
  }

  return {
    settingsForm,
    thinkingMode,
    thinkingModeLabel,
    presets,
    setThinkingMode,
    getThinkingConfig,
    buildRequestWithThinking,
    saveSettings,
    applyPreset,
    initSettingsFromConversation
  }
}