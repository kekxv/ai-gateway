import type { Protocol } from '@/api/types'
import {
  type ChatBlock,
  type ChatMessage,
  extractBody,
  isStreamBody,
} from './types'

// ---------------------------------------------------------------------------
// Stream assembly helpers
// ---------------------------------------------------------------------------

interface SseEvent {
  event?: string
  id?: string
  data?: unknown
  comment?: string
}

interface OpenAiToolCallAccum {
  id: string
  name: string
  arguments: string
}

interface AssembledAssistant {
  content: string
  toolCalls: Array<{ id: string; name: string; arguments: string }>
}

function assembleOpenAiStream(events: SseEvent[]): AssembledAssistant {
  let content = ''
  const toolCalls: OpenAiToolCallAccum[] = []

  for (const evt of events) {
    const d = evt.data
    if (d === '[DONE]' || !d || typeof d !== 'object') continue
    const data = d as Record<string, unknown>
    const choices = data.choices
    if (!Array.isArray(choices) || choices.length === 0) continue
    const delta = choices[0] as Record<string, unknown>
    const deltaObj = delta.delta as Record<string, unknown> | undefined
    if (!deltaObj) continue

    if (typeof deltaObj.content === 'string') content += deltaObj.content

    const tc = deltaObj.tool_calls
    if (Array.isArray(tc)) {
      for (const partial of tc) {
        if (!partial || typeof partial !== 'object') continue
        const p = partial as Record<string, unknown>
        const idx = typeof p.index === 'number' ? p.index : 0
        if (!toolCalls[idx]) {
          toolCalls[idx] = { id: '', name: '', arguments: '' }
        }
        const fn = p.function as Record<string, unknown> | undefined
        if (typeof p.id === 'string') toolCalls[idx].id = p.id
        if (fn) {
          if (typeof fn.name === 'string') toolCalls[idx].name += fn.name
          if (typeof fn.arguments === 'string') toolCalls[idx].arguments += fn.arguments
        }
      }
    }
  }

  return { content, toolCalls: toolCalls.filter(Boolean) }
}

interface ClaudeBlockAccum {
  type: 'text' | 'tool_use'
  text?: string
  id?: string
  name?: string
  inputJson?: string
}

function assembleClaudeStream(events: SseEvent[]): AssembledAssistant {
  const blocks: ClaudeBlockAccum[] = []

  for (const evt of events) {
    if (evt.event === 'content_block_start') {
      const d = (evt.data ?? {}) as Record<string, unknown>
      const cb = d.content_block as Record<string, unknown> | undefined
      if (!cb) continue
      const type = cb.type as string
      if (type === 'text') {
        blocks.push({ type: 'text', text: '' })
      } else if (type === 'tool_use') {
        blocks.push({
          type: 'tool_use',
          id: typeof cb.id === 'string' ? cb.id : '',
          name: typeof cb.name === 'string' ? cb.name : '',
          inputJson: '',
        })
      }
    } else if (evt.event === 'content_block_delta') {
      const d = (evt.data ?? {}) as Record<string, unknown>
      const delta = d.delta as Record<string, unknown> | undefined
      if (!delta) continue
      const idx = typeof d.index === 'number' ? d.index : blocks.length - 1
      const block = blocks[idx]
      if (!block) continue

      if (delta.type === 'text_delta' && typeof delta.text === 'string') {
        block.text = (block.text ?? '') + delta.text
      } else if (delta.type === 'input_json_delta' && typeof delta.partial_json === 'string') {
        block.inputJson = (block.inputJson ?? '') + delta.partial_json
      }
    }
  }

  let content = ''
  const toolCalls: Array<{ id: string; name: string; arguments: string }> = []

  for (const block of blocks) {
    if (block.type === 'text') {
      content += block.text ?? ''
    } else {
      toolCalls.push({
        id: block.id ?? '',
        name: block.name ?? '',
        arguments: block.inputJson ?? '',
      })
    }
  }

  return { content, toolCalls }
}

