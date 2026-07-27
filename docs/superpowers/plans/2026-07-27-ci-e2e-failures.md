# CI Playwright Failure Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the CI administrator-console Playwright job by fixing WCAG color contrast,
scrollable-region keyboard access, route-transition focus management, and obsolete UI selectors.

**Architecture:** Keep the existing end-to-end tests as the browser-level contract. Make the global
primary and danger colors meet WCAG AA on white, keep the scrollable main region in the keyboard
tab order, coordinate programmatic heading focus with Vue's `Transition` completion event, and
update stale locators to target the current page actions and card UI.

**Tech Stack:** Vue 3, Vue Router, Element Plus, TypeScript, Playwright, Axe.

## Global Constraints

- Preserve the existing administration-console layout and Chinese labels.
- Do not weaken or disable Axe checks.
- Do not add arbitrary timing sleeps to focus management or E2E tests.
- Keep provider creation behavior unchanged; only replace the obsolete table-row locator.
- Run the browser tests with one worker against the MySQL-backed gateway, matching CI.

---

### Task 1: Make action colors WCAG AA compliant

**Files:**
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/e2e/admin-console.spec.ts`

**Interfaces:**
- Consumes: CSS custom properties `--gateway-brand` and `--el-color-primary`.
- Produces: Primary and danger colors with at least 4.5:1 contrast against white for small text
  and buttons.

- [ ] **Step 1: Verify the existing Axe test fails for color contrast**

Run:

```bash
CI=1 CONSOLE_BASE_URL=http://127.0.0.1:8001/console/ \
  E2E_ADMIN_EMAIL=console-e2e-repro-20260727@example.com \
  E2E_ADMIN_PASSWORD='Local-e2e-repro-20260727!' \
  npm --prefix frontend run e2e -- \
  --grep 'login and administrator pages have no critical or serious Axe violations'
```

Expected: FAIL with Axe reporting `#3b82f6` at 3.67:1 against white.

- [ ] **Step 2: Change the shared brand and Element Plus primary color**

In `frontend/src/styles/index.css`, use the accessible blue consistently:

```css
--gateway-brand: #2563eb;
--el-color-primary: #2563eb;
--el-color-primary-dark-2: #1d4ed8;
--el-color-danger: #dc2626;
```

Keep the existing light variant unless Axe identifies another contrast failure.

- [ ] **Step 3: Verify the Axe test passes**

Run the Step 1 command again.

Expected: PASS with no critical or serious Axe violations on login or administrator pages.

### Task 2: Keep the main region keyboard-accessible and focus new page headings after transitions

**Files:**
- Modify: `frontend/src/layouts/AdminLayout.vue`
- Test: `frontend/e2e/admin-console.spec.ts`
- Test: `frontend/tests/admin-layout.spec.ts`

**Interfaces:**
- Consumes: `navigate(path: string)`, Vue `Transition` lifecycle, `.page-header h1`.
- Produces: A tab-focusable scrollable main region and `focusPendingPageHeading()` that focuses the
  destination heading only for navigation initiated by the shell.

- [ ] **Step 1: Verify the existing keyboard E2E test fails**

Run:

```bash
CI=1 CONSOLE_BASE_URL=http://127.0.0.1:8001/console/ \
  E2E_ADMIN_EMAIL=console-e2e-repro-20260727@example.com \
  E2E_ADMIN_PASSWORD='Local-e2e-repro-20260727!' \
  npm --prefix frontend run e2e -- \
  --grep 'keyboard focus moves from skip link through navigation to the page action'
```

Expected: FAIL because the Providers heading exists but is not focused.

- [ ] **Step 2: Coordinate focus with transition completion**

Change `#main-content` from `tabindex="-1"` to `tabindex="0"` so Axe and Safari recognize the
scrollable region as keyboard-accessible. Update the existing unit assertion accordingly.

In `frontend/src/layouts/AdminLayout.vue`, add a module-local pending flag and helper:

