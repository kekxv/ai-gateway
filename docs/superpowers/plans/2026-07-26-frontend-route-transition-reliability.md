# Frontend Route Transition Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the unsafe hover-triggered dynamic imports and give every cached admin route an element root so route fading produces no Vue Fragment warnings.

**Architecture:** Vue Router remains the sole owner of lazy route imports. `AdminLayout` retains its Transition/KeepAlive composition, while each of the seven routed admin views supplies one neutral `.route-page` element root.

**Tech Stack:** Vue 3.5, Vue Router 4.6, Vue Test Utils 2.4, Vitest 3.2, TypeScript 5.9.

## Global Constraints

- Preserve `<Transition name="page-fade" mode="out-in">` and `<KeepAlive :max="7">`.
- Remove `routeComponentPreloads`, `preloadRouteComponent`, and the navigation `@mouseover` binding.
- Keep every route lazy-loaded through the existing router records.
- Add one `.route-page` element root to Dashboard, Providers, Models, Users, API Keys, Request Logs, and Security.
- Do not add automatic reload or swallowed-error behavior for real route navigation failures.
- Preserve the current uncommitted `auth.ready` route-guard change exactly.
- Do not modify Playwright or backend static-file routing.

---

## File Structure

- Modify `frontend/tests/admin-layout.spec.ts`: reproduce the warning with the real Transition and guard representative route changes.
- Modify `frontend/src/layouts/AdminLayout.vue`: remove speculative route preloading, retain transition/cache behavior.
- Modify seven files under `frontend/src/views/`: add the required element roots.

---

### Task 1: Reproduce and Fix Route Transition Reliability

**Files:**
- Modify: `frontend/tests/admin-layout.spec.ts:53-77,88-176`
- Modify: `frontend/src/layouts/AdminLayout.vue:48-63,146-151,209-216`
- Modify: `frontend/src/views/DashboardView.vue:239-end of template`
- Modify: `frontend/src/views/ProvidersView.vue:378-end of template`
- Modify: `frontend/src/views/ModelsView.vue:930-end of template`
- Modify: `frontend/src/views/UsersView.vue:477-end of template`
- Modify: `frontend/src/views/ApiKeysView.vue:655-end of template`
- Modify: `frontend/src/views/RequestLogsView.vue:196-end of template`
- Modify: `frontend/src/views/SecurityView.vue:238-end of template`

**Interfaces:**
- Consumes: the current RouterView slot contract and existing lazy route records.
- Produces: one active `.route-page` element beneath the cached routed component and no `non-element root node` Vue warning.

- [ ] **Step 1: Extend the shell mount helper for a real Transition**

Add `warnings?: string[]` as the second `mountShell` parameter. Replace the existing `global` value in the `mount(App, ...)` call with:

```ts
global: {
  plugins: [pinia, router],
  ...(warnings === undefined
    ? {}
    : {
        stubs: { transition: false },
        config: {
          warnHandler(message: string) {
            warnings.push(message)
          },
        },
      }),
},
```

Do not duplicate the helper body; integrate the shown optional `global` fields into the existing helper.

- [ ] **Step 2: Write the failing warning regression**

Add to the existing `管理控制台外壳` describe block:

```ts
it('通过真实过渡渲染缓存页面时不产生 Fragment 根节点警告', async () => {
  const warnings: string[] = []
  const { router, wrapper } = await mountShell(1200, warnings)

  await router.push('/providers')
  await flushPromises()

  expect(
    warnings.some((message) =>
      message.includes('Component inside <Transition> renders non-element root node'),
    ),
  ).toBe(false)
  expect(wrapper.get('.route-page').text()).toContain('供应商列表')
})
```

This catches the actual Vue warning using the real Transition; it does not assert on a transition mock.

- [ ] **Step 3: Verify RED**

Run:

```bash
cd frontend
npm exec vitest -- run tests/admin-layout.spec.ts --maxWorkers=1
```

