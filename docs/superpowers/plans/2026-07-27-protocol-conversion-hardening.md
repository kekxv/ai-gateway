# Protocol Conversion Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make system/developer instructions, function calls/results, and image/resource conversion correct and explicitly reject non-portable content instead of emitting invalid target payloads.

**Architecture:** Keep the existing native JSON → canonical model → target JSON pipeline. Tighten protocol adapters at their decode/encode boundaries, retain OpenAI instruction-role descriptors in protocol-scoped metadata, and define a tested portable resource subset: text, function tools, and user image URLs/base64 images. Native same-protocol Responses pass-through remains unrestricted; conversion paths return `UnsupportedFeatureError` for unsupported files, audio, documents, image controls, or tool-result media.

**Tech Stack:** Python 3.12, dataclasses, orjson, pytest, Ruff, mypy.

## Global Constraints

- Native OpenAI Responses routes with `supports_responses=true` must continue to pass request/response/SSE payloads through, changing only the selected upstream model.
- Responses converts to Chat Completions only for OpenAI routes with `supports_responses=false`; cross-provider conversion continues to use the canonical adapters.
- Do not silently reinterpret audio, PDF, document, or generic file data as an image.
- Do not emit source-only image quality fields into Claude or Gemini payloads.
- Preserve the existing untracked `docs/superpowers/plans/2026-07-27-openai-endpoint-compatibility.md` file outside this worktree; do not modify or commit it.

---

### Task 1: Enforce the portable image boundary

**Files:**
- Modify: `src/ai_gateway/protocols/base.py`
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `src/ai_gateway/protocols/claude.py`
- Modify: `src/ai_gateway/protocols/gemini.py`
- Modify: `tests/contract/fixtures/openai/request.json`
- Modify: `tests/contract/fixtures/claude/request.json`
- Modify: `tests/contract/fixtures/gemini/request.json`
- Create: `tests/contract/protocols/test_resource_conversion.py`

**Interfaces:**
- Produces: `image_media_type(value: Any, field: str, *, required: bool) -> str | None` in `protocols.base`.
- Produces: adapters that only decode explicit `image/*` media as `ImagePart` and reject target-incompatible image controls/types.

- [ ] **Step 1: Write failing tests for non-image MIME and target-only detail controls**

```python
@pytest.mark.parametrize("part", [
    {"inlineData": {"mimeType": "audio/wav", "data": "eA=="}},
    {"fileData": {"mimeType": "application/pdf", "fileUri": "https://example.test/a.pdf"}},
])
def test_gemini_non_image_resources_are_not_decoded_as_images(part): ...

@pytest.mark.parametrize("target", ["claude", "gemini"])
def test_openai_image_detail_is_rejected_when_target_cannot_represent_it(target): ...
```

- [ ] **Step 2: Run the focused tests and verify they fail for the current misclassification/emission behavior**

Run: `uv run pytest tests/contract/protocols/test_resource_conversion.py -q`

- [ ] **Step 3: Add shared image MIME validation and tighten all three adapters**

Validate explicit base64/file MIME values as `image/*`; require Gemini `fileData.mimeType` before canonical conversion; validate target-supported base64 media types; reject non-null canonical image `detail` in Claude/Gemini encoders; stop decoding or emitting the non-native Claude/Gemini `detail` field.

- [ ] **Step 4: Correct the portable 3×3 fixtures**

Remove the synthetic `detail` field from Claude/Gemini fixtures and the `detail=high` field from the common OpenAI fixture. Keep URL and base64 images in every fixture, and cover OpenAI detail separately with the rejection test.

- [ ] **Step 5: Run resource and 3×3 tests**

Run: `uv run pytest tests/contract/protocols/test_resource_conversion.py tests/contract/protocols/test_cross_conversion.py -q`

### Task 2: Preserve OpenAI Responses instruction roles in Chat fallback

**Files:**
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `tests/contract/protocols/test_openai_responses.py`
- Modify: `tests/contract/gateway/test_openai_operations.py`

**Interfaces:**
- Produces: `_decode_responses_input(...)` metadata descriptors compatible with OpenAI Chat's existing `__system_messages__` encoder scope.