function assembleGeminiStream(events: SseEvent[]): AssembledAssistant {
  let lastData: Record<string, unknown> | null = null

  for (const evt of events) {
    const d = evt.data
    if (d && typeof d === 'object') {
      lastData = d as Record<string, unknown>
    }
  }

  let content = ''
  const toolCalls: Array<{ id: string; name: string; arguments: string }> = []

  if (lastData) {
    const candidates = lastData.candidates
    if (Array.isArray(candidates) && candidates.length > 0) {
      const candidate = candidates[0] as Record<string, unknown>
      const contentObj = candidate.content as Record<string, unknown> | undefined
      const parts = contentObj?.parts
      if (Array.isArray(parts)) {
        for (const part of parts) {
          if (!part || typeof part !== 'object') continue
          const p = part as Record<string, unknown>
          if (typeof p.text === 'string') {
            content += p.text
          } else if (p.functionCall && typeof p.functionCall === 'object') {
            const fc = p.functionCall as Record<string, unknown>
            toolCalls.push({
              id: typeof fc.id === 'string' ? fc.id : '',
              name: typeof fc.name === 'string' ? fc.name : '',
              arguments: typeof fc.args === 'object' && fc.args !== null
                ? JSON.stringify(fc.args)
                : '',
            })
          }
        }
      }
    }
  }

  return { content, toolCalls }
}

// ---------------------------------------------------------------------------
// OpenAI message parsing
// ---------------------------------------------------------------------------

function parseOpenAiContent(content: unknown): ChatBlock[] {
  if (typeof content === 'string') {
    return content ? [{ type: 'text', text: content }] : []
  }
  if (!Array.isArray(content)) return []

  const blocks: ChatBlock[] = []
  for (const part of content) {
    if (!part || typeof part !== 'object') continue
    const p = part as Record<string, unknown>
    if (p.type === 'text' && typeof p.text === 'string') {
      if (p.text) blocks.push({ type: 'text', text: p.text })
    } else if (p.type === 'image_url' && p.image_url && typeof p.image_url === 'object') {
      const url = (p.image_url as Record<string, unknown>).url
      if (typeof url === 'string' && url) {
        blocks.push({ type: 'image', url, mediaType: undefined })
      }
    } else if (p.type === 'input_image' && typeof p.image === 'string') {
      // OpenAI Responses format
      blocks.push({ type: 'image', url: p.image, mediaType: undefined })
    }
  }
  return blocks
}

function parseOpenAiMessages(
  requestBody: Record<string, unknown>,
  responseBody: Record<string, unknown>,
): ChatMessage[] {
  const messages: ChatMessage[] = []

  // System / developer messages from request
  const sysField = requestBody.system
  if (typeof sysField === 'string' && sysField) {
    messages.push({ role: 'system', blocks: [{ type: 'text', text: sysField }] })
  } else if (Array.isArray(sysField)) {
    const blocks = parseOpenAiContent(sysField)
    if (blocks.length > 0) messages.push({ role: 'system', blocks })
  }

  const reqMessages = requestBody.messages
  if (Array.isArray(reqMessages)) {
    for (const msg of reqMessages) {
      if (!msg || typeof msg !== 'object') continue
      const m = msg as Record<string, unknown>
      const role = m.role as string | undefined
      if (!role) continue

      if (role === 'system' || role === 'developer') {
        const blocks = parseOpenAiContent(m.content)
        if (blocks.length > 0) messages.push({ role: 'system', blocks })
        continue
      }

      if (role === 'user') {
        const blocks = parseOpenAiContent(m.content)
        if (blocks.length > 0) messages.push({ role: 'user', blocks })
        continue
      }

      if (role === 'assistant') {
        const blocks = parseOpenAiContent(m.content)
        const tcs = m.tool_calls
        if (Array.isArray(tcs)) {
          for (const tc of tcs) {
            if (!tc || typeof tc !== 'object') continue
            const call = tc as Record<string, unknown>
            const fn = call.function as Record<string, unknown> | undefined
            blocks.push({
              type: 'tool-use',
              id: typeof call.id === 'string' ? call.id : '',
              name: fn && typeof fn.name === 'string' ? fn.name : '',
              input: fn && typeof fn.arguments === 'string' ? fn.arguments : '',
            })
          }
        }
        if (blocks.length > 0) messages.push({ role: 'assistant', blocks })
        continue
      }

      if (role === 'tool') {
        const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
        messages.push({
          role: 'tool',
          blocks: [{
            type: 'tool-result',
            id: typeof m.tool_call_id === 'string' ? m.tool_call_id : '',
            name: typeof m.name === 'string' ? m.name : undefined,
            content,
          }],
        })
        continue
      }
    }
  }

  // Response assistant message
  const assembled = addResponseAssistant(responseBody, 'openai')
  if (assembled) messages.push(assembled)

  return messages
}

