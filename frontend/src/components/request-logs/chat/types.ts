import type { Protocol } from '@/api/types'

export type ChatRole = 'system' | 'user' | 'assistant' | 'tool'

export interface TextBlock {
  type: 'text'
  text: string
}

export interface ImageBlock {
  type: 'image'
  url: string
  mediaType: string | undefined
}

export interface ToolUseBlock {
  type: 'tool-use'
  id: string
  name: string
  input: string // JSON string (for display)
}

export interface ToolResultBlock {
  type: 'tool-result'
  id: string
  name: string | undefined
  content: string
  isError?: boolean
}

export type ChatBlock = TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock

export interface ChatMessage {
  role: ChatRole
  blocks: ChatBlock[]
}

export function isChatConvertible(detail: Record<string, unknown> | null, protocol: Protocol): boolean {
  const body = extractBody(detail)
  if (!body || typeof body !== 'object') return false

  const bodyObj = body as Record<string, unknown>

  switch (protocol) {
    case 'openai':
      return Array.isArray(bodyObj.messages) || Array.isArray(bodyObj.input) || typeof bodyObj.input === 'string'
    case 'claude':
      return Array.isArray(bodyObj.messages)
    case 'gemini':
      return Array.isArray(bodyObj.contents)
    default:
      return false
  }
}

export function extractBody(detail: Record<string, unknown> | null): unknown {
  if (!detail || typeof detail !== 'object') return null
  if ('body' in detail) return detail.body ?? null
  return detail
}

export function isStreamBody(body: unknown): boolean {
  if (!body || typeof body !== 'object') return false
  const bodyObj = body as Record<string, unknown>
  return bodyObj.format === 'sse' && Array.isArray(bodyObj.events)
}
