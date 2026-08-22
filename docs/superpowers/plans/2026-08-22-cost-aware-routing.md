# Cost-Aware Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route requests to the lowest provider cost multiplier first and fail over when a provider reports exhausted quota.

**Architecture:** The routing candidate projection will carry the provider cost multiplier. Selection will retain only the least-cost candidates before applying the existing weighted picker, so equal-cost routes retain configured traffic distribution. Gateway response classification will recognize the documented `403` error code `insufficient_user_quota`; that classification drives both retry/failover and route health accounting.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, httpx, pytest.

**Spec:** User request of 2026-08-22, including the observed upstream JSON error payload.

## Global Constraints

- Retain weights as the tie-breaker for routes with the same lowest cost multiplier.
- Do not treat arbitrary HTTP 403 responses as provider quota exhaustion.
- Keep upstream response body and headers available for normal error forwarding and audit.
- A quota exhaustion failure uses the existing route circuit breaker and failover mechanics.

---

### Task 1: Cost-ordered Candidate Selection

**Files:**
- Modify: `src/ai_gateway/routing/types.py`
- Modify: `src/ai_gateway/routing/service.py`
- Modify: `tests/unit/routing/test_weighted.py`
- Modify: `tests/unit/routing/test_candidate_projection.py`

**Interfaces:**
- Produces: `RouteCandidate.provider_cost_multiplier: Decimal`.
- Produces: `lowest_cost_candidates(candidates: Sequence[RouteCandidate]) -> list[RouteCandidate]`.

- [x] **Step 1: Write failing tests**

```python
async def test_router_selects_lowest_cost_before_weight(session: AsyncSession) -> None:
    # A high-weight route at 2.00 must lose to a low-weight route at 0.80.
    assert selected.route_id == low_cost_route.id
```

- [x] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/unit/routing/test_weighted.py tests/unit/routing/test_candidate_projection.py -q`
Expected: FAIL because candidates do not expose or select by provider cost.

- [x] **Step 3: Implement the smallest projection and selection change**

```python
minimum = min(candidate.provider_cost_multiplier for candidate in candidates)
return [candidate for candidate in candidates if candidate.provider_cost_multiplier == minimum]
```

- [x] **Step 4: Run focused tests and verify success**

Run: `pytest tests/unit/routing/test_weighted.py tests/unit/routing/test_candidate_projection.py -q`
Expected: PASS.

### Task 2: Quota-Exhaustion Failover and Circuit Breaker

**Files:**
- Modify: `src/ai_gateway/routing/health.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `tests/integration/routing/test_health.py`
- Modify: `tests/integration/gateway/test_failover.py`

**Interfaces:**
- Produces: `is_provider_quota_exhausted_response(response: httpx.Response) -> bool`.
- Produces: quota exhaustion classification that makes the 403 retryable and health-penalizing.

- [x] **Step 1: Write failing tests**

```python
def test_insufficient_user_quota_403_is_retryable_and_penalizing() -> None:
    response = httpx.Response(403, json={"error": {"code": "insufficient_user_quota"}})
    assert is_provider_quota_exhausted_response(response)
```

- [x] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/integration/routing/test_health.py tests/integration/gateway/test_failover.py -q`
Expected: FAIL because the current gateway returns the first 403 without retrying.

- [x] **Step 3: Implement minimal classification and failover**

```python
if is_provider_quota_exhausted_response(upstream):
    await router.record_failure(route.route_id, RouteFailure(status_code=403, error_code="insufficient_user_quota"))
    continue
```

- [x] **Step 4: Run focused tests and verify success**

Run: `pytest tests/integration/routing/test_health.py tests/integration/gateway/test_failover.py -q`
Expected: PASS.

### Task 3: End-to-End Verification

**Files:**
- Verify only.

- [x] **Step 1: Run formatting and static checks**

Run: `ruff check src tests && mypy src`
Expected: PASS.

- [x] **Step 2: Run affected test suite**

Run: `pytest tests/unit/routing tests/integration/routing/test_health.py tests/integration/gateway/test_failover.py -q`
Expected: PASS.
