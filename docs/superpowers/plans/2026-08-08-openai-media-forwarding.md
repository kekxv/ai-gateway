# OpenAI Media Forwarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forward OpenAI audio, image, and embedding requests to eligible OpenAI upstream routes while preserving multipart file payloads and native responses.

**Architecture:** Extend the OpenAI router with the six native audio/image POST endpoints and route each to the existing gateway service as an OpenAI-only native operation. The gateway will parse JSON as it does today; for `multipart/form-data`, it will read only the `model` form part from the raw request bytes and replace that one part before forwarding, leaving each file part and the original boundary untouched. Native binary or JSON responses will be returned unchanged.

**Tech Stack:** Python 3.12, FastAPI, httpx, orjson, pytest, pytest-asyncio.

## Global Constraints

- Support `POST /v1/embeddings`, `/v1/audio/speech`, `/v1/audio/transcriptions`, `/v1/audio/translations`, `/v1/images/generations`, `/v1/images/edits`, and `/v1/images/variations`.
- The seven endpoints require an OpenAI provider protocol; no conversion to Claude or Gemini is attempted.
- Multipart requests must preserve every non-`model` byte, including uploaded file bytes, headers, CRLFs, and boundary delimiters.
- Do not add local file persistence, multipart body logging, or a multipart parsing dependency.
- Existing audit handling of non-JSON bodies remains metadata-only (byte length and SHA-256).

---

### Task 1: Specify native JSON and multipart forwarding behavior

**Files:**
- Modify: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Consumes: `GatewayService.handle(request, Protocol.OPENAI, endpoint_path, openai_operation, required_protocol=Protocol.OPENAI)`.
- Produces: regression coverage that asserts endpoint URL selection, model alias rewriting, native response preservation, and byte-for-byte multipart file preservation.

- [ ] **Step 1: Write the failing JSON-operation test**

```python
@pytest.mark.parametrize(
    ("path", "payload", "expected_suffix", "response_content_type"),
    [
        ("/v1/audio/speech", {"model": "alias", "input": "Hi", "voice": "alloy"}, "/v1/audio/speech", "audio/mpeg"),
        ("/v1/images/generations", {"model": "alias", "prompt": "a fox"}, "/v1/images/generations", "application/json"),
        ("/v1/embeddings", {"model": "alias", "input": "Hi"}, "/v1/embeddings", "application/json"),
    ],
)
async def test_openai_native_json_operations_forward_to_the_matching_openai_endpoint(...):
    response = await client.post(path, json=payload)
    assert seen[0].url.path.endswith(expected_suffix)
    assert orjson.loads(seen[0].content) == {**payload, "model": "upstream-model"}
    assert response.content == upstream_content
    assert response.headers["content-type"].startswith(response_content_type)
```

- [ ] **Step 2: Run the JSON-operation test to verify it fails**

Run: `uv run pytest tests/contract/gateway/test_openai_operations.py -q`

Expected: FAIL with 404 for at least `/v1/audio/speech` and `/v1/images/generations` because their router entries do not yet exist.

- [ ] **Step 3: Write the failing multipart-operation test**

```python
@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/v1/audio/transcriptions", "file"),
        ("/v1/audio/translations", "file"),
        ("/v1/images/edits", "image"),
        ("/v1/images/variations", "image"),
    ],
)
async def test_openai_native_multipart_operations_rewrite_only_the_model_part(...):
    multipart = _multipart_body(model="alias", file_field=field, file_bytes=b"\\x00raw-file\\xff")
    response = await client.post(path, content=multipart.body, headers={"content-type": multipart.content_type})
    assert seen[0].url.path.endswith(path)
    assert seen[0].headers["content-type"] == multipart.content_type
    assert seen[0].content == multipart.body.replace(b"\\r\\n\\r\\nalias\\r\\n", b"\\r\\n\\r\\nupstream-model\\r\\n")
    assert response.content == b'{"text":"transcribed"}'
```

- [ ] **Step 4: Run the multipart-operation test to verify it fails**

Run: `uv run pytest tests/contract/gateway/test_openai_operations.py -q`

Expected: FAIL with 404 because no audio/image multipart routes are registered.

### Task 2: Add native operation routing and raw multipart model rewriting

**Files:**
- Modify: `src/ai_gateway/gateway/openai.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Test: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Consumes: a FastAPI `Request` containing JSON or `multipart/form-data`, the client model alias, and an OpenAI `RouteCandidate`.
- Produces: `GatewayService.handle` support for `audio_speech`, `audio_transcriptions`, `audio_translations`, `images_generations`, `images_edits`, and `images_variations`; an upstream request whose model selector is the route's `upstream_model`.

- [ ] **Step 1: Add OpenAI-only route entries**

```python
async def _native_openai_operation(
    request: Request,
    service: GatewayService,
    endpoint_path: str,
    operation: OpenAIOperation,
) -> Response: ...

