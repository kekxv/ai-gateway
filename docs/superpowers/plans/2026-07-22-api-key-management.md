# API Key Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the API-key placeholder with secure scoped-key CRUD, rotation, and one-time secret presentation.

**Architecture:** Keep API metadata in `ApiKeysView` and raw secrets only in a local `ref<string | null>` that is handed directly to a dedicated non-dismissible dialog. Put scope normalization and dirty PATCH construction in the form drawer, and use abort/session/operation guards in the view so stale responses cannot mutate current UI state.

**Tech Stack:** Vue 3 Composition API, TypeScript, Element Plus, Axios, Vitest, Vue Test Utils, MSW.

## Global Constraints

- Raw keys never enter Pinia, router/query state, browser storage, console output, generic notifications, or metadata collections.
- The secret dialog can close only after explicit acknowledgement and clears all secret-derived state on close/unmount.
- Scope values are exactly `all`, `providers`, `models`, and `providers_and_models`; irrelevant selector arrays are always cleared.
- Every request supports `AbortSignal`; teardown aborts loads, saves, rotations, and deletes.
- Destructive confirmation controllers are created before awaiting confirmation so teardown can invalidate the continuation.
- User-facing copy is Chinese, imports are local aliases, and the route remains lazy-loaded.

---

### Task 1: API functions and regression tests

**Files:**
- Create: `frontend/src/api/apiKeys.ts`
- Create: `frontend/tests/api-keys.spec.ts`

**Interfaces:**
- Produces: `listApiKeys(userId?: number, signal?: AbortSignal)`, `createApiKey(payload, signal?)`, `updateApiKey(id, payload, signal?)`, `deleteApiKey(id, signal?)`, and `rotateApiKey(id, signal?)`.

- [ ] Write tests that exercise user filter serialization, exact owner display, all four scope selector combinations, normalized create payloads, ISO/null expiry, dirty PATCH payloads, one-time dialog erasure, copy/download cleanup, confirmed rotation, inactive rotation refresh, stale-response guards, and teardown aborts.
- [ ] Run `npm --prefix frontend run test -- api-keys.spec.ts`; expect failure because the route/components/API module do not exist.
- [ ] Add thin typed Axios functions using `/admin/api-keys` and optional `{ params: { user_id }, signal }` configuration.
- [ ] Run focused API tests and retain the remaining component failures as the RED checkpoint.

### Task 2: Scoped form drawer

**Files:**
- Create: `frontend/src/components/api-keys/ApiKeyFormDrawer.vue`

**Interfaces:**
- Consumes: `ApiKeyResponse | null`, user/provider/model lists.
- Produces: `ApiKeyCreate | ApiKeyUpdate`, with `provider_ids`/`model_ids` normalized for the selected scope.

- [ ] Render owner and name inputs, exact four-value scope selection, conditional multi-selectors, enabled switch, and `datetime-local` expiry.
- [ ] Validate owner/name on create and required selector arrays per scope.
- [ ] Convert a nonblank local expiry to `new Date(value).toISOString()` and blank expiry to `null`.
- [ ] On edit, leave owner immutable and emit only changed fields; include normalized relationship arrays whenever scope or a relevant selection changes, and emit `expires_at: null` only when clearing a prior expiry.
- [ ] Clear irrelevant selection arrays immediately when scope changes and clear draft state when closed/unmounted.
- [ ] Run scope/form tests and expect them to pass.

### Task 3: One-time secret dialog

**Files:**
- Create: `frontend/src/components/api-keys/SecretResultDialog.vue`

**Interfaces:**
- Consumes: local `secret: string | null` and `modelValue` from the parent view.
- Produces: a close event only after acknowledgement; never emits or stores the secret elsewhere.

- [ ] Render an Element Plus dialog with modal/escape/header-close disabled and `destroy-on-close`.
- [ ] Provide explicit “复制” and “下载 .txt” actions and the exact acknowledgement checkbox text.
- [ ] Copy directly from the prop at click time; show only local non-secret action status.
- [ ] For download, create a Blob and object URL, click a temporary anchor, then revoke and remove immediately in `finally`; revoke any outstanding URL on unmount.
- [ ] Reset acknowledgement/status on close and emit close only after acknowledgement.
- [ ] Run secret-lifetime tests and expect them to pass.

### Task 4: Guarded key-management view and lazy route

**Files:**
- Create: `frontend/src/views/ApiKeysView.vue`
- Modify: `frontend/src/router/index.ts`

**Interfaces:**
- Consumes: API functions and catalog APIs.
- Produces: table columns for name, owner, prefix, scope, status, expiry, last-used, created, and guarded CRUD/rotation actions.

- [ ] Load keys/users/providers/models together under a generation and state-revision guard; abort the previous load first.
- [ ] Maintain per-key operation locks and save-session tokens; reject concurrent edit/delete/rotate operations.
- [ ] After creation/rotation, destructure `{ key, ...metadata }`, update metadata only, then assign the raw string directly to the local secret ref and open the shared dialog.
- [ ] Clear the secret synchronously when the acknowledged close event is received and on teardown.
- [ ] Create delete/rotate controllers before confirmation; after confirmation re-check mount, abort, and operation state.
- [ ] Confirm that rotation disables the old key; on success replace the old metadata entry with replacement metadata. On `api_key_inactive`, refresh and show guidance that only active keys can rotate.
- [ ] Point `/api-keys` at a local lazy import of `ApiKeysView.vue`.
- [ ] Run the full focused test file and typecheck.

### Task 5: Verification, security review, report, and commit

**Files:**
- Create: `.superpowers/sdd/task-9-report.md`

- [ ] Search the diff for raw-key persistence/logging paths and inspect every secret assignment/clear boundary.
- [ ] Run `npm --prefix frontend run test -- api-keys.spec.ts`.
- [ ] Run `npm --prefix frontend run test`, `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, and `npm --prefix frontend run build`.
- [ ] Record RED/GREEN evidence, gate outputs, secret-lifetime review, and concerns in the report.
- [ ] Commit the implementation, tests, plan, and report with `feat: add scoped api key management`.