// ---------------------------------------------------------------------------
// Claude message parsing
// ---------------------------------------------------------------------------

function parseClaudeContent(content: unknown): ChatBlock[] {
  if (typeof content === 'string') {
    return content ? [{ type: 'text', text: content }] : []
  }
  if (!Array.isArray(content)) return []

  const blocks: ChatBlock[] = []
  for (const part of content) {
    if (!part || typeof part !== 'object') continue
    const p = part as Record<string, unknown>

    if (p.type === 'text' && typeof p.text === 'string') {
      if (p.text) blocks.push({ type: 'text', text: p.text })
    } else if (p.type === 'image' && p.source && typeof p.source === 'object') {
      const src = p.source as Record<string, unknown>
      if (src.type === 'url' && typeof src.url === 'string') {
        blocks.push({ type: 'image', url: src.url, mediaType: undefined })
      } else if (src.type === 'base64' && typeof src.data === 'string') {
        const mediaType = typeof src.media_type === 'string' ? src.media_type : 'image/png'
        blocks.push({ type: 'image', url: `data:${mediaType};base64,${src.data}`, mediaType })
      }
    } else if (p.type === 'tool_use') {
      const input = p.input
      blocks.push({
        type: 'tool-use',
        id: typeof p.id === 'string' ? p.id : '',
        name: typeof p.name === 'string' ? p.name : '',
        input: input !== undefined ? (typeof input === 'string' ? input : JSON.stringify(input)) : '',
      })
    } else if (p.type === 'tool_result') {
      let resultContent = ''
      if (typeof p.content === 'string') {
        resultContent = p.content
      } else if (Array.isArray(p.content)) {
        resultContent = p.content
          .filter((b): b is Record<string, unknown> => b !== null && typeof b === 'object')
          .map((b) => (typeof b.text === 'string' ? b.text : JSON.stringify(b)))
          .join('\n')
      } else if (p.content !== undefined && p.content !== null) {
        resultContent = JSON.stringify(p.content)
      }
      blocks.push({
        type: 'tool-result',
        id: typeof p.tool_use_id === 'string' ? p.tool_use_id : '',
        name: typeof p.name === 'string' ? p.name : undefined,
        content: resultContent,
        isError: p.is_error === true,
      })
    }
  }
  return blocks
}

function parseClaudeMessages(
  requestBody: Record<string, unknown>,
  responseBody: Record<string, unknown>,
): ChatMessage[] {
  const messages: ChatMessage[] = []

  // System prompt
  const sys = requestBody.system
  if (typeof sys === 'string' && sys) {
    messages.push({ role: 'system', blocks: [{ type: 'text', text: sys }] })
  } else if (Array.isArray(sys)) {
    const blocks = parseClaudeContent(sys)
    if (blocks.length > 0) messages.push({ role: 'system', blocks })
  }

  const reqMessages = requestBody.messages
  if (Array.isArray(reqMessages)) {
    for (const msg of reqMessages) {
      if (!msg || typeof msg !== 'object') continue
      const m = msg as Record<string, unknown>
      const role = m.role as string | undefined
      if (!role) continue

      const blocks = parseClaudeContent(m.content)
      if (blocks.length === 0) continue

      if (role === 'user') {
        // Check if all blocks are tool results
        const allToolResults = blocks.every((b) => b.type === 'tool-result')
        if (allToolResults) {
          for (const block of blocks) {
            messages.push({ role: 'tool', blocks: [block] })
          }
        } else {
          messages.push({ role: 'user', blocks })
        }
      } else if (role === 'assistant') {
        messages.push({ role: 'assistant', blocks })
      }
    }
  }

  // Response
  const assembled = addResponseAssistant(responseBody, 'claude')
  if (assembled) messages.push(assembled)

  return messages
}

// ---------------------------------------------------------------------------
// Gemini message parsing
// ---------------------------------------------------------------------------

