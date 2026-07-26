# Frontend Admin Test Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute this plan task-by-task with specification and quality review checkpoints.

**Goal:** Make all API-key, provider, model, and route unit tests pass while preserving the current card/checkbox UI and fixing the production regressions identified in the design.

**Architecture:** Routed views own data and mutation coordination; form drawers own draft validation; cards expose stable semantic hooks and emit item-specific events. Tests assert behavior through those public UI contracts instead of obsolete layout details.

**Tech Stack:** Vue 3.5, Element Plus 2.11, Vue Test Utils 2.4, Vitest 3.2, TypeScript 5.9.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-26-frontend-admin-test-repair-design.md`.
- Use tests first for each production regression.
- Preserve the current card UI, collapsible route lists, provider credential guidance, and API-key scope checkboxes.
- Preserve the worktree's `auth.ready` route-guard correction exactly.
- Do not commit generated `pnpm-lock.yaml` or `pnpm-workspace.yaml` files.
- Use at most one worker for focused runs until the resource guard is implemented.

---

### Task 1: Restore API-key ownership and one-time-secret safety

**Files:**
- Modify: `frontend/tests/api-keys.spec.ts`
- Modify: `frontend/src/components/api-keys/ApiKeyFormDrawer.vue`
- Modify: `frontend/src/components/api-keys/SecretResultDialog.vue`
- Modify: `frontend/src/views/ApiKeysView.vue`

- [ ] Update the form tests to mount the current checkbox UI and add explicit assertions that create requires/selects an owner, edit displays a disabled owner, provider/model IDs follow checked boxes, and hidden scope selections are cleared.
- [ ] Keep the existing assertion that the raw one-time key occurs once and add an assertion that generated examples contain only the environment-variable placeholder.
- [ ] Run `npm exec vitest -- run tests/api-keys.spec.ts --maxWorkers=1 --reporter=dot` and record the expected failures.
- [ ] Add a required `users` prop and owner model to `ApiKeyFormDrawer`; remove `useAuthStore`; reset owner/drafts correctly; emit the selected user ID on create and the original user ID on edit.
- [ ] Add stable hooks to each provider/model scope checkbox and update tests to click the actual checkbox inputs.
- [ ] Pass `:users="users"` from `ApiKeysView`.
- [ ] Replace raw-secret interpolation in all request examples with `$AI_GATEWAY_API_KEY` while keeping the dedicated secret field/copy/download behavior.
- [ ] Re-run the focused test until green, then run `npm run typecheck`.
- [ ] Commit only Task 1 files with `fix: restore api key ownership controls`.

---

### Task 2: Restore generic provider credentials and operation-state contracts

**Files:**
- Modify: `frontend/tests/providers.spec.ts`
- Modify: `frontend/src/components/providers/ProviderCard.vue`
- Modify: `frontend/src/components/providers/ProviderFormDrawer.vue`
- Modify if required: `frontend/src/views/ProvidersView.vue`

- [ ] Extend tests for the selected credential merge rules: arbitrary object fields survive, guided reserved fields override matching advanced keys, arrays/scalars/malformed JSON are rejected inline, blank edit input omits `credential`, and secret drafts are cleared on close/success.
- [ ] Retain concurrency assertions for edit/sync/delete and stable per-provider hooks.
- [ ] Run `npm exec vitest -- run tests/providers.spec.ts --maxWorkers=1 --reporter=dot` and record RED.
- [ ] Restore `edit-provider-{id}`, `sync-provider-{id}`, and `delete-provider-{id}` hooks on the current card actions.
- [ ] Disable all card actions while `loading`; delete additionally respects `nonDeletable`.
- [ ] Add an advanced credential JSON-object textarea without removing the guided fields. Validate and merge it according to the design, omit blank credentials, and clear sensitive drafts on every terminal drawer path.
- [ ] Keep the view's existing operation guard as defense in depth.
- [ ] Re-run the focused test until green, then run `npm run typecheck`.
- [ ] Commit only Task 2 files with `fix: restore provider credential flexibility`.

---

### Task 3: Repair model-card and route behavior

**Files:**
- Modify: `frontend/tests/models.spec.ts`
- Modify: `frontend/tests/routes.spec.ts`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/src/views/ModelsView.vue`

- [ ] Update stale master/detail tests to the current independent-card UI: expand the target card before route assertions and use per-card creation/actions.
- [ ] Preserve tests for model/route delete conflicts, disable-instead recovery, exclusive mutations, route counts, and state surviving refreshes.
- [ ] Add regressions that edit/delete a route belonging to a non-initial card and assert that visible route notices/recovery controls are rendered.
- [ ] Run `npm exec vitest -- run tests/models.spec.ts tests/routes.spec.ts --maxWorkers=1 --reporter=dot` and record RED.
- [ ] Restore stable model hooks: `edit-model-{id}`, `delete-model-{id}`, `disable-model-{id}`, `model-status-{id}`, `route-count-{id}`, and a per-card create-route hook.
- [ ] Restore stable route hooks for edit/delete/disable/status within expanded cards.
- [ ] Pass route-loading and global operation state into cards and disable conflicting controls while mutations are active.
- [ ] Refactor route handlers to use the emitted model/route IDs rather than obsolete selected-model guards. Remove dead selection-only state only after confirming no consumer remains.
- [ ] Render `routeNotice` and the historical-route conflict action that disables the route instead of deleting it.
- [ ] Ensure card counts and route rows derive from the canonical `allRoutes` data and survive refresh reconciliation.
- [ ] Re-run focused tests until green, then run `npm run typecheck`.
- [ ] Commit only Task 3 files with `fix: repair model route card actions`.

---

### Task 4: Implement the bounded public test command

Execute every unchecked item in:

`docs/superpowers/plans/2026-07-26-frontend-test-resource-guard.md`

The final `npm run test` entry point must cap Vitest at two workers, terminate the whole suite at 120 seconds, allow 10 seconds for graceful shutdown, force-kill the remaining process group, and return 124 on timeout without hiding test failures.

Commit with `fix: bound frontend test resources`.

---

### Task 5: Repair route transition reliability

Execute every unchecked item in:

`docs/superpowers/plans/2026-07-26-frontend-route-transition-reliability.md`

Preserve the user-owned `auth.ready` guard change while removing only hover preloading from `AdminLayout.vue`; wrap all seven views with `.route-page` roots and prove the real Transition no longer warns.

Commit with `fix: stabilize admin route transitions`.

---

### Task 6: Integrated verification and final review

- [ ] Run all four repaired suites directly with at most two workers.
- [ ] Run `npm run test -- --reporter=dot`; confirm it exits itself, uses at most two workers, and finishes below the suite deadline.
- [ ] Run `npm run typecheck`, `npm run lint`, and `npm run build`.
- [ ] Run `git diff --check`, inspect the complete branch diff, and confirm only intended docs/frontend files changed.
- [ ] Confirm the original main workspace still contains its pre-existing `AdminLayout.vue` and `router/index.ts` changes and has not been overwritten.
- [ ] Perform a final specification review followed by a code-quality review. Fix any findings and repeat the affected verification.
