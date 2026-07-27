# OpenAI Endpoint Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenAI Responses, Embeddings, and Legacy Completions route to their correct upstream endpoints, preserve native Responses traffic when supported, fall back to Chat Completions only when explicitly configured, and repair the Claude/Gemini boundary cases found during protocol review.

**Architecture:** Add an OpenAI Responses capability flag to each provider protocol and carry it into route candidates. Make the gateway operation-aware instead of treating every OpenAI HTTP request as Chat Completions: native Responses routes pass request, response, and SSE bytes through; explicitly incompatible OpenAI routes and non-OpenAI routes use the canonical conversion path. Embeddings and Legacy Completions require OpenAI routes and remain native pass-through operations, while the Responses canonical adapter gains a correct portable subset and a stateful official-shape stream encoder.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, httpx, orjson, pytest/pytest-asyncio, Vue 3, TypeScript, Vitest.

## Global Constraints

- Native OpenAI Responses traffic must be byte-preserving at the response/SSE layer and semantic-JSON preserving at the request layer except for model alias rewriting.
- `supports_responses` defaults to `true`; only an explicit `false` enables Responses-to-Chat fallback for an OpenAI provider protocol.
- Embeddings and Legacy Completions must never route to Claude or Gemini and must never be rewritten as Chat Completions.
- Cross-protocol Responses support is limited to portable messages, text/image input, function tools, tool calls/results, sampling, output limits, stop sequences, and streaming equivalents; unsupported stateful or built-in-tool features return `422 unsupported_feature` before contacting upstream.
- Every production behavior change follows red-green-refactor TDD.
- Preserve unrelated user changes and do not alter provider credentials or existing route weights.

---

## File Map

- `migrations/versions/0008_provider_protocol_supports_responses.py`: add the provider capability column with a safe default.
- `src/ai_gateway/db/models/catalog.py`: persist the capability.
- `src/ai_gateway/catalog/schemas.py`: expose the capability in provider create/update/read contracts.
- `src/ai_gateway/admin/providers.py`: create, update, and serialize the capability.
- `src/ai_gateway/routing/types.py`: carry the capability on selected routes.
- `src/ai_gateway/routing/service.py`: select the capability with route candidates.
- `frontend/src/api/types.ts`: type the provider capability.
- `frontend/src/components/providers/ProviderFormDrawer.vue`: allow administrators to mark OpenAI backends as not supporting Responses.
- `src/ai_gateway/gateway/openai.py`: identify the OpenAI operation at each endpoint.
- `src/ai_gateway/gateway/service.py`: make preparation, route filtering, upstream URL/body selection, response conversion, and stream handling operation-aware.
- `src/ai_gateway/protocols/openai.py`: separate Chat and Responses parsing/encoding and implement official Responses stream state.
- `src/ai_gateway/transport/sse.py`: choose passthrough versus Responses conversion from the selected operation/capability and observe native Responses usage.
- `src/ai_gateway/billing/usage.py`: read Responses and Embeddings usage shapes without guessing from Chat fields.
- `src/ai_gateway/protocols/claude.py`: guarantee a valid `max_tokens` when converting requests to Claude.
- `src/ai_gateway/protocols/gemini.py`: represent blocked prompts/candidates without rejecting valid Gemini responses.
- `tests/contract/gateway/test_openai_operations.py`: end-to-end request URL/body/response/SSE contracts for the three OpenAI operations.
- `tests/contract/protocols/test_openai_responses.py`: official-shape Responses request, response, and stream contracts.
- `tests/contract/protocols/test_claude.py`: required output-limit conversion regression.
- `tests/contract/protocols/test_gemini.py`: blocked prompt/candidate regressions.
- `tests/integration/admin/test_providers.py`: persistence and API coverage for the capability.
- `frontend/tests/providers.spec.ts`: form serialization and dirty-state coverage.
- `docs/protocol-compatibility.md`, `docs/openai-api-reference.md`, `README.md`, `README.zh-CN.md`: document exact native/fallback behavior and portable limits.

---

### Task 1: Provider Responses Capability

