# Frontend Test Resource Guard Implementation Plan

> **Decision update (2026-07-27):** The user simplified this work to standard Vitest behavior. This plan supersedes the earlier custom suite-process-manager plan.

**Goal:** Keep `npm run test` as a direct Vitest command while limiting Vitest to two workers and bounding individual test, hook, and teardown operations.

**Architecture:** Vitest configuration owns concurrency and per-operation limits. npm launches Vitest directly. If an environment needs a whole-run deadline, CI or another external job supervisor owns it; the frontend application does not manage a suite process tree.

**Tech Stack:** Vitest 3.2, Vite 7.3, TypeScript 5.9, npm scripts.

## Global Constraints

- The normal command is exactly `npm run test`, backed by `"test": "vitest run"`.
- Vitest uses at most two workers and retains file parallelism.
- Individual tests use a 5-second timeout; hooks and teardown use 10-second timeouts.
- Tests continue after individual failures; do not enable `bail`.
- `npm run test -- <arguments>` uses standard argument forwarding to Vitest.
- `npm run test:watch` remains `vitest` and intentionally long-lived.
- Do not add a custom launcher, suite deadline, exit-code translation, signal forwarding, process-tree discovery, or platform-specific termination code.
- Do not modify the user's existing changes in `frontend/src/layouts/AdminLayout.vue` or `frontend/src/router/index.ts`.
- Do not add pnpm files.

---

## Final File Structure

- Keep `frontend/tests/test-runtime-config.spec.ts` for the Vitest policy contract.
- Keep the policy fields in `frontend/vite.config.ts`.
- Keep direct commands in `frontend/package.json`.
- Do not create `frontend/scripts/` test launchers or process helpers.
- Do not create process-manager or Windows process-tree unit tests.

---

### Task 1: Bound Vitest Concurrency and Operation Timeouts

**Files:**
- Create: `frontend/tests/test-runtime-config.spec.ts`
- Modify: `frontend/vite.config.ts`

**Interfaces:**
- Consumes: the existing default Vite/Vitest configuration export.
- Produces: `maxWorkers: 2`, `testTimeout: 5_000`, `hookTimeout: 10_000`, and `teardownTimeout: 10_000`.

- [x] **Step 1: Add a focused configuration regression**

  Assert all four values through the exported Vite configuration so accidental relaxation fails visibly.

- [x] **Step 2: Verify the regression fails before implementation**

  Run `cd frontend && npm exec vitest -- run tests/test-runtime-config.spec.ts --maxWorkers=1` and confirm the missing fields cause the expected failure.

- [x] **Step 3: Add the minimal Vitest settings**

  Add only the four selected fields to the existing `test` object. Do not add `minWorkers`, `fileParallelism`, or `bail`.

- [x] **Step 4: Verify the focused regression passes**

  Re-run the same focused command and confirm one file and one test pass.

- [x] **Step 5: Commit**

  Commit the configuration and focused regression as `test: bound frontend unit test resources`.

---

### Task 2: Keep the Public Command Standard

**Files:**
- Verify: `frontend/package.json`
- Verify: `frontend/tsconfig.json`
- Remove if present: custom test launchers, process helpers, and their tests.

- [x] **Step 1: Restore the direct npm contract**

  Keep `"test": "vitest run"` and leave `"test:watch": "vitest"` unchanged.

- [x] **Step 2: Remove custom suite management**

  Remove application-owned whole-suite deadlines, timeout-specific exit handling, signal forwarding, process-group cleanup, Windows CIM discovery, and direct task termination. Remove the corresponding implementation and tests rather than leaving dormant code.

- [x] **Step 3: Keep TypeScript scope minimal**

  Do not include a removed `frontend/scripts/` tree in `frontend/tsconfig.json`.

- [x] **Step 4: Preserve normal Vitest behavior**

  Allow Vitest to own normal exit codes, cancellation, reporting, and worker shutdown. Document that an external CI/job timeout may bound the entire command when required.

---

### Task 3: Align Related Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-frontend-test-resource-guard-design.md`
- Modify: `docs/superpowers/specs/2026-07-26-frontend-admin-test-repair-design.md`
- Modify: `docs/superpowers/plans/2026-07-26-frontend-admin-test-repair.md`

- [x] Record the user's simplified decision in the resource design.
- [x] Remove the former global-runner guarantees and special timeout behavior.
- [x] Keep only the two-worker and per-operation Vitest limits as application-owned policy.
- [x] Assign any whole-run timeout to CI or another external job supervisor.

---

### Task 4: Verification

- [ ] Run the focused runtime-policy regression with one worker:

  ```bash
  cd frontend
  npm exec vitest -- run tests/test-runtime-config.spec.ts --maxWorkers=1
  ```

- [ ] Run the direct public suite:

  ```bash
  npm run test -- --reporter=dot
  ```

- [ ] Run type checking and lint only the owned implementation/configuration targets.
- [ ] Run `git diff --check` and inspect the final file set.
- [ ] Confirm no custom runner, process-tree helper/test, suite-deadline code, GNU timeout wrapper, or pnpm file remains.
- [ ] Confirm the user's uncommitted AdminLayout and router changes remain untouched.
