# Models, Aliases, and Weighted Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the model placeholder with a Chinese master/detail console for exact-price models, aliases, and weighted provider routes.

**Architecture:** Add a typed API module, two focused form drawers, and one coordinating view. The view owns list loading, selection, row-operation exclusion, conflict-to-disable recovery, and stale-response protection; the drawers own draft initialization, exact string validation, cleanup, and payload construction.

**Tech Stack:** Vue 3 Composition API, TypeScript, Element Plus local imports, Axios, Vitest, Vue Test Utils, MSW.

## Global Constraints

- Prices remain strings from response through edit input and request payload; never convert prices through JavaScript numbers.
- Normalize backend scientific zero strings such as `0E-8` with string operations only.
- Alias values are unique within a model, cannot equal the canonical name, and retain their enabled state.
- The route field is labeled `提供商原始模型名` and explains alias rewriting.
- Route protocols are restricted to the selected provider; route weights are integers from 1 through 10000.
- Route source, runtime health, failure count, disabled-until, and last-error data are read-only.
- Model and route history conflicts expose an actionable disable PATCH flow.
- Prevent drawer closure during saves; bind async work to mount/session/record state; exclude concurrent operations per record; reject stale loads; clean form drafts immediately on close and teardown.
- Use Simplified Chinese copy, local Element Plus imports/styles, a lazy route, and test-driven development.

---

### Task 1: API contract and failing behavior suites

**Files:**
- Create: `frontend/src/api/models.ts`
- Create: `frontend/tests/models.spec.ts`
- Create: `frontend/tests/routes.spec.ts`

**Interfaces:**
- Produces: `listModels`, `createModel`, `updateModel`, `deleteModel`.
- Produces: `listModelRoutes`, `createModelRoute`, `updateModelRoute`, `deleteModelRoute`.
- `listModelRoutes(filters?, signal?)` serializes only defined `model_id` and `provider_id` values.

- [ ] **Step 1: Write failing model tests**

Cover lazy routing, exact decimal strings including scientific zero normalization, enabled alias objects, duplicate/canonical alias rejection, validation focus, lifecycle exclusion, stale list rejection, delete confirmation, and history-conflict disable PATCH.

- [ ] **Step 2: Write failing route tests**

Cover provider/protocol filtering, original-name label and rewrite explanation, integer weight validation, read-only metadata, discovered-route editing, health labels, selected-model loading, lifecycle exclusion, delete confirmation, and history-conflict disable PATCH.

- [ ] **Step 3: Run RED**

Run: `npm --prefix frontend run test -- models.spec.ts routes.spec.ts`

Expected: the suites fail because the model API, view, and drawers do not exist.

- [ ] **Step 4: Implement the typed API module**

Each function accepts an optional `AbortSignal`; create/update/delete functions target `/admin/models/:id` and `/admin/model-routes/:id`, while list functions target the collection URLs.

### Task 2: Model form drawer

**Files:**
- Create: `frontend/src/components/models/ModelFormDrawer.vue`

**Interfaces:**
- Consumes: `ModelResponse | null`, `modelValue`, and `submitting` props.
- Produces: `submit` with `ModelCreate | ModelUpdate` and `update:modelValue`.

- [ ] **Step 1: Build string-safe initialization**

Use `normalizeDecimalInput(value: string)` to detect only zero-valued decimal/scientific strings with a regular expression and return `0`; otherwise preserve the original string exactly.

- [ ] **Step 2: Add validation and payload construction**

Validate names, `^\d{1,12}(\.\d{1,8})?$` prices, unique trimmed aliases, aliases different from the trimmed canonical name, and enabled alias rows. Create sends all fields; edit sends only changed fields while preserving price strings.

- [ ] **Step 3: Add lifecycle behavior**

Block close, cancel, Escape, overlay close, and external close while submitting. Reset all draft and error state synchronously on accepted close, successful external closure, prop-session replacement, and teardown.

### Task 3: Route form drawer

**Files:**
- Create: `frontend/src/components/models/RouteFormDrawer.vue`

**Interfaces:**
- Consumes: selected `model`, `route`, `providers`, `modelValue`, and `submitting` props.
- Produces: `submit` with `ModelRouteCreate | ModelRouteUpdate` and `update:modelValue`.

- [ ] **Step 1: Build filtered provider/protocol selection**

When provider changes, retain the protocol only if it belongs to that provider; otherwise select the first available protocol. Render protocol labels from the selected provider only.

- [ ] **Step 2: Validate route inputs**

Require provider, matching protocol, trimmed original upstream model, and an integer weight from 1 through 10000. Label the original name exactly and render the alias rewrite explanation.

- [ ] **Step 3: Add lifecycle behavior**

Use the same save-time close blocking, synchronous draft cleanup, validation focus, and prop-session replacement protections as the model drawer.

### Task 4: Master/detail models view

**Files:**
- Create: `frontend/src/views/ModelsView.vue`
- Modify: `frontend/src/router/index.ts`

**Interfaces:**
- Consumes: the model/route/provider API modules and both drawers.
- Produces: selected-model route detail loading and all CRUD interactions.

- [ ] **Step 1: Load models, providers, and route counts safely**

Issue abortable generation-bound loads. Fetch all routes for route counts, then fetch the selected model's routes with `model_id`; local mutations advance state revisions and deleted records remain tombstoned for the page session.

- [ ] **Step 2: Render the model master table**

Render display/canonical names, enabled alias tags, exact prices, weighted-random label, enabled state, route count, and create/edit/delete actions. Selection changes route detail context.

- [ ] **Step 3: Render route detail and metadata**

Render provider/protocol names, upstream model, weight, enabled/source/runtime state, failures, disabled-until, and last error. Map `closed` to `健康`, `half_open` to `探测中`, and `open` to `不可用`.

- [ ] **Step 4: Add lifecycle-safe mutations**

Use a per-model and per-route operation map, save token, drawer session generation, operation controller, mounted guard, and current-record checks. Prevent a record from being edited/deleted/disabled concurrently.

- [ ] **Step 5: Add conflict-to-disable flows**

After `model_has_history` or `model_route_has_history`, retain the row and show a warning containing a button that sends `PATCH {"enabled": false}` through the guarded operation path.

- [ ] **Step 6: Activate the lazy route**

Change only the `models` child route component to `() => import('@/views/ModelsView.vue')`.

### Task 5: Verification, report, and commit

**Files:**
- Create: `.superpowers/sdd/task-7-report.md`

- [ ] **Step 1: Run focused GREEN**

Run: `npm --prefix frontend run test -- models.spec.ts routes.spec.ts`

- [ ] **Step 2: Run full frontend gates**

Run `npm --prefix frontend run test`, `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, and `npm --prefix frontend run build`.

- [ ] **Step 3: Inspect the change**

Run `git diff --check`, inspect `git status --short`, and review the final diff for string prices, local imports, Chinese copy, stale async guards, operation exclusion, cleanup, and real conflict-disable actions.

- [ ] **Step 4: Write the report**

Record RED/GREEN evidence, exact-decimal evidence, concurrency self-review, all gate outputs, the final commit, and remaining concerns in `.superpowers/sdd/task-7-report.md`.

- [ ] **Step 5: Commit**

Stage only Task 7 files and commit with `feat: manage models aliases and routes`.