**Files:**
- Create: `migrations/versions/0008_provider_protocol_supports_responses.py`
- Modify: `src/ai_gateway/db/models/catalog.py`
- Modify: `src/ai_gateway/catalog/schemas.py`
- Modify: `src/ai_gateway/admin/providers.py`
- Modify: `src/ai_gateway/routing/types.py`
- Modify: `src/ai_gateway/routing/service.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/providers/ProviderFormDrawer.vue`
- Test: `tests/integration/migrations/test_0008_provider_protocol_supports_responses.py`
- Test: `tests/integration/admin/test_providers.py`
- Test: `tests/unit/routing/test_weighted.py`
- Test: `frontend/tests/providers.spec.ts`

**Interfaces:**
- Produces: `ProviderProtocol.supports_responses: bool`, `ProviderProtocolInput.supports_responses: bool`, `ProviderProtocolResponse.supports_responses: bool`, and `RouteCandidate.supports_responses: bool`.
- Default: `true` in database, backend schema, and frontend form.

- [ ] **Step 1: Write failing migration and API tests**

```python
async def test_0008_defaults_existing_provider_protocols_to_responses_supported(connection):
    await upgrade_to(connection, "0007")
    protocol_id = await insert_provider_protocol(connection, protocol="openai")
    await upgrade_to(connection, "0008")
    value = await connection.scalar(
        text("SELECT supports_responses FROM provider_protocols WHERE id=:id"),
        {"id": protocol_id},
    )
    assert value == 1


async def test_provider_api_persists_responses_capability(admin_client):
    response = await admin_client.post(
        "/admin/providers",
        json={
            "name": "legacy-openai",
            "protocols": [{
                "protocol": "openai",
                "base_url": "https://legacy.example/v1",
                "supports_responses": False,
            }],
        },
    )
    assert response.json()["protocols"][0]["supports_responses"] is False
```

- [ ] **Step 2: Run focused tests and verify expected schema/attribute failures**

Run:

```bash
uv run pytest tests/integration/migrations/test_0008_provider_protocol_supports_responses.py tests/integration/admin/test_providers.py -q
```

Expected: FAIL because the column and schema field do not exist.

- [ ] **Step 3: Add the migration, ORM field, schemas, admin mapping, and route projection**

```python
supports_responses: Mapped[bool] = mapped_column(
    Boolean,
    default=True,
    server_default=text("1"),
    nullable=False,
)
```

Include `ProviderProtocol.supports_responses` in `_candidate_query()` and `_candidate_from_row()`.

- [ ] **Step 4: Write failing frontend form tests**

```ts
it('submits an explicit Responses compatibility override for OpenAI protocols', async () => {
  const wrapper = mountProviderForm()
  await setProtocolSupportsResponses(wrapper, false)
  await submitProvider(wrapper)
  expect(lastSubmit().protocols?.[0]?.supports_responses).toBe(false)
})
```

- [ ] **Step 5: Implement the OpenAI-only switch and dirty comparison**

Add `supportsResponses` to `ProtocolRow`, show the switch only when `row.protocol === 'openai'`, and always normalize non-OpenAI rows to `true` so the flag has no effect outside OpenAI routing.

- [ ] **Step 6: Run backend/frontend focused tests**

```bash
uv run pytest tests/integration/migrations/test_0008_provider_protocol_supports_responses.py tests/integration/admin/test_providers.py tests/unit/routing/test_weighted.py -q
npm --prefix frontend test -- --run frontend/tests/providers.spec.ts
```

Expected: PASS.

---

### Task 2: Operation-Aware OpenAI Routing

**Files:**
- Modify: `src/ai_gateway/gateway/openai.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/transport/sse.py`
- Modify: `src/ai_gateway/billing/usage.py`
- Create: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Produces: `OpenAIOperation = Literal["chat_completions", "responses", "embeddings", "completions"]` stored on `_PreparedRequest` and `GatewayContext`.
- Extends: `upstream_url(..., openai_operation: OpenAIOperation = "chat_completions")`.
- Routing rule: embeddings/completions call `select_route(..., required_protocol=Protocol.OPENAI)`; Responses may select any HTTP protocol.

- [ ] **Step 1: Write failing native endpoint routing tests**

