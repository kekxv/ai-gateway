import { describe, expect, it } from 'vitest'

import { getAssembledMessages } from '@/components/request-logs/chat/assemble'
import { isChatConvertible } from '@/components/request-logs/chat/types'

describe('request log chat assembly', () => {
  it('assembles OpenAI Responses input and output messages', () => {
    const request = {
      body: {
        model: 'gpt-5',
        instructions: 'Be concise.',
        input: [{
          role: 'user',
          content: [{ type: 'input_text', text: 'Hello' }],
        }],
      },
    }
    const response = {
      body: {
        output: [{
          type: 'message',
          role: 'assistant',
          content: [{ type: 'output_text', text: 'Hi there' }],
        }],
        output_text: 'Hi there',
      },
    }

    expect(isChatConvertible(request, 'openai')).toBe(true)
    expect(getAssembledMessages(request, response, 'openai')).toEqual([
      { role: 'system', blocks: [{ type: 'text', text: 'Be concise.' }] },
      { role: 'user', blocks: [{ type: 'text', text: 'Hello' }] },
      { role: 'assistant', blocks: [{ type: 'text', text: 'Hi there' }] },
    ])
  })

  it('assembles OpenAI Responses function calls and tool outputs', () => {
    const request = {
      input: [
        { type: 'function_call_output', call_id: 'call_1', output: '{"ok":true}' },
        { role: 'user', content: 'Continue' },
      ],
    }
    const response = {
      output: [{ type: 'function_call', call_id: 'call_2', name: 'lookup', arguments: '{"q":"x"}' }],
    }

    expect(getAssembledMessages(request, response, 'openai')).toEqual([
      { role: 'tool', blocks: [{ type: 'tool-result', id: 'call_1', name: undefined, content: '{"ok":true}' }] },
      { role: 'user', blocks: [{ type: 'text', text: 'Continue' }] },
      { role: 'assistant', blocks: [{ type: 'tool-use', id: 'call_2', name: 'lookup', input: '{"q":"x"}' }] },
    ])
  })

  it('accepts Claude text responses represented as a string', () => {
    const request = { messages: [{ role: 'user', content: 'Hello' }] }
    const response = { content: 'Hi there' }

    expect(getAssembledMessages(request, response, 'claude')).toEqual([
      { role: 'user', blocks: [{ type: 'text', text: 'Hello' }] },
      { role: 'assistant', blocks: [{ type: 'text', text: 'Hi there' }] },
    ])
  })

  it('assembles OpenAI Responses streaming events', () => {
    const request = { input: 'Hello' }
    const response = {
      format: 'sse',
      events: [
        { data: { type: 'response.output_text.delta', delta: 'Hi' } },
        { data: { type: 'response.output_text.delta', delta: ' there' } },
      ],
    }

    expect(getAssembledMessages(request, response, 'openai')).toEqual([
      { role: 'user', blocks: [{ type: 'text', text: 'Hello' }] },
      { role: 'assistant', blocks: [{ type: 'text', text: 'Hi there' }] },
    ])
  })

  it('assembles Claude streaming events when type is carried in data', () => {
    const response = {
      format: 'sse',
      events: [
        { data: { type: 'content_block_start', content_block: { type: 'text' } } },
        { data: { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: 'Hi' } } },
      ],
    }

    expect(getAssembledMessages({ messages: [{ role: 'user', content: 'Hello' }] }, response, 'claude')).toEqual([
      { role: 'user', blocks: [{ type: 'text', text: 'Hello' }] },
      { role: 'assistant', blocks: [{ type: 'text', text: 'Hi' }] },
    ])
  })
})
