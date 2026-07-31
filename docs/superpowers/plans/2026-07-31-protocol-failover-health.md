# Protocol Failover and Effective Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cross-protocol requests choose a stable compatible protocol, fail over when a successful HTTP response cannot be converted, audit the malformed response safely, and show effective route availability in the console.

**Architecture:** Keep model routes provider-scoped and add an explicit protocol fallback order when the inbound protocol is unavailable. Validate non-streaming upstream responses inside the bounded failover loop so health success occurs only after conversion, while malformed responses are health failures and their final raw response is carried to the existing redacting audit boundary. Derive console availability from route, provider, and enabled-provider-protocol state without changing persisted circuit-breaker state.

**Tech Stack:** Python 3.12, FastAPI, HTTPX, SQLAlchemy, pytest, Vue 3, TypeScript, Vitest.

## Global Constraints

- Preserve same-protocol byte-for-byte passthrough behavior.
- Keep retries bounded by distinct model routes; a malformed response may fail over to another provider route but must not loop through the same route's protocols.
- Never expose upstream credentials or unredacted malformed response content in attempt summaries or public errors.
- Preserve unrelated dashboard changes already present in the dirty worktree.
- Do not create commits unless the user explicitly requests them.

---

### Task 1: Stable cross-protocol fallback selection

**Files:**
- Modify: `src/ai_gateway/routing/service.py:471-490`
- Test: `tests/unit/routing/test_weighted.py`

**Interfaces:**
- Consumes: `Router.select_route(..., preferred_protocol=Protocol)` and provider protocol rows.
- Produces: `_protocol_preference(protocol, preferred_protocol) -> tuple[int, int]`, used when one provider exposes multiple enabled protocols.

- [ ] **Step 1: Write the failing test**

```python
async def test_conversion_fallback_prefers_openai_over_protocol_creation_order(session):
    model, route = await _add_route(session, suffix="fallback-order", protocol=Protocol.CLAUDE)
    openai = ProviderProtocol(
        provider_id=route.provider_id,
        protocol=Protocol.OPENAI,
        base_url="https://openai.provider.invalid/v1",
    )
    session.add(openai)
    await session.flush()

    selected = await Router(session).select_route(
        model,
        principal(),
        preferred_protocol=Protocol.GEMINI,
    )

    assert selected.provider_protocol_id == openai.id
    assert selected.protocol is Protocol.OPENAI
```

- [ ] **Step 2: Run the focused test and confirm it fails by selecting Claude**

Run: `uv run pytest tests/unit/routing/test_weighted.py::test_conversion_fallback_prefers_openai_over_protocol_creation_order -v`

- [ ] **Step 3: Implement the minimal stable order**

Use native protocol first, then `OPENAI`, `CLAUDE`, `GEMINI`, and finally protocol-row ID as a deterministic tie breaker. Do not alter weighted selection between provider routes.

- [ ] **Step 4: Run routing tests**

Run: `uv run pytest tests/unit/routing/test_weighted.py -v`

### Task 2: Validate responses before recording health success

**Files:**
- Modify: `src/ai_gateway/gateway/service.py:88-1110`
- Test: `tests/contract/gateway/test_non_streaming.py`

**Interfaces:**
- Consumes: `_convert_response(...)` and `_send_with_failover(...)`.
- Produces: `_ConvertedResponse` carried by `_AttemptResponse`; `UpstreamError.upstream_headers` and `UpstreamError.upstream_body` for final audit recording.

- [ ] **Step 1: Write the malformed-response failover test**

```python
async def test_cross_protocol_invalid_response_penalizes_route_and_fails_over(session):
    # First route returns HTTP 200 with a non-Claude response; second route returns valid OpenAI.
    # Assert the client receives Gemini 200, first route is a health failure, only the second route
    # is a health success, both route IDs appear in attempts, and no malformed secret is exposed.
```