```python
@pytest.mark.parametrize(
    ("path", "expected_suffix"),
    [
        ("/v1/responses", "/v1/responses"),
        ("/v1/embeddings", "/v1/embeddings"),
        ("/v1/completions", "/v1/completions"),
    ],
)
async def test_native_openai_operation_uses_matching_upstream_path(
    gateway_client, fake_openai, path, expected_suffix
):
    response = await gateway_client.post(path, json=native_payload(path))
    assert response.status_code == 200
    assert fake_openai.requests[-1]["path"].endswith(expected_suffix)
    assert fake_openai.requests[-1]["json"]["model"] == "upstream-model"
```

Add assertions that Embeddings and Completions responses are byte-for-byte forwarded and that no Claude/Gemini route is selected.

- [ ] **Step 2: Run the new gateway tests and verify they fail on `/chat/completions`**

```bash
uv run pytest tests/contract/gateway/test_openai_operations.py -q
```

Expected: FAIL showing every operation reached `/v1/chat/completions` or was parsed as Chat.

- [ ] **Step 3: Introduce the operation enum and endpoint-specific preparation**

```python
@router.post("/v1/embeddings")
async def embeddings(...):
    return (
        await service.handle(
            request,
            Protocol.OPENAI,
            openai_operation="embeddings",
            required_protocol=Protocol.OPENAI,
        )
    ).response()
```

For Embeddings and Legacy Completions, create a minimal canonical billing request without applying the Chat schema. Preserve all native payload fields and only rewrite `model`.

- [ ] **Step 4: Implement operation-aware URLs and response/SSE passthrough**

```python
suffix = {
    "chat_completions": "chat/completions",
    "responses": "responses",
    "embeddings": "embeddings",
    "completions": "completions",
}[openai_operation]
return f"{base}/{suffix}" if base.endswith("/v1") else f"{base}/v1/{suffix}"
```

Do not invoke Chat response conversion for native Responses, Embeddings, or Completions.

- [ ] **Step 5: Add usage extraction tests and implementation**

```python
def test_responses_usage_uses_input_and_output_tokens():
    assert resolve_native_openai_usage(
        "responses",
        {"usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}},
    ) == CanonicalUsage(11, 7)


def test_embeddings_usage_has_zero_output_tokens():
    assert resolve_native_openai_usage(
        "embeddings",
        {"usage": {"prompt_tokens": 9, "total_tokens": 9}},
    ) == CanonicalUsage(9, 0)
```

- [ ] **Step 6: Run focused routing and billing tests**

```bash
uv run pytest tests/contract/gateway/test_openai_operations.py tests/unit/billing/test_usage.py -q
```

Expected: PASS.

---

### Task 3: Native Responses Passthrough and Explicit Chat Fallback

**Files:**
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/transport/sse.py`
- Modify: `src/ai_gateway/protocols/openai.py`
- Test: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Produces: `route_uses_native_responses(prepared, route) -> bool`.
- Native condition: inbound operation is Responses, outbound protocol is OpenAI, and `route.supports_responses is True`.
- Fallback condition: inbound operation is Responses, outbound protocol is OpenAI, and `route.supports_responses is False`.

- [ ] **Step 1: Write failing native Responses passthrough tests**

```python
async def test_supported_openai_route_preserves_responses_request_and_response(
    gateway_client, fake_openai_responses
):
    payload = {
        "model": "alias",
        "input": "hello",
        "instructions": "be concise",
        "previous_response_id": "resp_previous",
        "tools": [{"type": "web_search"}],
    }
    response = await gateway_client.post("/v1/responses", json=payload)
    upstream = fake_openai_responses.requests[-1]
    assert upstream["path"] == "/v1/responses"
    assert upstream["json"] == {**payload, "model": "upstream-model"}
    assert response.content == fake_openai_responses.native_response_bytes
