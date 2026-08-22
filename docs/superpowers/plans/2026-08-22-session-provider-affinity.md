# Session Provider Affinity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep each detected CLI session on its current provider for one sliding hour, switching only when that provider is no longer eligible.

**Architecture:** A protocol-neutral extractor hashes native CLI session identifiers, with a first-user-message fingerprint fallback. A MySQL affinity table stores `api_key_id + affinity_hash -> provider_id` and expiry; the router tries the stored provider before normal cost-tier routing, and the gateway updates the binding only after an upstream request succeeds.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, MySQL 8.4, httpx, pytest.

**Spec:** User-provided Claude CLI and Codex ACP request headers in this conversation.

## Global Constraints

- Native identifiers take precedence: `x-claude-code-session-id`, `session-id`, `thread-id`, `x-opencode-session`, `prompt_cache_key`, then Codex turn metadata.
- Raw client session identifiers must never be stored in the database.
- Affinity is isolated by API key and expires after 3600 seconds of inactivity.
- A healthy bound provider wins over a newly cheaper provider.
- A manually or dynamically unavailable bound provider triggers normal cost-aware reassignment.
- A recovered old provider does not regain the session while the replacement remains eligible.
- Affinity persistence failure must not fail an otherwise valid model request.

---

### Task 1: Session Identity Extraction

**Files:**
- Create: `src/ai_gateway/routing/affinity.py`
- Create: `tests/unit/routing/test_affinity.py`

**Interfaces:**
- Produces: `session_affinity_hash(headers: Mapping[str, str], payload: Mapping[str, Any]) -> bytes | None`.

- [x] **Step 1: Write failing extraction tests**

```python
def test_claude_session_header_wins_over_prompt_fallback() -> None:
    result = session_affinity_hash(
        {"x-claude-code-session-id": "claude-session"},
        {"messages": [{"role": "user", "content": "hello"}]},
    )
    assert result == sha256(b"id:claude-session").digest()
```

- [x] **Step 2: Run tests and observe the missing module failure**

Run: `uv run pytest tests/unit/routing/test_affinity.py -q`
Expected: FAIL because `ai_gateway.routing.affinity` does not exist.

- [x] **Step 3: Implement native-ID precedence and prompt fallback**

```python
def session_affinity_hash(headers, payload):
    identifier = first_native_identifier(headers, payload)
    if identifier is not None:
        return sha256(f"id:{identifier}".encode()).digest()
    return first_user_message_hash(payload)
```

- [x] **Step 4: Run focused extraction tests**

Run: `uv run pytest tests/unit/routing/test_affinity.py -q`
Expected: PASS.

### Task 2: Persistent Sliding Affinity Store

**Files:**
- Create: `migrations/versions/0023_session_route_affinity.py`
- Create: `tests/unit/migrations/test_0023_session_route_affinity.py`
- Modify: `src/ai_gateway/main.py`
- Modify: `src/ai_gateway/core/config.py`
- Modify: `src/ai_gateway/db/models/identity.py`
- Modify: `src/ai_gateway/db/models/__init__.py`
- Modify: `tests/integration/test_schema.py`
- Modify: `tests/integration/test_startup.py`
- Modify: `src/ai_gateway/routing/affinity.py`
- Modify: `tests/integration/routing/test_affinity.py`

**Interfaces:**
- Produces: `SessionRouteAffinity` ORM model.
- Produces: `SessionAffinityStore.resolve(api_key_id: int, affinity_hash: bytes) -> int | None`.
- Produces: `SessionAffinityStore.bind(api_key_id: int, affinity_hash: bytes, provider_id: int) -> None`.

- [x] **Step 1: Write failing migration, schema, expiry, renewal, and rebinding tests**

```python
provider_id = await store.resolve(api_key_id, affinity_hash)
assert provider_id == original_provider_id
await store.bind(api_key_id, affinity_hash, replacement_provider_id)
assert await store.resolve(api_key_id, affinity_hash) == replacement_provider_id
```

- [x] **Step 2: Run focused tests and observe missing storage behavior**

Run: `uv run pytest tests/unit/migrations/test_0023_session_route_affinity.py tests/integration/routing/test_affinity.py -q`
Expected: FAIL before the migration/model/store exist.

- [x] **Step 3: Implement the migration, ORM model, setting, and store**

```python
class SessionRouteAffinity(Base):
    __tablename__ = "session_route_affinities"
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), primary_key=True)
    affinity_hash: Mapped[bytes] = mapped_column(BINARY(32), primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
```

- [x] **Step 4: Run focused storage tests**

Run: `uv run pytest tests/unit/migrations/test_0023_session_route_affinity.py tests/integration/routing/test_affinity.py -q`
Expected: PASS.

### Task 3: Affinity-Aware Routing and Gateway Binding

**Files:**
- Modify: `src/ai_gateway/routing/service.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `tests/unit/routing/test_weighted.py`
- Modify: `tests/integration/gateway/test_failover.py`

**Interfaces:**
- Extends: `Router.select_route(..., preferred_provider_id: int | None = None) -> RouteCandidate`.
- Consumes: `SessionAffinityStore.resolve` before initial selection.
- Consumes: `SessionAffinityStore.bind` after a successful upstream response.

- [x] **Step 1: Write failing sticky, failover, recovery, and expiry integration tests**

```python
first = await request(session_id="same")
second = await request(session_id="same")
assert first.provider_id == second.provider_id
```

- [x] **Step 2: Run focused routing tests and observe affinity is ignored**

Run: `uv run pytest tests/unit/routing/test_weighted.py tests/integration/gateway/test_failover.py -q`
Expected: FAIL because the preferred provider and affinity store are not consulted.

- [x] **Step 3: Implement preferred-provider pools and success-only binding**

```python
affinity_candidates = [item for item in candidates if item.provider_id == preferred_provider_id]
pools = [affinity_candidates, remaining_native, remaining_fallback]
```

- [x] **Step 4: Run the affected suite and static checks**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: PASS.
