# Task 4 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve every Task 4 review finding with regression tests for login lifecycle, route security, responsive shell behavior, and accessibility.

**Architecture:** Keep the existing lazy Vue Router and locally imported Element Plus components. Make the smallest component changes needed: unlock before focusing the TOTP input, protect every route except login, use a single semantic not-found link, and provide a custom Chinese-labelled drawer close button. Exercise lifecycle and responsive behavior through mounted router trees rather than component-local shortcuts.

**Tech Stack:** Vue 3, Vue Router 4, Pinia, Element Plus, Vitest, Vue Test Utils, MSW, TypeScript.

## Global Constraints

- Use TDD for every regression.
- Only `/login` is public; wildcard routes require authentication.
- Preserve the two-stage login flow and in-flight submission locking.
- Keep `skipLibCheck: true` and all other current strict TypeScript settings.
- Do not install the global Element Plus plugin or full global Element Plus theme.

---

### Task 1: Login focus and route-driven secret cleanup

**Files:**
- Modify: `frontend/tests/login.spec.ts`
- Modify: `frontend/src/views/LoginView.vue`

**Interfaces:**
- Consumes: `createAppRouter(createMemoryHistory())`, `App.vue`, `useAuthStore().login()`.
- Produces: TOTP mode where the input is enabled before `nextTick()` and focus, plus secret cleanup on actual RouterView unmount.

- [ ] **Step 1: Write failing regressions**

Add a browser-order regression that inspects the TOTP input at its `focus()` call and expects it not to be disabled. Replace the manual `LoginView` cleanup check with a mounted `App`/`RouterView` test that populates password and TOTP, navigates away while authenticated, and verifies the captured input elements are cleared and disconnected.

- [ ] **Step 2: Run the focused login tests to verify RED**

Run: `npm --prefix frontend run test -- login.spec.ts`

Expected: the focus regression reports that the revealed TOTP input is disabled when focus is attempted; the old direct-mount lifecycle gap is exposed by the new RouterView test until its harness and implementation are complete.

- [ ] **Step 3: Implement the minimal fix**

In the `totp_required` branch, set `needsTotp`, clear the TOTP code, set `submitting` false, then await `nextTick()` and call the Element Plus input focus method. Keep the early in-flight guard and ensure `finally` still leaves submission unlocked. Keep `onBeforeUnmount(clearSecrets)`.

- [ ] **Step 4: Run the focused login tests to verify GREEN**

Run: `npm --prefix frontend run test -- login.spec.ts`

Expected: all login tests pass.

---

### Task 2: Router and not-found security semantics

**Files:**
- Modify: `frontend/tests/router.spec.ts`
- Modify: `frontend/src/router/index.ts`
- Create: `frontend/src/router/redirect.ts`
- Modify: `frontend/src/views/NotFoundView.vue`

**Interfaces:**
- Consumes: `RouteLocationNormalized.fullPath`, route meta, login redirect query.
- Produces: exact query/hash redirect preservation, authenticated-only wildcard, hostile redirect rejection, and one semantic link control on the 404 page.

- [ ] **Step 1: Write failing router regressions**

Add tests for `/providers?enabled=true#details` preserving the exact full path, unauthenticated `/unknown/path?x=1#missing` redirecting to login, authenticated unknown paths rendering the named not-found route, and login redirects rejecting `//evil.example`, encoded protocol-relative values, backslash variants, and non-root-relative URL values.

- [ ] **Step 2: Run router tests to verify RED**

Run: `npm --prefix frontend run test -- router.spec.ts`

Expected: unauthenticated wildcard navigation reaches public not-found instead of login.

- [ ] **Step 3: Implement routing and semantic-link fixes**

Remove `meta.public` from the wildcard route so the guard protects it. Replace `RouterLink > ElButton` with one styled `RouterLink` and remove the Element Plus button import/theme from `NotFoundView.vue`. Centralize redirect validation in an exported router helper so tests cover decoded and hostile query values; accept only root-relative paths whose parsed URL remains on the internal placeholder origin and whose raw value contains no backslash.