```

Add an SSE variant asserting exact upstream bytes, including vendor events and event IDs.

- [ ] **Step 2: Run native passthrough tests and verify the current Chat endpoint/conversion failure**

```bash
uv run pytest tests/contract/gateway/test_openai_operations.py -k 'supported_openai_route' -q
```

Expected: FAIL because the current route targets Chat and re-encodes Responses.

- [ ] **Step 3: Implement native Responses selection before portable-feature validation**

Parse enough of the request for authentication, model resolution, billing estimation, and stream detection, but retain non-portable fields in protocol-scoped metadata. Only validate portability when the selected route needs conversion.

- [ ] **Step 4: Write failing explicit fallback tests**

```python
async def test_unsupported_openai_route_converts_portable_responses_request_to_chat(
    gateway_client, fake_legacy_openai
):
    response = await gateway_client.post(
        "/v1/responses",
        json={
            "model": "alias",
            "instructions": "be concise",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "max_output_tokens": 32,
        },
    )
    assert fake_legacy_openai.requests[-1]["path"] == "/v1/chat/completions"
    assert fake_legacy_openai.requests[-1]["json"] == {
        "model": "upstream-model",
        "messages": [
            {"role": "developer", "content": "be concise"},
            {"role": "user", "content": "hi"},
        ],
        "max_completion_tokens": 32,
        "stream": False,
    }
    assert response.json()["object"] == "response"
```

Add a test proving `previous_response_id` or a built-in tool returns 422 on a fallback route without making an upstream request.

- [ ] **Step 5: Implement fallback body/response selection**

Use the canonical Chat encoder only for `supports_responses=False`. Preserve native Responses response bytes when the capability is true; synthesize official Responses objects only for fallback or Claude/Gemini conversion.

- [ ] **Step 6: Run native/fallback tests**

```bash
uv run pytest tests/contract/gateway/test_openai_operations.py -k 'responses' -q
```

Expected: PASS.

---

### Task 4: Official Responses Portable Request and Non-Streaming Response Shapes

**Files:**
- Modify: `src/ai_gateway/protocols/openai.py`
- Create: `tests/contract/protocols/test_openai_responses.py`

**Interfaces:**
- Produces: `OpenAIAdapter.decode_responses_request(payload) -> CanonicalRequest`.
- Produces: `OpenAIAdapter.validate_responses_portability(request) -> None`.
- Produces: `OpenAIAdapter.encode_responses_api_response(response) -> dict[str, Any]` with official item IDs/status fields.

- [ ] **Step 1: Write failing official request-shape tests**

```python
def test_responses_request_maps_instructions_limit_images_and_flat_function_tools():
    request = OpenAIAdapter().decode_responses_request({
        "model": "gpt-test",
        "instructions": "be concise",
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "describe"},
                {"type": "input_image", "image_url": "https://example.test/a.png", "detail": "low"},
            ],
        }],
        "tools": [{
            "type": "function",
            "name": "lookup",
            "description": "lookup data",
            "parameters": {"type": "object", "properties": {}},
            "strict": True,
        }],
        "tool_choice": {"type": "function", "name": "lookup"},
        "max_output_tokens": 64,
    })
    assert request.system == (TextPart("be concise"),)
    assert request.max_output_tokens == 64
    assert request.tools[0].name == "lookup"
    assert request.tool_choice == {"name": "lookup"}
    assert isinstance(request.messages[0].content[1], ImagePart)
```

- [ ] **Step 2: Run request tests and verify failures on missing Chat-style nesting/input image handling**

```bash
uv run pytest tests/contract/protocols/test_openai_responses.py -k 'request' -q
```

Expected: FAIL on `instructions`, `max_output_tokens`, flat tool shape, or `input_image`.

- [ ] **Step 3: Implement the separate Responses decoder and portability markers**

Preserve `strict` and other native function fields in OpenAI-scoped metadata. Record non-portable features such as `previous_response_id`, conversations, built-in tools, background mode, and hosted tool outputs; native pass-through ignores these markers, converted routes reject them with the exact field path.

- [ ] **Step 4: Write failing response-shape tests**

```python
def test_length_response_is_incomplete_with_details():
    encoded = OpenAIAdapter().encode_responses_api_response(canonical_response("length"))
    assert encoded["status"] == "incomplete"
    assert encoded["incomplete_details"] == {"reason": "max_output_tokens"}


