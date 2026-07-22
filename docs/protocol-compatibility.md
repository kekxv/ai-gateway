# Protocol compatibility

## Routing and pass-through rules

The inbound protocol is determined by the endpoint. Model canonical names and enabled aliases are
resolved before routing. For HTTP/SSE, a route may use any of the three provider protocols and the
gateway converts through its canonical model. For WebSockets, the selected route must use the same
protocol as the endpoint.

When inbound and outbound HTTP protocols match, the native JSON is passed through with the model
rewritten to `ModelRoute.upstream_model`; native provider errors can also be returned in their
original shape. This is semantic JSON pass-through: all parsed fields are preserved except the
model rewrite, but whitespace, object-key order, and duplicate-key behavior are not byte-preserved.
The gateway deliberately parses and re-encodes JSON instead of doing unsafe byte replacement.
Cross-protocol requests/responses and every cross-protocol stream are mapped as described below.

## Request field mapping

| Canonical meaning | OpenAI | Claude | Gemini | Notes/losses |
|---|---|---|---|---|
| Model | `model` | `model` | URL `models/{model}` | Always rewritten to the selected route's upstream model |
| System instruction | `system`/`developer` messages | `system` | `systemInstruction.parts` | Cross-protocol conversion can lose the distinction/order between OpenAI `system` and `developer` roles |
| Conversation | `messages[]` | `messages[]` | `contents[]` | User/assistant map to user/assistant/model; unsupported roles are rejected |
| Text | string or text content parts | text blocks/string | `parts[].text` | Text content is preserved; target-native wrapper shape changes |
| Image | `image_url` content part | image source block | `inlineData`/`fileData` | URL/media-type/base64 representations map where target supports them; provider-specific image options may be omitted |
| Tool definition | `tools[].function` | `tools[]` | `tools[].functionDeclarations` | Function name, description, and JSON input schema map; vendor extensions are not portable |
| Tool call | assistant `tool_calls[]` | `tool_use` block | `functionCall` part | IDs/names/JSON arguments map; targets that synthesize IDs may not preserve the original ID exactly |
| Tool result | `role=tool` + `tool_call_id` | `tool_result` block | `functionResponse` part | Text/structured result maps; provider-only status/cache metadata may be lost |
| Tool choice | `auto`/`none`/`required`/function | `auto`/`any`/`tool` | function-calling mode/config | Only the common intent is portable; parallel/allowed-function nuances can be lossy |
| Sampling | `temperature`, `top_p` | `temperature`, `top_p` | `generationConfig.temperature/topP` | Numeric values map directly when accepted by the target provider |
| Output limit | `max_completion_tokens` or `max_tokens` | `max_tokens` | `generationConfig.maxOutputTokens` | Maps to a single canonical maximum |
| Stop strings | `stop` | `stop_sequences` | `generationConfig.stopSequences` | String/list syntax is normalized |
| Streaming | `stream` | `stream` | streaming endpoint | Gateway forces stream mode for Gemini's stream endpoint |

Unknown fields are retained as protocol-scoped metadata when an adapter can safely round-trip
them. They are not promised to appear on a different protocol's wire representation.

## Response field mapping

| Canonical meaning | OpenAI | Claude | Gemini | Notes/losses |
|---|---|---|---|---|
| Response ID | `id` | `id` | `responseId` | A gateway default may be synthesized if the source omits an ID |
| Model | `model` | `model` | `modelVersion` | Reflects the provider response/upstream model, not necessarily the inbound alias |
| Assistant content | `choices[0].message` | `content` | `candidates[0].content.parts` | Text/tool calls map; native wrapper metadata may be omitted |
| Finish reason | `stop`, `length`, `tool_calls`, `content_filter` | `end_turn`, `max_tokens`, `tool_use`, `stop_sequence` | `STOP`, `MAX_TOKENS`, `SAFETY`, and related values | Common stop/length/tool/safety intents map; provider-specific reasons fall back to a generic representation |
| Usage | `prompt_tokens`, `completion_tokens` | `input_tokens`, `output_tokens` | `promptTokenCount`, `candidatesTokenCount` | Provider counts are preferred; absent counts are estimated and marked `estimated` in audit data |

Cross-protocol response adapters currently require one OpenAI choice or one Gemini candidate.
Multi-choice semantics have no common representation and are rejected rather than silently
mis-billed.

## Streaming events

| Meaning | OpenAI SSE | Claude SSE | Gemini SSE |
|---|---|---|---|
| Start/model | initial chat chunk | `message_start` | first candidate snapshot |
| Text delta | `choices[].delta.content` | `content_block_delta` / `text_delta` | candidate `parts[].text` snapshot converted to a delta |
| Tool call | incremental `tool_calls` | content block start/delta/stop | `functionCall` part |
| Finish | chunk `finish_reason` | `message_delta` then `message_stop` | candidate `finishReason` |
| Usage | final usage-only chunk | start/delta usage fields | `usageMetadata` |
| End marker | `[DONE]` | `message_stop` | end of SSE response |

The stream decoder is stateful: fragmented TCP chunks, cumulative Gemini snapshots, incremental
tool arguments, and usage-only frames are assembled before target encoding. Cross-protocol
conversion does not preserve exact source chunk boundaries, event names, event IDs, retry fields,
or timing. Content order, tool-call index, terminal reason, and billable usage are preserved where
the source provides them.

## WebSocket compatibility

| Endpoint | Required route protocol | Model source | Relay behavior |
|---|---|---|---|
| `/v1/realtime` | OpenAI | `?model=` or OpenAI session frame | Allows `realtime`/`openai-realtime-v1` subprotocols |
| `/v1beta/live` | Gemini | `?model=` or first `setup.model` frame | Allows `gemini-live` subprotocol |

For both endpoints:

- Every query/setup/session-update model value is rewritten to `upstream_model`; a later client
  frame cannot switch the selected route or leak an alias/other canonical model upstream.
- Gateway API credentials in headers, query keys, and credential-like subprotocols are stripped.
- Provider auth and configured extra headers are injected.
- Text/binary frames and normal close code/reason are relayed; ping/pong is handled by the
  WebSocket library.
- Native usage messages drive billing when available. Otherwise conservative text/audio metadata
  estimates are used and identified as estimated usage.

There is no OpenAI Realtime ↔ Gemini Live conversion, no audio transcoding, and no attempt to map
provider-specific session configuration between WebSocket protocols.

## Model listing

`GET /v1/models` returns canonical names and enabled aliases that have an eligible OpenAI route.
`GET /v1beta/models` does the same for eligible Gemini routes. Alias entries include their
canonical model in gateway metadata. API-key provider/model scopes are applied before listing.
Listings intentionally correlate with the entry protocol for discoverability; an HTTP request may
still route to and convert for another provider protocol after selecting one of the listed names.