function parseGeminiParts(parts: unknown): ChatBlock[] {
  if (!Array.isArray(parts)) return []

  const blocks: ChatBlock[] = []
  for (const part of parts) {
    if (!part || typeof part !== 'object') continue
    const p = part as Record<string, unknown>

    if (typeof p.text === 'string') {
      if (p.text) blocks.push({ type: 'text', text: p.text })
    } else if (p.inlineData && typeof p.inlineData === 'object') {
      const ind = p.inlineData as Record<string, unknown>
      if (typeof ind.data === 'string') {
        const mime = typeof ind.mimeType === 'string' ? ind.mimeType : 'image/png'
        blocks.push({ type: 'image', url: `data:${mime};base64,${ind.data}`, mediaType: mime })
      }
    } else if (p.fileData && typeof p.fileData === 'object') {
      const fd = p.fileData as Record<string, unknown>
      if (typeof fd.fileUri === 'string') {
        blocks.push({
          type: 'image',
          url: fd.fileUri,
          mediaType: typeof fd.mimeType === 'string' ? fd.mimeType : undefined,
        })
      }
    } else if (p.functionCall && typeof p.functionCall === 'object') {
      const fc = p.functionCall as Record<string, unknown>
      const args = fc.args
      blocks.push({
        type: 'tool-use',
        id: typeof fc.id === 'string' ? fc.id : '',
        name: typeof fc.name === 'string' ? fc.name : '',
        input: args !== undefined ? (typeof args === 'string' ? args : JSON.stringify(args)) : '',
      })
    } else if (p.functionResponse && typeof p.functionResponse === 'object') {
      const fr = p.functionResponse as Record<string, unknown>
      const resp = fr.response
      blocks.push({
        type: 'tool-result',
        id: typeof fr.id === 'string' ? fr.id : '',
        name: typeof fr.name === 'string' ? fr.name : undefined,
        content: resp !== undefined ? (typeof resp === 'string' ? resp : JSON.stringify(resp)) : '',
      })
    }
  }
  return blocks
}

function parseGeminiMessages(
  requestBody: Record<string, unknown>,
  responseBody: Record<string, unknown>,
): ChatMessage[] {
  const messages: ChatMessage[] = []

  // System instruction
  const sysInstr = requestBody.systemInstruction
  if (sysInstr && typeof sysInstr === 'object') {
    const si = sysInstr as Record<string, unknown>
    const parts = parseGeminiParts(si.parts)
    const textParts = parts.filter((b): b is { type: 'text'; text: string } => b.type === 'text')
    if (textParts.length > 0) {
      messages.push({ role: 'system', blocks: textParts })
    }
  }

  const contents = requestBody.contents
  if (Array.isArray(contents)) {
    for (const item of contents) {
      if (!item || typeof item !== 'object') continue
      const c = item as Record<string, unknown>
      const role = c.role as string | undefined

      const blocks = parseGeminiParts(c.parts)
      if (blocks.length === 0) continue

      if (role === 'model') {
        messages.push({ role: 'assistant', blocks })
      } else {
        // user role
        const allToolResults = blocks.every((b) => b.type === 'tool-result')
        if (allToolResults) {
          for (const block of blocks) {
            messages.push({ role: 'tool', blocks: [block] })
          }
        } else {
          messages.push({ role: 'user', blocks })
        }
      }
    }
  }

  // Response
  const assembled = addResponseAssistant(responseBody, 'gemini')
  if (assembled) messages.push(assembled)

  return messages
}

// ---------------------------------------------------------------------------
// Response helper
// ---------------------------------------------------------------------------

