# Multimodal Model Types and Identifier Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a model declare multiple supported types (for example `text` and `image`), export those capabilities to DeepSeek Harness, and present every model canonical name with the same one-click copy control.

**Architecture:** Add `models.model_types` as the authoritative JSON array while keeping the existing scalar `model_type` as a compatibility projection. API create/update accepts `model_types` and synchronizes the scalar to its first canonical value; legacy scalar-only requests become a one-item array. The console uses checkbox inputs and display tags for the array, and the Harness serializer derives its documented `input` list from selected `text`/`image` capabilities.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/Alembic/MySQL JSON, Vue 3, Element Plus, Vitest, pytest.

## Global Constraints

- `model_types` is a non-empty, duplicate-free list of existing `ModelType` values; default and migration value are `["text"]`.
- Retain scalar `model_type` in API/database/catalog payloads for backward compatibility; it mirrors the first normalized `model_types` item.
- Existing scalar-only create, update, import, and database records must continue to work as a one-item `model_types` list.
- DeepSeek Harness emits only the documented input modalities: selected `text` and `image`; if neither is selected, emit `[text]` as its safe manual-model fallback.
- Render canonical name in every `ModelCard` using the same accessible copy button, regardless of pricing tier state.
- Do not send API keys or credentials to the backend or browser storage.

---

### Task 1: Persist and expose multi-value model types compatibly

**Files:**

- Create: `migrations/versions/0021_model_types.py`
- Modify: `src/ai_gateway/db/models/catalog.py`
- Modify: `src/ai_gateway/catalog/schemas.py`
- Modify: `src/ai_gateway/admin/models.py`
- Modify: `src/ai_gateway/admin/configuration.py`
- Modify: `tests/integration/admin/test_models.py`
- Modify: `tests/integration/admin/test_configuration.py`
- Modify: `tests/integration/test_schema.py`
- Create: `tests/unit/migrations/test_0021_model_types.py`

**Interfaces:**

- Produces: `Model.model_types: list[ModelType]`, JSON field `models.model_types`, and response/input field `model_types: list[ModelType]`.
- Consumes: legacy `model_type: ModelType` values from API and catalog import payloads.

- [ ] **Step 1: Write failing API and migration tests**

```python
created = await admin_client.post('/admin/models', json={
    'canonical_name': 'vision-chat', 'display_name': 'Vision Chat',
    'model_types': ['text', 'image'],
})
assert created.json()['model_types'] == ['text', 'image']
assert created.json()['model_type'] == 'text'

updated = await admin_client.patch(f"/admin/models/{created.json()['id']}", json={
    'model_types': ['image'],
})
assert updated.json()['model_types'] == ['image']
assert updated.json()['model_type'] == 'image'
```

Add negative tests for empty and duplicate arrays, plus a migration recorder test that requires an added `model_types` JSON column and records backfill SQL.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -W error tests/integration/admin/test_models.py tests/unit/migrations/test_0021_model_types.py`

Expected: FAIL because `model_types` is currently rejected or absent.

- [ ] **Step 3: Implement migration, ORM, schemas, and compatibility synchronization**

```python
model_types: Mapped[list[ModelType]] = mapped_column(JSON, default=lambda: [ModelType.TEXT])

def normalized_model_types(values: list[ModelType]) -> list[ModelType]:
    if not values or len(values) != len(set(values)):
        raise ValueError('model_types must contain unique values')
    return values
```

Migration upgrade adds nullable JSON `model_types`, executes `UPDATE models SET model_types = JSON_ARRAY(model_type)`, then makes it non-null. Downgrade copies the first JSON item back to legacy `model_type` before dropping `model_types`. Create/update/import normalizes `model_types`, persists it, and assigns `model_type = model_types[0]`; scalar-only inputs set `model_types = [model_type]`.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest -W error tests/integration/admin/test_models.py tests/integration/admin/test_configuration.py tests/integration/test_schema.py tests/unit/migrations/test_0021_model_types.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Stage only Task 1 source, migration, and test files with message `feat: support multiple model types`.

### Task 2: Make model type selection, display, and canonical-name copy consistent

**Files:**

- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/models/ModelFormDrawer.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/tests/models.spec.ts`

**Interfaces:**

- Consumes: `ModelResponse.model_types?: ModelType[]` and backward-compatible `model_type?: ModelType`.
- Produces: checkbox selection in the model form, multi-tag display in the card, and `data-test="copy-model-canonical-<id>"` for every card.

- [ ] **Step 1: Write failing component tests**