Expected: the new test fails at the warning assertion because the warnings collector contains the non-element-root warning. Also confirm `.route-page` is absent before implementation.

- [ ] **Step 4: Remove speculative hover imports**

Delete the `routeComponentPreloads` constant and `preloadRouteComponent` function from `AdminLayout.vue`. Remove only `@mouseover="preloadRouteComponent"` from the desktop `<nav>` and leave keyboard and menu navigation intact.

Do not replace the deleted preloader with a catch block or eager imports. Existing router records remain unchanged.

- [ ] **Step 5: Add a single element root to all seven routed views**

For each view listed in this task, insert `<div class="route-page">` immediately after its opening `<template>` tag and insert the matching `</div>` immediately before its closing `</template>` tag. Indent all existing template children one level. Move no existing node outside the wrapper, rename no test selector, and add no wrapper CSS. Element Plus drawers/dialogs keep teleporting from inside the new root.

- [ ] **Step 6: Verify GREEN and existing shell behavior**

Run:

```bash
npm exec vitest -- run tests/admin-layout.spec.ts --maxWorkers=1
```

Expected: five tests pass with no Vue transition warning in output.

- [ ] **Step 7: Run focused view regressions**

Run:

```bash
npm exec vitest -- run \
  tests/dashboard.spec.ts tests/providers.spec.ts tests/models.spec.ts \
  tests/users.spec.ts tests/api-keys.spec.ts tests/request-logs.spec.ts \
  tests/security.spec.ts --maxWorkers=2 --reporter=dot
```

Expected: record the exact result. Do not alter application behavior to mask failures that were already present before this task; distinguish wrapper regressions from the known dirty-worktree baseline.

- [ ] **Step 8: Run static and production-build checks**

```bash
npm run typecheck
npm run lint
npm run build
```

Expected: typecheck and lint exit zero; Vite emits lazy chunks for all seven admin views and completes the build. Existing third-party Rollup annotation or chunk-size warnings may remain, but no Vue/template/compiler errors are allowed.

- [ ] **Step 9: Commit**

```bash
git add \
  frontend/tests/admin-layout.spec.ts \
  frontend/src/layouts/AdminLayout.vue \
  frontend/src/views/DashboardView.vue \
  frontend/src/views/ProvidersView.vue \
  frontend/src/views/ModelsView.vue \
  frontend/src/views/UsersView.vue \
  frontend/src/views/ApiKeysView.vue \
  frontend/src/views/RequestLogsView.vue \
  frontend/src/views/SecurityView.vue
git commit -m "fix: stabilize admin route transitions"
```

---

### Task 2: Integrated Verification with the Resource Guard

**Files:**
- Verify only after the frontend test resource-guard plan is also implemented.

**Interfaces:**
- Consumes: the safe `npm run test` entry point plus Task 1's route fix.
- Produces: fresh integrated evidence that the suite exits, remains bounded, and the production bundle resolves all lazy views.

- [ ] **Step 1: Run the public test entry point**

```bash
cd frontend
npm run test -- --reporter=dot
```

Expected: the direct Vitest command uses no more than two workers, applies only the configured per-operation timeouts, and exits by itself through normal Vitest behavior. The frontend owns no global suite deadline, grace-kill sequence, or timeout-specific exit code. Report exact pass/fail counts; do not claim unrelated baseline failures are fixed.

- [ ] **Step 2: Re-run the direct route regression**

```bash
npm exec vitest -- run tests/admin-layout.spec.ts --maxWorkers=1 --reporter=dot
```

Expected: five tests pass with pristine output and no Transition warning.

- [ ] **Step 3: Verify the production asset graph**

```bash
npm run build
```

Expected: exit zero and generated asset entries for Dashboard, Providers, Models, Users, ApiKeys, RequestLogs, and Security.

- [ ] **Step 4: Review ownership and diff scope**

```bash
git status --short
git diff --check
git log -6 --oneline
```

Expected: the route guard's `auth.ready` change is preserved exactly, and no backend or Playwright files changed.