- [ ] **Step 1: Write a failing adapter test with ordered `system` and `developer` input messages**

```python
def test_responses_fallback_preserves_system_and_developer_roles():
    request = adapter.decode_responses_request(payload)
    encoded = adapter.encode_request(request)
    assert [message["role"] for message in encoded["messages"][:3]] == [
        "system", "system", "developer"
    ]
```

- [ ] **Step 2: Run the test and verify current fallback collapses all instructions into one system message**

Run: `uv run pytest tests/contract/protocols/test_openai_responses.py -q`

- [ ] **Step 3: Record instruction descriptors during Responses decoding**

Treat string `instructions` as one system descriptor, retain each explicit input message's `system` or `developer` role and part count, and attach the descriptors through the existing OpenAI `__system_messages__` vendor scope.

- [ ] **Step 4: Add gateway-level fallback coverage**

Assert an OpenAI route with `supports_responses=false` receives separate ordered system/developer Chat messages, while a native Responses route remains unchanged.

- [ ] **Step 5: Run adapter and gateway fallback tests**

Run: `uv run pytest tests/contract/protocols/test_openai_responses.py tests/contract/gateway/test_openai_operations.py -q`

### Task 3: Make tool-result resource behavior protocol-correct

**Files:**
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `tests/contract/protocols/test_resource_conversion.py`
- Modify: `tests/contract/protocols/test_openai_responses.py`

**Interfaces:**
- Produces: OpenAI Chat tool-result decoding/encoding restricted to text parts.
- Produces: Responses `function_call_output` parsing that preserves text arrays and rejects unsupported file/audio content explicitly.

- [ ] **Step 1: Write failing tests for image tool messages and Responses file outputs**

```python
def test_openai_chat_tool_messages_reject_image_content_on_decode(): ...
def test_openai_chat_tool_messages_reject_image_content_on_encode(): ...
def test_responses_function_output_text_parts_convert_to_chat_tool_text(): ...
def test_responses_input_file_is_explicitly_nonportable(): ...
```

- [ ] **Step 2: Verify the tests expose image acceptance and array stringification**

Run: `uv run pytest tests/contract/protocols/test_resource_conversion.py tests/contract/protocols/test_openai_responses.py -q`

- [ ] **Step 3: Restrict Chat tool results and parse portable Responses tool output**

Require `TextPart` only for OpenAI `role=tool`; parse a Responses output string or text-only content list into canonical text parts; reject `input_file`, `input_audio`, and non-portable output resources with field-specific `UnsupportedFeatureError` messages.

- [ ] **Step 4: Run strict tool/resource contract tests**

Run: `uv run pytest tests/contract/protocols/test_resource_conversion.py tests/contract/protocols/test_strict_contracts.py tests/contract/protocols/test_openai_responses.py -q`

### Task 4: Document the exact conversion contract and verify the repository

**Files:**
- Modify: `docs/protocol-compatibility.md`
- Test: `tests/contract/protocols/`
- Test: `tests/contract/gateway/`

**Interfaces:**
- Produces: an explicit support matrix for instruction roles, function tools/results, images, files/audio/documents, and native pass-through.

- [ ] **Step 1: Update compatibility documentation**

Document that system/developer distinctions are preserved only on OpenAI→OpenAI Chat fallback, flatten across Claude/Gemini, image URL/base64 is the portable multimodal subset, OpenAI detail is not portable, OpenAI Chat tool results are text-only, and file/audio/document content requires native pass-through.

- [ ] **Step 2: Run focused protocol and gateway suites**

Run: `uv run pytest tests/contract/protocols tests/contract/gateway -q`

- [ ] **Step 3: Run repository verification**

Run: `uv run ruff check .`

Run: `uv run mypy`

Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -q`

- [ ] **Step 4: Review the diff and commit the isolated branch**

```bash
git diff --check
git status --short
git add docs/protocol-compatibility.md docs/superpowers/plans/2026-07-27-protocol-conversion-hardening.md src/ai_gateway/protocols tests/contract
git commit -m "fix: harden protocol resource conversion"
```
