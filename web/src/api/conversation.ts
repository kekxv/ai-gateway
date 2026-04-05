import { api } from './index'
import type { Conversation, Message, CreateConversationRequest, UpdateConversationRequest, ChatRequest, ConversationSettings } from '@/types/conversation'

export const conversationApi = {
  // List all conversations for current user
  list: () =>
    api.get<{ data: Conversation[] }>('/conversations'),

  // Create a new conversation
  create: (data: CreateConversationRequest) =>
    api.post<{ data: Conversation }>('/conversations', data),

  // Get a conversation by ID
  get: (id: number) =>
    api.get<{ data: Conversation }>(`/conversations/${id}`),

  // Update a conversation
  update: (id: number, data: UpdateConversationRequest) =>
    api.put<{ data: Conversation }>(`/conversations/${id}`, data),

  // Delete a conversation
  delete: (id: number) =>
    api.delete(`/conversations/${id}`),

  // Get messages for a conversation
  getMessages: (id: number) =>
    api.get<{ data: Message[] }>(`/conversations/${id}/messages`),

  // Send a message (non-streaming)
  sendMessage: (id: number, data: ChatRequest) =>
    api.post<{ data: Message; usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } }>(`/conversations/${id}/chat`, { ...data, stream: false }),

  // Send a message with streaming
  sendMessageStream: async (id: number, data: ChatRequest, onContent: (content: string) => void, onDone: () => void, onError: (error: string) => void) => {
    const token = localStorage.getItem('token')
    const response = await fetch(`${api.defaults.baseURL}/conversations/${id}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ ...data, stream: true })
    })

    if (!response.ok) {
      const errorData = await response.json()
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

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
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
              onDone()
              break
            }
            try {
              const chunk = JSON.parse(jsonData)
              if (chunk.choices && chunk.choices[0]?.delta?.content) {
                onContent(chunk.choices[0].delta.content)
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Stream error')
    }
  }
}

export const modelApi = {
  // Get available models for chat
  listForChat: () =>
    api.get<{ id: number; name: string; alias?: string }[]>('/models')
}