- [ ] **Step 2: Write the final malformed-response audit test**

```python
async def test_final_cross_protocol_invalid_response_is_audited_without_health_success(session):
    # A single Claude route returns HTTP 200 with {"secret": "malformed"}.
    # Assert gateway 502, router.failures contains the route, router.successes is empty,
    # RequestFailure.body is the raw upstream bytes, headers include content-type, and attempts
    # contain only sanitized invalid_response metadata.
```

- [ ] **Step 3: Run both tests and confirm the current implementation fails**

Run: `uv run pytest tests/contract/gateway/test_non_streaming.py -k 'cross_protocol_invalid_response' -v`

- [ ] **Step 4: Move non-stream conversion into bounded failover**

For HTTP statuses below 400, call `_convert_response` before `record_success`. On conversion failure, replace the attempt outcome with `failure`, add `error_code="invalid_response"`, record a health failure using `RouteFailure(status_code=502, error_code="invalid_response")`, close the response, and continue to a distinct route. Return converted output with the successful attempt so the main handler does not decode twice.

- [ ] **Step 5: Preserve malformed response context for the final audit**

Carry only the final upstream headers and body on `UpstreamError`; have `_cleanup_after_failure` pass them to `RequestFailure`. Attempt summaries remain identifier/status/error-code only and the real `AuditService` continues to redact body/header secrets.

- [ ] **Step 6: Run non-streaming contract tests**

Run: `uv run pytest tests/contract/gateway/test_non_streaming.py -v`

### Task 3: Display effective route availability

**Files:**
- Modify: `frontend/src/components/models/ModelCard.vue:45-109,289-405`
- Test: `frontend/tests/routes.spec.ts`

**Interfaces:**
- Consumes: `ModelRouteResponse.provider_id`, `ProviderResponse.enabled`, and `ProviderProtocolResponse.enabled`.
- Produces: `routeIsEffectivelyEnabled(route)` and `routeIsAvailable(route)` for summary counts and route presentation.

- [ ] **Step 1: Write the failing console test**

```typescript
it('供应商停用时不把所属路由计为有效启用或可用', async () => {
  // Return one closed route owned by an enabled provider and one closed route owned by a
  // disabled provider. Assert the model card reads “1/2 有效启用” and “1/2 可用”, and the
  // disabled-provider route is visually disabled while retaining its circuit-breaker label.
})
```

- [ ] **Step 2: Run the focused frontend test and confirm the current 2/2 counts fail**

Run: `cd frontend && npm test -- routes.spec.ts -t '供应商停用时不把所属路由计为有效启用或可用'`

- [ ] **Step 3: Implement effective availability helpers**

A route is effectively enabled only when the route is enabled, its provider is enabled, and that provider has at least one enabled protocol. It is available only when effectively enabled and `runtime_state === 'closed'`. Use these helpers for counts and disabled styling, while continuing to show the stored circuit state separately.

- [ ] **Step 4: Run frontend route tests**

Run: `cd frontend && npm test -- routes.spec.ts`

### Task 4: Full verification

**Files:**
- Verify only; no new production files.

**Interfaces:**
- Consumes: all preceding behavior.
- Produces: fresh evidence for the completed change.

- [ ] **Step 1: Run backend focused suites**

Run: `uv run pytest tests/unit/routing/test_weighted.py tests/contract/gateway/test_non_streaming.py -v`

- [ ] **Step 2: Run backend static checks**

Run: `uv run ruff check src tests && uv run mypy src`

- [ ] **Step 3: Run frontend verification**

Run: `cd frontend && npm test -- routes.spec.ts && npm run typecheck && npm run lint && npm run build`

- [ ] **Step 4: Review the diff and requirement checklist**

Confirm stable OpenAI fallback, post-conversion health success, malformed-response failure/failover/audit coverage, effective UI counts, no secret-bearing attempt metadata, and no changes to the user's unrelated dashboard files.
