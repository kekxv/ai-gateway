import { api } from './index'
import { ElMessage } from '@/plugins/element-plus-services'
import type { Conversation, Message, CreateConversationRequest, UpdateConversationRequest, ChatRequest, ChatContentPart, ChatModelOption } from '@/types/conversation'
import type { ToolCall } from '@/types/tool'

export const conversationApi = {
  list: () =>
    api.get<{ data: Conversation[] }>('/conversations'),

  create: (data: CreateConversationRequest) =>
    api.post<{ data: Conversation }>('/conversations', data),

  get: (id: number) =>
    api.get<{ data: Conversation }>(`/conversations/${id}`),

  update: (id: number, data: UpdateConversationRequest) =>
    api.put<{ data: Conversation }>(`/conversations/${id}`, data),

  delete: (id: number) =>
    api.delete(`/conversations/${id}`),

  getMessages: (id: number) =>
    api.get<{ data: Message[] }>(`/conversations/${id}/messages`),

  addMessage: (id: number, data: { role: string; content: string; tool_calls?: string; tokens?: number }) =>
    api.post<{ data: Message }>(`/conversations/${id}/messages`, data),

  deleteMessagesAfter: (id: number, messageId: number) =>
    api.delete(`/conversations/${id}/messages/after/${messageId}`),

  generateTitle: (id: number) =>
    api.post<{ data: { title: string } }>(`/conversations/${id}/generate-title`),

  updateTitle: (id: number, title: string) =>
    api.put<{ message: string; title: string }>(`/conversations/${id}/title`, { title }),

  streamChat: async (
    data: ChatRequest,
    onContent: (content: string) => void,
    onDone: () => void,
    onError: (error: string) => void,
    onReasoning?: (reasoning: string) => void,
    onToolCall?: (toolCalls: ToolCall[]) => Promise<void>,
    abortSignal?: AbortSignal
  ) => {
    const token = localStorage.getItem('token')
    const baseURL = api.defaults.baseURL || '/api'

    try {
      const response = await fetch(`${baseURL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ ...data, stream: true }),
        signal: abortSignal
      })

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          ElMessage.error('登录已过期，请重新登录')
          window.location.href = '/#/login'
          window.location.reload()
          return
        }
        const errorData = await response.json().catch(() => ({ error: '请求失败' }))
        onError(errorData.error || 'Request failed')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('No response body')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let toolCalls: ToolCall[] = []
      let toolCallsByIndex: Map<number, ToolCall> = new Map()

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (toolCalls.length > 0 && onToolCall) {
            await onToolCall(toolCalls)
            return
          }
          onDone()
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonData = line.slice(6)
            if (jsonData === '[DONE]') {
              if (toolCalls.length > 0 && onToolCall) {
                await onToolCall(toolCalls)
                return
              }
              onDone()
              break
            }

            try {
              const chunk = JSON.parse(jsonData)
              if (chunk.choices && chunk.choices[0]?.delta) {
                const delta = chunk.choices[0].delta

                // Handle reasoning content - call separate callback for thinking
                const reasoning = delta.reasoning || delta.reasoning_content
                if (reasoning && typeof reasoning === 'string' && onReasoning) {
                  onReasoning(reasoning)
                }

                // Handle regular content
                if (delta.content && typeof delta.content === 'string') {
                  onContent(delta.content)
                }

                // Handle tool calls
                if (delta.tool_calls && Array.isArray(delta.tool_calls)) {
                  for (const tc of delta.tool_calls) {
                    const idx = tc.index ?? 0
                    const tcId = tc.id || ''
                    const tcName = tc.function?.name || ''
                    const tcArgs = tc.function?.arguments || ''

                    const existing = toolCallsByIndex.get(idx)
                    if (existing) {
                      existing.function.arguments += tcArgs
                    } else if (tcId || tcName) {
                      const newToolCall: ToolCall = {
                        id: tcId || `tool_${Date.now()}_${idx}`,
                        type: 'function',
                        function: {
                          name: tcName,
                          arguments: tcArgs
                        }
                      }
                      toolCallsByIndex.set(idx, newToolCall)
                      toolCalls.push(newToolCall)
                    }
                  }
                }
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        return
      }
      onError(err instanceof Error ? err.message : 'Stream error')
    }
  }
}

export const modelApi = {
  listForChat: () =>
    api.get<ChatModelOption[]>('/models/chat')
}

export function buildUserContent(text: string, parts?: ChatContentPart[]): ChatContentPart[] | string {
  if (!parts || parts.length === 0) {
    return text
  }
  const contentParts: ChatContentPart[] = []
  if (text) {
    contentParts.push({ type: 'text', text: text })
  }
  for (const part of parts) {
    if (part.type === 'image_url' && part.image_url) {
      contentParts.push({ type: 'image_url', image_url: part.image_url })
    }
  }
  if (contentParts.length === 1 && contentParts[0].type === 'text') {
    return contentParts[0].text || ''
  }
  return contentParts
}