- [ ] **Step 4: Run router tests to verify GREEN**

Run: `npm --prefix frontend run test -- router.spec.ts`

Expected: all router tests pass.

---

### Task 3: Responsive administration shell and accessible drawer close

**Files:**
- Create: `frontend/tests/admin-layout.spec.ts`
- Modify: `frontend/src/layouts/AdminLayout.vue`

**Interfaces:**
- Consumes: authenticated Pinia state, RouterView, `window.innerWidth`, resize events.
- Produces: expanded desktop at 1200 px and above, collapsed sidebar from 768–1199 px, drawer below 768 px, drawer navigation, logout, skip link, focusable main region, and a Chinese-labelled custom close control.

- [ ] **Step 1: Write failing shell regressions**

Mount the real router tree with an authenticated store and assert the three viewport modes at 1200, 1199, 768, and 767 px. Open the mobile drawer, verify `aria-label="关闭导航菜单"`, navigate through a drawer item and confirm closure, exercise the header security action, spy on logout and verify replacement to login, and assert the skip link targets `#main-content` whose element is a focusable main region containing RouterView content.

- [ ] **Step 2: Run shell tests to verify RED**

Run: `npm --prefix frontend run test -- admin-layout.spec.ts`

Expected: no Chinese-labelled drawer close control is present and any unimplemented shell selectors fail.

- [ ] **Step 3: Implement the minimal shell accessibility fix**

Set `:show-close="false"` on `ElDrawer`, use its header slot, render the title, and add one local `ElButton` with `aria-label="关闭导航菜单"` that closes the drawer. Add stable `data-test` attributes only where needed for robust mode/navigation assertions; do not add global Element Plus imports.

- [ ] **Step 4: Run shell tests to verify GREEN**

Run: `npm --prefix frontend run test -- admin-layout.spec.ts`

Expected: all shell tests pass.

---

### Task 4: Full verification, report, and commit

**Files:**
- Modify: `.superpowers/sdd/task-4-report.md`
- Modify: `docs/superpowers/plans/2026-07-22-task-4-review-fixes.md`

**Interfaces:**
- Consumes: focused RED/GREEN outputs and final frontend verification.
- Produces: auditable review-fix evidence and one committed change set.

- [ ] **Step 1: Run focused tests together**

Run: `npm --prefix frontend run test -- login.spec.ts router.spec.ts admin-layout.spec.ts`

Expected: all focused tests pass.

- [ ] **Step 2: Run the full frontend gate**

Run: `npm --prefix frontend run test && npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run build`

Expected: every command exits 0; retain `skipLibCheck: true`.

- [ ] **Step 3: Review the diff**

Run: `git diff --check && git diff -- frontend/src frontend/tests frontend/tsconfig.json .superpowers/sdd/task-4-report.md docs/superpowers/plans/2026-07-22-task-4-review-fixes.md`

Expected: no whitespace errors, no nested interactive controls, only login is public, no global Element Plus plugin/theme, and strict settings are unchanged.

- [ ] **Step 4: Append the review-fixes report**

Document RED/GREEN evidence, commands and results, changed files, self-review, and remaining concerns under `## Review fixes` in `.superpowers/sdd/task-4-report.md`.

- [ ] **Step 5: Commit**

Run:

```bash
git add frontend/src frontend/tests .superpowers/sdd/task-4-report.md docs/superpowers/plans/2026-07-22-task-4-review-fixes.md
git commit -m "fix: address console shell review findings"
```

Expected: a new commit on `feature/lean-ai-gateway` and a clean tracked worktree.

## Self-Review

- Spec coverage: all six required review areas map to Tasks 1–4.
- Placeholder scan: no deferred implementation steps or unspecified error handling remain.
- Type consistency: tests and implementation use existing `createAppRouter`, Pinia auth state, named routes, and Vue component interfaces.