def test_tool_only_response_has_no_empty_message_item():
    encoded = OpenAIAdapter().encode_responses_api_response(tool_only_response())
    assert [item["type"] for item in encoded["output"]] == ["function_call"]
    assert encoded["output"][0]["id"].startswith("fc_")
    assert encoded["output"][0]["call_id"].startswith("call_")
```

- [ ] **Step 5: Implement official portable Response object fields**

Include stable `id`, `created_at`, `object`, `status`, `error`, `incomplete_details`, `instructions`, `max_output_tokens`, `model`, `output`, `parallel_tool_calls`, `previous_response_id`, `reasoning`, `store`, `temperature`, `text`, `tool_choice`, `tools`, `top_p`, `truncation`, `usage`, and `metadata` values where known or `null` where the official schema requires nullable fields.

- [ ] **Step 6: Run Responses protocol tests**

```bash
uv run pytest tests/contract/protocols/test_openai_responses.py -q
```

Expected: PASS.

---

### Task 5: Stateful Official Responses Streaming

**Files:**
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `src/ai_gateway/transport/sse.py`
- Test: `tests/contract/protocols/test_openai_responses.py`
- Test: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Produces: `_ResponsesAPIStreamEncoder.encode(StreamEvent) -> tuple[bytes, ...]` with monotonically increasing `sequence_number`.
- Maintains: response ID, message item/text content, one state record per function call, accumulated arguments, output indices, final usage, and terminal status.

- [ ] **Step 1: Write failing text stream contract**

```python
def test_responses_text_stream_has_sequence_and_complete_terminal_objects():
    events = encode_responses_stream(text_stream_events("Hello"))
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    delta = next(event for event in events if event["type"] == "response.output_text.delta")
    assert delta["response_id"].startswith("resp_")
    assert delta["item_id"].startswith("msg_")
    done = next(event for event in events if event["type"] == "response.content_part.done")
    assert done["part"]["text"] == "Hello"
    completed = events[-1]
    assert completed["response"]["output"][0]["content"][0]["text"] == "Hello"
```

- [ ] **Step 2: Run and verify failure on missing IDs/sequence and empty terminal text**

```bash
uv run pytest tests/contract/protocols/test_openai_responses.py -k 'text_stream' -q
```

Expected: FAIL.

- [ ] **Step 3: Implement text/message stream state**

Emit SSE frames with `event: <payload.type>` and matching JSON `type`. Increment `sequence_number` for every frame and build terminal message/output objects from accumulated content.

- [ ] **Step 4: Write failing parallel function stream contract**

```python
def test_responses_parallel_function_stream_tracks_each_output_item():
    events = encode_responses_stream(parallel_tool_events())
    added = [event for event in events if event["type"] == "response.output_item.added"]
    assert [event["output_index"] for event in added if event["item"]["type"] == "function_call"] == [0, 1]
    argument_done = [
        event for event in events if event["type"] == "response.function_call_arguments.done"
    ]
    assert [event["arguments"] for event in argument_done] == ['{"x":1}', '{"y":2}']
    assert len([event for event in events if event["type"] == "response.output_item.done"]) == 2
```

- [ ] **Step 5: Implement per-tool state and terminal events**

Use canonical `tool_index` when available; otherwise assign indices by first appearance. Emit each item-added event once, accumulate partial argument strings, then emit arguments-done and output-item-done before `response.completed`.

- [ ] **Step 6: Add gateway conversion stream test and run focused suite**

```bash
uv run pytest tests/contract/protocols/test_openai_responses.py tests/contract/gateway/test_openai_operations.py -k 'stream' -q
```

Expected: PASS.

---

### Task 6: Claude and Gemini Boundary Repairs

**Files:**
- Modify: `src/ai_gateway/protocols/claude.py`
- Modify: `src/ai_gateway/protocols/gemini.py`
- Modify: `src/ai_gateway/protocols/types.py`
- Test: `tests/contract/protocols/test_claude.py`
- Test: `tests/contract/protocols/test_gemini.py`
- Test: `tests/contract/protocols/test_cross_conversion.py`

**Interfaces:**
- Claude: converted requests always contain a positive `max_tokens`; use the gateway billing default passed through conversion context, or reject with an explicit field error if no configured default is available.
- Gemini: blocked prompts and content-less safety candidates decode into a canonical content-filter result without fabricating assistant text.

- [ ] **Step 1: Write failing Claude output-limit test**

```python
def test_openai_request_without_limit_encodes_valid_claude_max_tokens():
    canonical = OpenAIAdapter().decode_request({
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
    })
    encoded = ClaudeAdapter(default_max_output_tokens=4096).encode_request(canonical)
    assert encoded["max_tokens"] == 4096