```ts
let pendingPageHeadingFocus = false

function focusPendingPageHeading(): void {
  if (!pendingPageHeadingFocus) return
  const heading = document.querySelector<HTMLElement>('.page-header h1')
  if (heading === null) return
  heading.focus()
  pendingPageHeadingFocus = false
}
```

Set the flag before `router.push(path)`, call the helper after `nextTick()` for non-animated or
same-route navigation, and bind the same helper to the page transition's `after-enter` event:

```vue
<Transition name="page-fade" mode="out-in" @after-enter="focusPendingPageHeading">
```

- [ ] **Step 3: Add unit coverage for shell-initiated navigation focus**

In `frontend/tests/admin-layout.spec.ts`, navigate through the Providers menu item, wait for the
route and rendered heading, then assert:

```ts
expect(document.activeElement).toBe(wrapper.get('.page-header h1').element)
```

- [ ] **Step 4: Verify unit and E2E focus tests pass**

Run:

```bash
npm --prefix frontend test -- admin-layout.spec.ts
```

Then run the Step 1 E2E command again.

Expected: both commands PASS; pressing Tab after the focused heading reaches the first current
page action (`import-catalog`).

### Task 3: Update smoke-test locators for the current provider and model card UIs

**Files:**
- Modify: `frontend/e2e/admin-console.spec.ts`

**Interfaces:**
- Consumes: `ProviderCard` and `ModelCard` attributes including `provider-card-<id>`,
  `model-card-<id>`, `edit-provider-<id>`, `edit-model-<id>`, and route action hooks.
- Produces: Locators that find newly created cards by name and extract their numeric IDs without
  assuming the pages still render tables.

- [ ] **Step 1: Confirm the current selector fails because no row exists**

Run:

```bash
CI=1 CONSOLE_BASE_URL=http://127.0.0.1:8001/console/ \
  E2E_ADMIN_EMAIL=console-e2e-repro-20260727@example.com \
  E2E_ADMIN_PASSWORD='Local-e2e-repro-20260727!' \
  npm --prefix frontend run e2e -- \
  --grep 'creates, verifies, and safely cleans up console records'
```

Expected: FAIL while waiting for `getByRole('row')` after the provider-created notice succeeds.

- [ ] **Step 2: Replace the stale row locator**

Use the current stable card hook:

```ts
const providerCard = page.locator('[data-test^="provider-card-"]').filter({
  hasText: providerName,
})
await expect(providerCard).toContainText('停用')
entities.providerId = await numericId(
  providerCard.locator('[data-test^="edit-provider-"]'),
  'edit-provider-',
)
```

- [ ] **Step 3: Verify the smoke journey passes and cleans up records**

Apply the same card-based approach to the model portion of the smoke journey. Create a route with
`create-route-<model-id>`, expand that model card's route section, and locate the route item within
the card instead of using `getByRole('row')`.

Run the Step 1 command again.

Expected: PASS, including provider/model/route/user/API-key creation and reverse-order cleanup.

### Task 4: Run the complete quality gate and commit

**Files:**
- Verify: all changed files

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: a clean `main` commit ready to push.

- [ ] **Step 1: Run all three Playwright tests together**

```bash
CI=1 CONSOLE_BASE_URL=http://127.0.0.1:8001/console/ \
  E2E_ADMIN_EMAIL=console-e2e-repro-20260727@example.com \
  E2E_ADMIN_PASSWORD='Local-e2e-repro-20260727!' \
  npm --prefix frontend run e2e
```

Expected: `3 passed`.

- [ ] **Step 2: Run frontend unit and static checks**

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: all commands exit 0.

- [ ] **Step 3: Run backend and repository checks**

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest -W error -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src scripts
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit the verified fix**

```bash
git add frontend/src/styles/index.css frontend/src/layouts/AdminLayout.vue \
  frontend/tests/admin-layout.spec.ts frontend/e2e/admin-console.spec.ts \
  docs/superpowers/plans/2026-07-27-ci-e2e-failures.md
git commit -m "fix: stabilize console accessibility e2e"
```
