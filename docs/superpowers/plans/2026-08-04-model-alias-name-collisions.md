# Model Alias Name Collisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow canonical model names and aliases to share the same value while exposing every selectable name only once in public model-list APIs.

**Architecture:** Treat a requested selector as the union of its enabled canonical-name match and all enabled alias matches, then route across the resulting model IDs using the existing route-weight logic. Build public model listings by grouping canonical names and aliases by selector; retain canonical metadata only when the selector resolves to exactly one model.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async ORM, pytest, MySQL, Ruff, mypy, npm frontend checks, Docker.

## Global Constraints

- Canonical model names remain unique among canonical model names.
- Alias values may equal canonical names on the same or different models.
- Duplicate alias entries within one model payload remain invalid.
- Shared selectors continue to use existing eligible-route weights; no model-level weight is added.
- HTTP retry pinning, billing, and audit behavior continue to use the selected model.

---

### Task 1: Merge Canonical and Alias Resolution

**Files:**
- Modify: `tests/unit/catalog/test_resolution.py`
- Modify: `src/ai_gateway/catalog/repository.py`

**Interfaces:**
- Consumes: `CatalogRepository.resolve_model(name: str) -> ResolvedModel`
- Produces: `ResolvedModel.model_ids` containing every enabled canonical or alias target in model-ID order.

- [x] **Step 1: Change the canonical-collision test to require a merged result**

```python
async def test_canonical_name_and_matching_aliases_resolve_to_one_weighted_pool(...):
    ...
    assert resolved.model_ids == (canonical.id, alias_target.id)
    assert resolved.canonical_name is None
```

- [x] **Step 2: Run the focused test and verify RED**

Run: `uv run pytest tests/unit/catalog/test_resolution.py::test_canonical_name_and_matching_aliases_resolve_to_one_weighted_pool -q`

Expected: FAIL because canonical lookup currently returns before alias lookup.

- [x] **Step 3: Replace the early canonical return with one outer-join query**

```python
models = (
    await self._session.scalars(
        select(Model)
        .outerjoin(ModelAlias)
        .where(
            Model.enabled.is_(True),
            or_(
                Model.canonical_name == name,
                and_(ModelAlias.alias == name, ModelAlias.enabled.is_(True)),
            ),
        )
        .distinct()
        .order_by(Model.id)
    )
).all()
```

- [x] **Step 4: Run all catalog resolution tests and verify GREEN**

Run: `uv run pytest tests/unit/catalog/test_resolution.py -q`

- [x] **Step 5: Commit**

```bash
git add tests/unit/catalog/test_resolution.py src/ai_gateway/catalog/repository.py
git commit -m "feat: merge canonical and alias model selectors"
```

### Task 2: Permit Canonical/Alias Collisions in Admin APIs and Imports

**Files:**
- Modify: `tests/integration/admin/test_models.py`
- Modify: `tests/integration/admin/test_configuration.py`
- Modify: `src/ai_gateway/admin/models.py`
- Modify: `src/ai_gateway/admin/configuration.py`

**Interfaces:**
- Consumes: model create/update APIs and `POST /admin/configuration/import`.
- Produces: accepted same-name canonical/alias combinations while preserving canonical uniqueness and per-model alias uniqueness.

- [x] **Step 1: Rewrite conflict tests as acceptance tests**

```python
assert alias_owner.status_code == 201
assert matching_canonical.status_code == 201

assert promoted.status_code == 200
assert promoted.json()["canonical_name"] == "alias-promotion-target"

assert import_response.status_code == 200
```

Also add a create request whose own alias equals its canonical name and assert HTTP 201.

- [x] **Step 2: Run the focused integration tests and verify RED**

Run: `uv run pytest tests/integration/admin/test_models.py tests/integration/admin/test_configuration.py -q -k 'canonical_name or canonical_alias_collision or alias_that_collides'`

Expected: FAIL with the current `ambiguous_model_name`, `model_name_conflict`, or `catalog_import_conflict` responses.

- [x] **Step 3: Restrict admin validation to canonical-vs-canonical uniqueness**

