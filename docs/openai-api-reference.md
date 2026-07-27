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

OpenAI provider protocols default to native Responses support. On such routes, the gateway calls
the upstream `/v1/responses` endpoint, changes only the model alias in the request JSON, and
forwards non-streaming response bytes or streaming SSE bytes unchanged. This preserves stateful
fields, built-in tools, vendor events, event IDs, and other native OpenAI features.

Set `supports_responses=false` only for an OpenAI-compatible provider that exposes Chat
Completions but not Responses. That route uses `/v1/chat/completions` and converts the portable
subset. Claude and Gemini routes use the same portable conversion path. Portable conversion
supports string/message input, text and image content, function tools, function calls/results,
tool choice, sampling controls, output limits, and streaming equivalents. Stateful fields such as
`previous_response_id` and `conversation`, background execution, and built-in tools return
`422 unsupported_feature` on converted routes before an upstream request is sent.

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
      "id": "fc_123",
      "call_id": "call_123",
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

When `stream: true` is set, native Responses routes preserve the upstream SSE bytes. Converted
routes synthesize official Responses events. Every converted event has an SSE `event:` name that
matches its JSON `type`, a monotonically increasing `sequence_number`, and the required response,
item, output, and content identifiers. A shortened text sequence looks like this:

```text
event: response.created
data: {"type":"response.created","sequence_number":0,"response":{"id":"resp_...","object":"response","status":"in_progress","output":[]}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":4,"response_id":"resp_...","item_id":"msg_...","output_index":0,"content_index":0,"delta":"Hello"}

event: response.output_text.done
data: {"type":"response.output_text.done","sequence_number":5,"response_id":"resp_...","item_id":"msg_...","output_index":0,"content_index":0,"text":"Hello"}

event: response.completed
data: {"type":"response.completed","sequence_number":8,"response":{"id":"resp_...","object":"response","status":"completed","output":[{"type":"message","id":"msg_...","role":"assistant","status":"completed","content":[{"type":"output_text","text":"Hello","annotations":[]}]}],"usage":{"input_tokens":9,"output_tokens":1,"total_tokens":10}}}
```

### Embeddings API

**Endpoint:** `POST /v1/embeddings`

Generate text embeddings for RAG (Retrieval-Augmented Generation) and vector operations.

This endpoint requires an eligible OpenAI provider protocol and calls the upstream
`/v1/embeddings` endpoint. The gateway rewrites the model alias but does not convert the request or
response to Chat, Claude, or Gemini.

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

This endpoint requires an eligible OpenAI provider protocol and calls the upstream
`/v1/completions` endpoint. It is not rewritten as Chat Completions.

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

Chat Completions can be converted among OpenAI, Claude, and Gemini routes. Responses uses native
OpenAI pass-through whenever the selected OpenAI provider protocol has
`supports_responses=true` (the default); only explicit OpenAI fallback or a Claude/Gemini route
uses the portable conversion subset. Embeddings and Legacy Completions are OpenAI-only native
operations. Provider-specific fields outside a portable subset are not claimed to work across
protocols and return `422 unsupported_feature` when conversion would be unsafe.

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
