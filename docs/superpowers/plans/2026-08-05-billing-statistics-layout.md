# Billing Statistics Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the billing-statistics filter area compact, readable, and responsive without changing its query semantics or role-based visibility.

**Architecture:** Keep the existing `BillingStatisticsView` data flow and Element Plus controls. Restructure only the filter markup and scoped styles into a primary date-range group and a compact secondary filter group, with CSS Grid breakpoints that prevent the date picker from overflowing. Tests exercise the rendered controls and user-visible layout contract, while the current API tests continue to protect query serialization.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Element Plus, Vitest, Vue Test Utils.

## Global Constraints

- Keep administrator-only provider filtering and internal financial figures unchanged.
- Keep regular users’ API Key labels free of email and ID data.
- Preserve the existing selected date range and multi-select query behavior.
- Use Chinese UI copy.
- Do not add dependencies.

---

### Task 1: Protect the filter layout contract

**Files:**
- Modify: `frontend/tests/billing-statistics.spec.ts`
- Test: `frontend/tests/billing-statistics.spec.ts`

**Interfaces:**
- Consumes: `BillingStatisticsView` and its existing `data-test="provider-filter"` selector.
- Produces: tests for the primary date filter, quick time range presets, and compact secondary filters.

- [x] **Step 1: Write the failing rendering tests**

Add an administrator test that checks for `data-test="billing-date-range"`, the three quick-range controls (`today`, `7d`, `30d`), and a separate `data-test="billing-secondary-filters"` container that holds provider, model, and API Key inputs.

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm --prefix frontend test -- --run tests/billing-statistics.spec.ts`

Expected: FAIL because the current page has one unstructured grid and no quick-range controls or filter group selectors.

- [x] **Step 3: Implement the minimal layout structure**

In `frontend/src/views/BillingStatisticsView.vue`, add `setQuickRange(days: number)` and `setTodayRange()` handlers that update `selectedRange`. Wrap the date picker in `billing-date-range`, render compact preset buttons, and move the remaining filter items into `billing-secondary-filters` without changing their `v-model` bindings or the query button action.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `npm --prefix frontend test -- --run tests/billing-statistics.spec.ts`

Expected: PASS with the existing role-visibility tests and new layout test passing.

### Task 2: Make the filter card responsive and compact

**Files:**
- Modify: `frontend/src/views/BillingStatisticsView.vue`
- Test: `frontend/tests/billing-statistics.spec.ts`

**Interfaces:**
- Consumes: the `billing-date-range` and `billing-secondary-filters` containers created in Task 1.
- Produces: a non-overflowing desktop and mobile filter layout.

- [x] **Step 1: Write the failing layout-state test**

Extend the rendering test to select the 7-day preset and assert that it triggers a subsequent statistics request with a valid increasing `startAt` / `endAt` range. This catches an inert visual-only preset button.

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm --prefix frontend test -- --run tests/billing-statistics.spec.ts`

Expected: FAIL because the preset button does not exist and cannot update the range.

- [x] **Step 3: Implement responsive scoped CSS**

Replace the five-column `.filters` grid with a stacked filter-card header: a `minmax(20rem, 1.35fr)` date-range column and a responsive secondary grid. Set `min-width: 0` on grid children and date-picker wrappers, keep the query action aligned at desktop widths, then stack controls at tablet and mobile widths.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `npm --prefix frontend test -- --run tests/billing-statistics.spec.ts`

Expected: PASS; the tested preset makes a new request using a valid date range.

### Task 3: Verify the completed page

**Files:**
- Modify: `frontend/src/views/BillingStatisticsView.vue`
- Modify: `frontend/tests/billing-statistics.spec.ts`

- [x] **Step 1: Run focused regression tests**

Run: `npm --prefix frontend test -- --run tests/billing-statistics.spec.ts tests/billing-statistics-api.spec.ts`

Expected: PASS; UI behavior and multi-select query serialization remain intact.

- [x] **Step 2: Run full frontend checks**

Run: `npm --prefix frontend test && npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run build && git diff --check`

Expected: all commands return status 0.

## Self-Review

- The card no longer relies on a five-column row that can clip the date range.
- Desktop and narrow viewports have deliberate grid rules with `min-width: 0` safeguards.
- Quick ranges alter the real date query, rather than only changing visual state.
- Provider selection remains administrator-only; model/API Key selection remains available to both roles.
- No placeholder tasks or undefined interfaces remain.