function addResponseAssistant(
  responseBody: Record<string, unknown>,
  protocol: Protocol,
): ChatMessage | null {
  let content = ''
  const toolCalls: ChatBlock[] = []

  if (protocol === 'openai') {
    const choices = responseBody.choices
    if (Array.isArray(choices) && choices.length > 0) {
      const choice = choices[0] as Record<string, unknown>
      const msg = choice.message as Record<string, unknown> | undefined
      if (msg) {
        const blocks = parseOpenAiContent(msg.content)
        for (const b of blocks) {
          if (b.type === 'text') content += b.text
          else toolCalls.push(b)
        }
        const tcs = msg.tool_calls
        if (Array.isArray(tcs)) {
          for (const tc of tcs) {
            if (!tc || typeof tc !== 'object') continue
            const call = tc as Record<string, unknown>
            const fn = call.function as Record<string, unknown> | undefined
            toolCalls.push({
              type: 'tool-use',
              id: typeof call.id === 'string' ? call.id : '',
              name: fn && typeof fn.name === 'string' ? fn.name : '',
              input: fn && typeof fn.arguments === 'string' ? fn.arguments : '',
            })
          }
        }
      }
    }
  } else if (protocol === 'claude') {
    const contentArr = responseBody.content
    if (Array.isArray(contentArr)) {
      for (const block of contentArr) {
        if (!block || typeof block !== 'object') continue
        const b = block as Record<string, unknown>
        if (b.type === 'text' && typeof b.text === 'string') {
          content += b.text
        } else if (b.type === 'tool_use') {
          const input = b.input
          toolCalls.push({
            type: 'tool-use',
            id: typeof b.id === 'string' ? b.id : '',
            name: typeof b.name === 'string' ? b.name : '',
            input: input !== undefined ? (typeof input === 'string' ? input : JSON.stringify(input)) : '',
          })
        }
      }
    }
  } else {
    const candidates = responseBody.candidates
    if (Array.isArray(candidates) && candidates.length > 0) {
      const candidate = candidates[0] as Record<string, unknown>
      const contentObj = candidate.content as Record<string, unknown> | undefined
      if (contentObj) {
        const blocks = parseGeminiParts(contentObj.parts)
        for (const b of blocks) {
          if (b.type === 'text') content += b.text
          else toolCalls.push(b)
        }
      }
    }
  }

  const blocks: ChatBlock[] = []
  if (content) blocks.push({ type: 'text', text: content })
  blocks.push(...toolCalls)

  return blocks.length > 0 ? { role: 'assistant', blocks } : null
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function getAssembledMessages(
  requestDetail: Record<string, unknown> | null,
  responseDetail: Record<string, unknown> | null,
  protocol: Protocol,
): ChatMessage[] {
  const requestBody = extractBody(requestDetail)
  const responseBody = extractBody(responseDetail)

  const reqObj = requestBody && typeof requestBody === 'object' && !Array.isArray(requestBody)
    ? requestBody as Record<string, unknown>
    : {}

  // Handle response: assemble stream if needed
  let respObj: Record<string, unknown> = {}
  if (responseBody && typeof responseBody === 'object' && !Array.isArray(responseBody)) {
    const bodyObj = responseBody as Record<string, unknown>
    if (isStreamBody(bodyObj)) {
      const events = bodyObj.events as SseEvent[]
      const assembled =
        protocol === 'openai' ? assembleOpenAiStream(events)
        : protocol === 'claude' ? assembleClaudeStream(events)
        : assembleGeminiStream(events)

      // Build a synthetic non-stream response object for uniform handling
      if (protocol === 'openai') {
        const message: Record<string, unknown> = { role: 'assistant', content: assembled.content }
        if (assembled.toolCalls.length > 0) {
          message.tool_calls = assembled.toolCalls.map((tc) => ({
            id: tc.id,
            type: 'function',
            function: { name: tc.name, arguments: tc.arguments },
          }))
        }
        respObj = { choices: [{ message }] }
      } else if (protocol === 'claude') {
        const contentArr: Array<Record<string, unknown>> = []
        if (assembled.content) {
          contentArr.push({ type: 'text', text: assembled.content })
        }
        for (const tc of assembled.toolCalls) {
          let input: unknown = tc.arguments
          try { input = JSON.parse(tc.arguments) } catch { /* keep string */ }
          contentArr.push({ type: 'tool_use', id: tc.id, name: tc.name, input })
        }
        respObj = { content: contentArr }
      } else {
        const parts: Array<Record<string, unknown>> = []
        if (assembled.content) parts.push({ text: assembled.content })
        for (const tc of assembled.toolCalls) {
          let args: unknown = tc.arguments
          try { args = JSON.parse(tc.arguments) } catch { /* keep string */ }
          parts.push({ functionCall: { id: tc.id, name: tc.name, args } })
        }
        respObj = { candidates: [{ content: { role: 'model', parts } }] }
      }
    } else {
      respObj = bodyObj
    }
  }

  switch (protocol) {
    case 'openai':
      return parseOpenAiMessages(reqObj, respObj)
    case 'claude':
      return parseClaudeMessages(reqObj, respObj)
    case 'gemini':
      return parseGeminiMessages(reqObj, respObj)
    default:
      return []
  }
}