```

- [ ] **Step 2: Run and verify `max_tokens` is absent**

```bash
uv run pytest tests/contract/protocols/test_claude.py -k 'without_limit' -q
```

Expected: FAIL.

- [ ] **Step 3: Implement an explicit conversion default without changing native Claude passthrough**

Keep native Claude requests untouched. Only canonical-to-Claude encoding supplies the configured default.

- [ ] **Step 4: Write failing Gemini blocked-response tests**

```python
def test_blocked_gemini_prompt_decodes_as_content_filter():
    response = GeminiAdapter().decode_response({
        "promptFeedback": {"blockReason": "SAFETY"},
        "usageMetadata": {"promptTokenCount": 3, "totalTokenCount": 3},
    })
    assert response.finish_reason == "content_filter"
    assert response.message.content == ()


def test_safety_candidate_without_content_decodes_as_content_filter():
    response = GeminiAdapter().decode_response({
        "candidates": [{"index": 0, "finishReason": "SAFETY", "safetyRatings": []}],
    })
    assert response.finish_reason == "content_filter"
    assert response.message.content == ()
```

- [ ] **Step 5: Implement blocked-response decoding and cross-protocol encoding**

Preserve `promptFeedback` and safety ratings in Gemini-scoped metadata. OpenAI/Claude targets emit an empty assistant result with the closest content-filter/refusal terminal reason.

- [ ] **Step 6: Run protocol and cross-conversion tests**

```bash
uv run pytest tests/contract/protocols/test_claude.py tests/contract/protocols/test_gemini.py tests/contract/protocols/test_cross_conversion.py -q
```

Expected: PASS.

---

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `docs/protocol-compatibility.md`
- Modify: `docs/openai-api-reference.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Documents: native Responses passthrough default, explicit Chat fallback flag, OpenAI-only Embeddings/Completions routing, and portable cross-protocol subset.

- [ ] **Step 1: Update documentation after behavior tests are green**

Document these exact rules:

```text
OpenAI provider protocols default to native Responses support. Set
supports_responses=false only for OpenAI-compatible backends that expose
Chat Completions but not Responses. Embeddings and Legacy Completions require
an eligible OpenAI route and are never converted to Claude or Gemini.
```

Remove claims that every vendor feature is transparently portable.

- [ ] **Step 2: Run backend formatting, lint, typing, and tests**

Use the commands declared by `pyproject.toml`; at minimum:

```bash
uv run ruff check src tests migrations
uv run mypy src
uv run pytest tests/unit tests/contract -q
```

Run database integration tests when `GATEWAY_TEST_DATABASE_URL` is available:

```bash
uv run pytest tests/integration -q
```

- [ ] **Step 3: Run frontend checks**

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

- [ ] **Step 4: Verify migration head and repository diff**

```bash
uv run alembic heads
git diff --check
git status --short
```

Expected: migration head `0008`, no whitespace errors, and only intended files changed.

- [ ] **Step 5: Perform the self-review checklist**

- Native Responses uses `/v1/responses` and preserves native response/SSE bytes.
- Explicit `supports_responses=false` uses `/v1/chat/completions` and only accepts portable fields.
- Embeddings uses `/v1/embeddings`, Completions uses `/v1/completions`, and both require OpenAI routes.
- Responses request fields, function tools, tool choice, input images, incomplete responses, sequence numbers, text accumulation, and parallel function calls have regression tests.
- Claude conversion always sends `max_tokens`.
- Gemini blocked prompts/candidates do not become upstream-invalid-response errors.
- README and compatibility docs match the implemented boundary.