```ts
await wrapper.get('[data-test="model-type-image"]').setValue(true)
await wrapper.get('form').trigger('submit')
expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
  model_types: ['text', 'image'],
}))

await card.get('[data-test="copy-model-canonical-1"]').trigger('click')
expect(writeText).toHaveBeenCalledWith('gpt-4.1')
```

Mount both a tiered-price card and a base-price card. Assert both show the same canonical copy button and multi-type labels.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend run test -- tests/models.spec.ts`

Expected: FAIL because the form is a scalar select and tiered cards omit the copy control.

- [ ] **Step 3: Implement minimal uniform controls**

```ts
const modelTypes = ref<ModelType[]>(['text'])

function responseModelTypes(model: ModelResponse): ModelType[] {
  return model.model_types?.length ? model.model_types : [model.model_type ?? 'text']
}
```

Replace the scalar select with a checkbox group whose seven values reuse existing labels. Validate at least one selection before submit. Move one `copyable-code` canonical-name row above conditional pricing sections so all cards use it; retain the clipboard fallback and update the button data test/accessibility label.

- [ ] **Step 4: Verify GREEN**

Run: `npm --prefix frontend run test -- tests/models.spec.ts && npm --prefix frontend run lint && npm --prefix frontend run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Stage only Task 2 files with message `feat: make model types multi-select`.

### Task 3: Export selected input modalities to DeepSeek Harness

**Files:**

- Modify: `frontend/src/lib/deepseekHarness.ts`
- Modify: `frontend/src/views/ProvidersView.vue`
- Modify: `frontend/tests/deepseek-harness.spec.ts`
- Modify: `frontend/tests/providers.spec.ts`

**Interfaces:**

- Consumes: `model_types?: ModelType[]` with legacy `model_type?: ModelType` fallback.
- Produces: Harness model YAML `input: [text, image]` when both supported types are selected.

- [ ] **Step 1: Write a failing serializer test**

```ts
const files = buildDeepSeekHarnessFiles({
  /* required provider options */,
  models: [{ canonical_name: 'vision-chat', model_types: ['text', 'image'], enabled: true }],
})
expect(files.settingsYaml).toContain('input: [text, image]')
```

Add cases for image-only, non-input types fallback, and legacy scalar model data.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend run test -- tests/deepseek-harness.spec.ts tests/providers.spec.ts`

Expected: FAIL because serializer checks only the scalar value.

- [ ] **Step 3: Implement compatible type extraction**

```ts
function harnessInputs(model: DeepSeekHarnessModel): ('text' | 'image')[] {
  const types = model.model_types?.length ? model.model_types : [model.model_type ?? 'text']
  const inputs = ['text', 'image'].filter((type) => types.includes(type as ModelType))
  return inputs.length === 0 ? ['text'] : inputs
}
```

Pass `model_types` through the provider-dialog model loader without changing its credential lifecycle or single adapter radio group.

- [ ] **Step 4: Verify GREEN**

Run: `npm --prefix frontend run test -- tests/deepseek-harness.spec.ts tests/providers.spec.ts && npm --prefix frontend run lint && npm --prefix frontend run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Stage only Task 3 files with message `fix: export multimodal Harness inputs`.

### Task 4: Verify migration, API, console, and browser workflow

**Files:**

- Modify: none

- [ ] **Step 1: Run a clean MySQL migration check**

Run: start an isolated `mysql:8.4` container using `docker run --rm`, apply `uv run alembic upgrade head`, and assert a legacy model becomes `model_types == ['text']`.

Expected: PASS.

- [ ] **Step 2: Run complete frontend and backend quality checks**

Run: `npm --prefix frontend run test && npm --prefix frontend run build && uv run ruff check src tests scripts && uv run ruff format --check src tests scripts && uv run mypy src scripts && uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90`

Expected: PASS.

- [ ] **Step 3: Run browser acceptance tests against the isolated database**

Run: after applying migrations with CI-equivalent environment values, `CI=true E2E_ADMIN_EMAIL='console-e2e@example.com' E2E_ADMIN_PASSWORD="$(openssl rand -hex 24)" npm --prefix frontend run e2e`.

Expected: PASS.

## Self-Review

- The plan converts model capability selection to a non-empty multi-value list without breaking scalar clients or existing rows.
- The same compatibility rule is used by API, catalog export/import, console display/form state, and Harness serialization.
- The canonical-name copy control is lifted out of pricing-specific branches so every model card has the same interaction and visual treatment.
