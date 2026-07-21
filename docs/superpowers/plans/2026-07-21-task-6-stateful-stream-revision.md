# Task 6 Stateful Stream Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all protocol stream conversions correct across complete incremental sequences while closing the re-review's validation and extension-retention gaps.

**Architecture:** Add explicit decoder and encoder context objects created by each adapter and retained by the streaming orchestrator. Stateless adapter methods remain compatibility conveniences that create a fresh context and therefore only promise single-frame conversion. Stateful contexts normalize native frames into canonical message/content/tool boundary events and encode those events while tracking open blocks, native indices, emitted starts/stops, tool identity, and Gemini tool-call history.

**Tech Stack:** Python 3.12, dataclasses, orjson, pytest, Ruff, mypy, Alembic/MySQL.

## Global Constraints

- Follow TDD and preserve reviewer RED evidence in `.superpowers/sdd/task-6-report.md`.
- Complete sequences must be tested incrementally for all nine source/target pairs.
- Same-protocol vendor extensions must round-trip; cross-protocol extensions must be omitted.
- Run focused and full tests with `-W error`, then Ruff, format check, mypy, and restore Alembic head.

---

### Task 1: Stateful stream contract and regression matrix

**Files:**
- Modify: `src/ai_gateway/protocols/base.py`
- Modify: `src/ai_gateway/protocols/types.py`
- Create: `tests/contract/protocols/test_stateful_stream_sequences.py`
- Modify: `tests/contract/protocols/test_cross_conversion.py`

**Interfaces:**
- Produces: `ProtocolAdapter.create_stream_decoder() -> StreamDecoder`
- Produces: `ProtocolAdapter.create_stream_encoder() -> StreamEncoder`
- Produces: `StreamDecoder.decode(event) -> tuple[StreamEvent, ...]`
- Produces: `StreamEncoder.encode(event) -> tuple[bytes, ...]`

- [ ] **Step 1: Write failing tests for full incremental source sequences and all nine target conversions**

Cover message start, repeated text deltas, parallel tool starts/fragments/stops, finish, usage, errors, and terminal events. Assert Claude start/delta/stop order and native indices; assert Gemini STOP remembers prior function calls.

- [ ] **Step 2: Run focused tests and record RED**

Run: `uv run pytest tests/contract/protocols/test_stateful_stream_sequences.py tests/contract/protocols/test_cross_conversion.py -W error -q`

- [ ] **Step 3: Add context abstractions and canonical content boundaries**

Add `content_start` to `StreamEventType`; keep `content_end`. Define stream decoder/encoder abstract interfaces and make adapter convenience methods instantiate a fresh context.

- [ ] **Step 4: Run the new tests to expose adapter-specific failures**

Run the same focused command and preserve the failure count in the report.

### Task 2: Stateful OpenAI, Claude, and Gemini sequences

**Files:**
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `src/ai_gateway/protocols/claude.py`
- Modify: `src/ai_gateway/protocols/gemini.py`
- Modify: `tests/contract/protocols/test_stream_events.py`
- Modify: `tests/contract/protocols/test_stateful_stream_sequences.py`

**Interfaces:**
- Consumes: the Task 1 stream context interfaces.
- Produces: complete canonical sequences with stable content/tool indices and complete target-native sequences.

- [ ] **Step 1: Implement OpenAI state**

Track emitted message/text starts, OpenAI `tool_call.index`, active tool IDs/names, content stops, and stream envelope/choice/delta extensions.

- [ ] **Step 2: Implement Claude state**

Decode `input={}` tool starts without emitting `"{}"`; encode text/tool starts before deltas and stops before message end; accept partial JSON for Claude targets and preserve content block indices.

- [ ] **Step 3: Implement Gemini state**

Assign stable part positions, remember prior function calls so later STOP maps to canonical `tool_call`, and buffer partial canonical tool arguments only when Gemini is the target.

- [ ] **Step 4: Run sequence and legacy stream tests**

Run: `uv run pytest tests/contract/protocols/test_stateful_stream_sequences.py tests/contract/protocols/test_stream_events.py tests/contract/protocols/test_cross_conversion.py -W error -q`

### Task 3: Extension retention and strict validation

**Files:**
- Modify: `src/ai_gateway/protocols/base.py`
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `src/ai_gateway/protocols/claude.py`
- Modify: `src/ai_gateway/protocols/gemini.py`
- Modify: `tests/contract/protocols/test_nested_extensions.py`
- Modify: `tests/contract/protocols/test_strict_contracts.py`

**Interfaces:**
- Consumes: protocol-scoped `vendor_metadata`, `add_vendor_scope`, and `vendor_scope` helpers.
- Produces: same-protocol preservation for OpenAI system/developer messages and choices, Gemini candidates, and stream envelope/choice/delta objects.

- [ ] **Step 1: Add failing independent extension tests**

Assert exact same-protocol nested restoration and explicit absence after cross-protocol conversion.

- [ ] **Step 2: Add failing strict-validation tests**

Reject non-text system content for OpenAI, Claude, and Gemini; unsupported OpenAI string `tool_choice`; boolean or negative token counts in request/response/stream usage fields.

- [ ] **Step 3: Implement scoped extension capture/restore and nonnegative integer validation**

Use a shared helper for token counts. Preserve source message/candidate/envelope structure only in the originating protocol metadata scopes.

- [ ] **Step 4: Run contract tests**

Run: `uv run pytest tests/contract/protocols -W error -q`

### Task 4: Verification, database restoration, report, and commit

**Files:**
- Modify: `.superpowers/sdd/task-6-report.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified revision commit and updated audit report.

- [ ] **Step 1: Run formatting and static checks**

Run `uv run ruff format src/ai_gateway/protocols tests/contract/protocols`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy`.

- [ ] **Step 2: Run focused and full suites**

Run `uv run pytest tests/contract/protocols -W error -q` and `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway' uv run pytest -W error`.

- [ ] **Step 3: Restore and verify the database**

Run Alembic stamp/upgrade/current with `GATEWAY_DATABASE_URL`, then confirm `0003 (head)` and 13 tables.

- [ ] **Step 4: Review and commit**

Run `git diff --check`, inspect status/stat, stage only Task 6 source/tests/plan, and commit with `fix: make protocol streams stateful`.

- [ ] **Step 5: Update the ignored report**

Record RED/GREEN counts, schema restoration, final commit hash, and remaining representability concerns.