```python
model_query = select(Model.id).where(Model.canonical_name == canonical_name)
if model_id is not None:
    model_query = model_query.where(Model.id != model_id)
if await session.scalar(model_query.limit(1)) is not None:
    _raise_model_conflict()
```

Remove import checks comparing aliases with canonical names, but keep each model's `model_aliases` duplicate check.

- [x] **Step 4: Run the admin tests and verify GREEN**

Run: `uv run pytest tests/integration/admin/test_models.py tests/integration/admin/test_configuration.py -q`

- [x] **Step 5: Commit**

```bash
git add tests/integration/admin/test_models.py tests/integration/admin/test_configuration.py src/ai_gateway/admin/models.py src/ai_gateway/admin/configuration.py
git commit -m "feat: allow canonical names to match aliases"
```

### Task 3: Deduplicate Public Model Selectors

**Files:**
- Modify: `tests/contract/gateway/test_models.py`
- Modify: `src/ai_gateway/gateway/models.py`

**Interfaces:**
- Consumes: protocol- and API-key-filtered `Model` rows.
- Produces: one `SelectableModel` per selector ID; `canonical_name=None` for selectors backed by multiple models.

- [x] **Step 1: Add a contract test for shared and canonical-colliding selectors**

```python
ids = [item["id"] for item in response.json()["data"]]
assert ids.count("shared-selector") == 1
shared = next(item for item in response.json()["data"] if item["id"] == "shared-selector")
assert shared["metadata"] == {}
```

- [x] **Step 2: Run the focused contract test and verify RED**

Run: `uv run pytest tests/contract/gateway/test_models.py::test_model_list_deduplicates_shared_and_canonical_alias_selectors -q`

Expected: FAIL because the current list contains one alias entry per backing model.

- [x] **Step 3: Group selectable names by distinct backing model**

```python
targets_by_name: dict[str, dict[int, Model]] = {}
for model in models:
    targets_by_name.setdefault(model.canonical_name, {})[model.id] = model
    for alias in model.aliases:
        if alias.enabled:
            targets_by_name.setdefault(alias.alias, {})[model.id] = model
```

When a group has one target, preserve its canonical metadata and display name. When it has multiple targets, emit empty canonical metadata and use the selector as the display name.

- [x] **Step 4: Run all model-list contract tests and verify GREEN**

Run: `uv run pytest tests/contract/gateway/test_models.py -q`

- [x] **Step 5: Commit**

```bash
git add tests/contract/gateway/test_models.py src/ai_gateway/gateway/models.py
git commit -m "fix: deduplicate shared model selectors"
```

### Task 4: Full CI Verification

**Files:**
- Verify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: committed implementation and the repository's locked dependencies.
- Produces: fresh pass/fail evidence for every CI step, with unrelated known failures reported exactly.

- [x] **Step 1: Run backend quality gates**

```bash
uv sync --frozen
uv run alembic upgrade head
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src scripts
uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
```

- [x] **Step 2: Run frontend quality gates**

```bash
npm ci --prefix frontend
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm exec --prefix frontend -- playwright install --with-deps chromium
npm --prefix frontend run e2e
```

- [x] **Step 3: Run deployment gates**

```bash
docker compose -f compose.yaml config --quiet
docker compose -f example/compose.yaml config --quiet
docker build -t lean-ai-gateway:test .
```

- [x] **Step 4: Review the final diff and status**

Run: `git diff HEAD~3 --check && git status --short --branch`

- [x] **Step 5: Record verification evidence**

Update this plan's checkboxes and report every command's exit status, including any pre-existing CI failure that remains reproducible.

## Verification Results

- `uv sync --frozen`, `npm ci --prefix frontend`, and Alembic upgrade through `0015`: passed.
- Ruff lint, Ruff format check, and mypy: passed after formatting three changed files.
- Backend suite: 1,145 passed, 1 unrelated refresh-token replay test failed; coverage was 90.92% and exceeded the 90% gate.
- Frontend lint, typecheck, 238 unit tests, and production build: passed.
- Playwright: failed in authentication/registration timing, cleanup, and collapsed-sidebar layout scenarios; the 1px sidebar mismatch was previously observed, and the alias change does not modify frontend files.
- Both Compose configurations and the production Docker image build: passed.