@router.post("/v1/audio/transcriptions")
async def audio_transcriptions(request: Request, service: Annotated[GatewayService, Depends(get_gateway_service)]) -> Response:
    return await _native_openai_operation(
        request, service, "/v1/audio/transcriptions", "audio_transcriptions"
    )
```

Implement the same helper-backed route shape for `/v1/audio/speech`, `/v1/audio/translations`, `/v1/images/generations`, `/v1/images/edits`, and `/v1/images/variations`; the helper passes `required_protocol=Protocol.OPENAI` and returns `native_error_response(Protocol.OPENAI, exc)` on failure.

- [ ] **Step 2: Extend native-operation endpoint selection**

```python
type OpenAIOperation = Literal[
    "chat_completions", "responses", "embeddings", "completions",
    "audio_speech", "audio_transcriptions", "audio_translations",
    "images_generations", "images_edits", "images_variations",
]

suffix = {
    "audio_speech": "audio/speech",
    "audio_transcriptions": "audio/transcriptions",
    "audio_translations": "audio/translations",
    "images_generations": "images/generations",
    "images_edits": "images/edits",
    "images_variations": "images/variations",
}[openai_operation]
```

Treat all of these as native OpenAI operations in request decoding, response conversion, usage extraction fallback, and outbound operation selection.

- [ ] **Step 3: Preserve multipart body bytes while rewriting `model`**

```python
def _rewrite_multipart_model(raw_body: bytes, content_type: str, upstream_model: str) -> bytes:
    boundary = _multipart_boundary(content_type)
    for part in _multipart_parts(raw_body, boundary):
        if part.name == "model" and part.filename is None:
            return raw_body[:part.content_start] + upstream_model.encode() + raw_body[part.content_end:]
    raise InvalidRequestError("A non-empty model is required")
```

Pass the inbound `Content-Type` into request preparation. For multipart requests, obtain the requested model from the raw `model` part and create the minimal native billing request from `{"model": normalized_model}`. In `_upstream_body`, route multipart OpenAI requests through `_rewrite_multipart_model` instead of JSON serialization. Reject malformed multipart data or absent/empty model fields with `InvalidRequestError`.

- [ ] **Step 4: Run the focused contract suite to verify both test groups pass**

Run: `uv run pytest tests/contract/gateway/test_openai_operations.py -q`

Expected: PASS with the native operations, multipart preservation, existing responses, embeddings, and completions tests all green.

- [ ] **Step 5: Run static checks**

Run: `uv run ruff check src/ai_gateway/gateway/openai.py src/ai_gateway/gateway/service.py tests/contract/gateway/test_openai_operations.py && uv run mypy src/ai_gateway/gateway/openai.py src/ai_gateway/gateway/service.py`

Expected: both commands exit 0.

- [ ] **Step 6: Commit the implementation and regression tests**

```bash
git add src/ai_gateway/gateway/openai.py src/ai_gateway/gateway/service.py tests/contract/gateway/test_openai_operations.py
git commit -m "feat: forward OpenAI audio and image APIs"
```

### Task 3: Document supported native OpenAI media APIs

**Files:**
- Modify: `docs/openai-api-reference.md`
- Test: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Consumes: the implemented OpenAI-only native operation behavior.
- Produces: user-facing endpoint and protocol restrictions for audio, images, and embeddings.

- [ ] **Step 1: Document the endpoints and multipart behavior**

```markdown
### Audio and Images APIs

The gateway forwards `/v1/audio/speech`, `/v1/audio/transcriptions`, `/v1/audio/translations`,
`/v1/images/generations`, `/v1/images/edits`, and `/v1/images/variations` only to eligible OpenAI
provider routes. JSON and multipart requests retain their native OpenAI shape; multipart file parts
are forwarded without local persistence and only the `model` field is rewritten to the configured
upstream model.
```

- [ ] **Step 2: Run the focused contract suite after the documentation change**

Run: `uv run pytest tests/contract/gateway/test_openai_operations.py -q`

Expected: PASS.

- [ ] **Step 3: Commit the documentation**

```bash
git add docs/openai-api-reference.md
git commit -m "docs: describe OpenAI media forwarding"
```

## Self-Review

- Spec coverage: Task 1 covers all seven requested OpenAI endpoint classes; Task 2 implements native OpenAI-only routing, raw multipart forwarding, model rewriting, native response preservation, and error handling; Task 3 documents the supported behavior.
- Placeholder scan: no implementation step uses TBD-style placeholders; every test and code step names exact files, commands, operations, and assertions.
- Type consistency: every router operation string appears in the `OpenAIOperation` literal and the endpoint suffix map; the multipart helper consumes `bytes`, `str`, and returns `bytes` for `_upstream_body`.
