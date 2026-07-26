# OpenAI API Reference

This document describes the OpenAI API endpoints supported by the AI Gateway.

## Overview

The gateway supports multiple OpenAI API formats for compatibility with various CLI tools and applications, including Claude CLI, Codex, and other modern AI development tools.

## Endpoints

### Chat Completions API

**Endpoint:** `POST /v1/chat/completions`

The standard chat completions endpoint compatible with OpenAI's Chat API.

**Request:**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 100,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "gpt-4",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21
  }
}
```

### Responses API

**Endpoint:** `POST /v1/responses`

The newer unified API that supports both simple string input and structured conversation history. This is the recommended API for new integrations and is compatible with Claude CLI and other modern tools.

**Simple String Input:**
```json
{
  "model": "gpt-4",
  "input": "Hello, how are you?"
}
```

**Structured Conversation History:**
```json
{
  "model": "gpt-4",
  "input": [
    {"type": "message", "role": "user", "content": "Hello"},
    {"type": "message", "role": "assistant", "content": "Hi there!"},
    {"type": "message", "role": "user", "content": "How are you?"}
  ]
}
```

**Tool Calls:**
```json
{
  "model": "gpt-4",
  "input": [
    {"type": "message", "role": "user", "content": "What's the weather in Paris?"},
    {
      "type": "function_call",
      "id": "call_123",
      "name": "get_weather",
      "arguments": "{\"city\": \"Paris\"}"
    },
    {
      "type": "function_call_output",
      "call_id": "call_123",
      "output": "{\"temperature\": 22}"
    }
  ],
  "tools": [
    {
      "type": "function",
      "name": "get_weather",
      "description": "Get weather information",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {"type": "string"}
        },
        "required": ["city"]
      }
    }
  ]
}
```

**Response:**
```json
{
  "id": "resp_abc123def456",
  "object": "response",
  "created_at": 1677652288,
  "model": "gpt-4",
  "output": [
    {
      "type": "message",
      "id": "msg_xyz789",
      "role": "assistant",
      "status": "completed",
      "content": [
        {
          "type": "output_text",
          "text": "Hello! How can I help you today?",
          "annotations": []
        }
      ]
    }
  ],
  "status": "completed",
  "usage": {
    "input_tokens": 9,
    "output_tokens": 12,
    "total_tokens": 21
  }
}
```

**Streaming Response:**

When `stream: true` is set, the response is sent as Server-Sent Events (SSE) with the following event types:

```
event: response.created
data: {"type": "response.created", "response": {"id": "resp_...", "object": "response", "created_at": 1677652288, "model": "gpt-4", "output": [], "status": "in_progress"}}

event: response.in_progress
data: {"type": "response.in_progress", "response": {"id": "resp_...", "object": "response", "created_at": 1677652288, "model": "gpt-4", "output": [], "status": "in_progress"}}

event: response.output_item.added
data: {"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "id": "msg_...", "role": "assistant", "status": "in_progress", "content": []}}

event: response.content_part.added
data: {"type": "response.content_part.added", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}}

event: response.output_text.delta
data: {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": "Hello"}

event: response.content_part.done
data: {"type": "response.content_part.done", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "Hello! How can I help you today?", "annotations": []}}

event: response.output_item.done
data: {"type": "response.output_item.done", "output_index": 0, "item": {"type": "message", "id": "msg_...", "role": "assistant", "status": "completed", "content": []}}

event: response.completed
data: {"type": "response.completed", "response": {"id": "resp_...", "object": "response", "created_at": 1677652288, "model": "gpt-4", "output": [], "status": "completed", "usage": {"input_tokens": 9, "output_tokens": 12, "total_tokens": 21}}}
```

### Embeddings API

**Endpoint:** `POST /v1/embeddings`

Generate text embeddings for RAG (Retrieval-Augmented Generation) and vector operations.

**Request:**
```json
{
  "model": "text-embedding-ada-002",
  "input": "The quick brown fox jumps over the lazy dog"
}
```

**Response:**
```json
{
  "object": "list",
  "data": [{
    "object": "embedding",
    "embedding": [0.0023064255, -0.009327292, ...],
    "index": 0
  }],
  "model": "text-embedding-ada-002",
  "usage": {
    "prompt_tokens": 8,
    "total_tokens": 8
  }
}
```

### Completions API (Legacy)

**Endpoint:** `POST /v1/completions`

Legacy text completions endpoint for backward compatibility with older applications.

**Request:**
```json
{
  "model": "gpt-3.5-turbo-instruct",
  "prompt": "Once upon a time",
  "max_tokens": 50,
  "temperature": 0.7
}
```

**Response:**
```json
{
  "id": "cmpl-123",
  "object": "text_completion",
  "created": 1677652288,
  "model": "gpt-3.5-turbo-instruct",
  "choices": [{
    "text": " there was a brave knight...",
    "index": 0,
    "logprobs": null,
    "finish_reason": "length"
  }],
  "usage": {
    "prompt_tokens": 4,
    "completion_tokens": 8,
    "total_tokens": 12
  }
}
```

## Protocol Conversion

All OpenAI API requests are automatically converted to the gateway's canonical format and routed to the appropriate upstream provider (OpenAI, Claude, or Gemini). The gateway handles all protocol differences transparently, so you can use the OpenAI API format regardless of which upstream provider you're using.

## Authentication

All endpoints require authentication via the `Authorization` header:

```
Authorization: Bearer sk-gw-YOUR_API_KEY
```

## Streaming

The Chat Completions and Responses APIs support streaming responses by setting `"stream": true` in the request. The response will be sent as Server-Sent Events (SSE) with the following format:

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Error Responses

Error responses follow the OpenAI error format:

```json
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

## Rate Limiting

Rate limiting is handled by the upstream providers. The gateway forwards rate limit information in the response headers:

- `X-RateLimit-Limit-Requests`: Maximum number of requests
- `X-RateLimit-Limit-Tokens`: Maximum number of tokens
- `X-RateLimit-Remaining-Requests`: Remaining requests
- `X-RateLimit-Remaining-Tokens`: Remaining tokens
- `X-RateLimit-Reset-Requests`: Time until request limit resets
- `X-RateLimit-Reset-Tokens`: Time until token limit resets
