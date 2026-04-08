// Conversation types
export interface Conversation {
  id: number
  user_id: number
  title: string
  model: string
  system_prompt: string
  settings: ConversationSettings
  created_at: string
  updated_at: string
}

export interface ConversationSettings {
  temperature?: number
  max_tokens?: number
  top_p?: number
  top_k?: number
  frequency_penalty?: number
  presence_penalty?: number
  enable_thinking?: boolean
}

export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_calls?: string | Array<{
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
  }>
  tool_calls_raw?: string  // JSON string from backend (deprecated, use tool_calls instead)
  tokens?: number
  created_at: string
}

export interface CreateConversationRequest {
  title?: string
  model?: string
  system_prompt?: string
  settings?: ConversationSettings
}

export interface UpdateConversationRequest {
  title?: string
  model?: string
  system_prompt?: string
  settings?: ConversationSettings
}

export interface ChatContentPart {
  type: 'text' | 'image_url'
  text?: string
  image_url?: { url: string; detail?: string }
}

export interface ChatRequest {
  messages?: Array<{
    role: string
    content: string
    tool_calls?: string | any[]
  }>
  content: string
  parts?: ChatContentPart[]
  stream?: boolean
  settings?: ConversationSettings
  tools?: Array<{
    type: string
    function: {
      name: string
      description: string
      parameters: Record<string, unknown>
    }
  }>
  delete_after_id?: number // for regenerate: delete messages after this ID
  enable_thinking?: boolean
}

export interface ChatStreamEvent {
  type: 'content' | 'done' | 'error'
  content?: string
  error?: string
}

// Preset prompt types
export interface PresetPrompt {
  id: string
  name: string
  description?: string
  content: string
  category?: string
}

// Common preset prompts
export const PRESET_PROMPTS: PresetPrompt[] = [
  {
    id: 'translate',
    name: '翻译助手',
    description: '将文本翻译为指定语言',
    content: '请将以下内容翻译为中文（如果原文是中文则翻译为英文）：\n\n',
    category: '实用工具'
  },
  {
    id: 'summarize',
    name: '内容摘要',
    description: '总结文本要点',
    content: '请对以下内容进行简要总结，提取关键要点：\n\n',
    category: '实用工具'
  },
  {
    id: 'code-explain',
    name: '代码解释',
    description: '解释代码功能',
    content: '请解释以下代码的功能和逻辑：\n\n',
    category: '编程'
  },
  {
    id: 'code-fix',
    name: '代码修复',
    description: '修复代码问题',
    content: '请检查以下代码是否有问题，如有问题请指出并提供修复建议：\n\n',
    category: '编程'
  },
  {
    id: 'creative',
    name: '创意写作',
    description: '创意内容生成',
    content: '请帮我创作一段有趣的内容，主题是：',
    category: '创作'
  },
  {
    id: 'qa',
    name: '问答助手',
    description: '回答问题并解释',
    content: '请详细回答以下问题，并给出解释：\n\n',
    category: '通用'
  }
]