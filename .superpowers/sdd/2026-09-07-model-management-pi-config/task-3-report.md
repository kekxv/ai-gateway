# Task 3 Report: Loaded request-log cost summary

## Exact changes

- `frontend/src/utils/decimal.ts`
  - Added `sumDecimals()` using the existing `BigInt` decimal parsing model, so loaded cost totals never pass through JavaScript floating-point arithmetic.
- `frontend/src/views/RequestLogsView.vue`
  - Computes the user-cost total from the currently loaded `logs` entries.
  - Computes the internal-cost total only for admins and renders both values in the list header with `data-test` hooks.
  - Does not render or calculate the internal-cost summary for ordinary users.
- `frontend/tests/request-logs.spec.ts`
  - Added admin and ordinary-user coverage for the current-page summaries, including a value larger than `Number.MAX_SAFE_INTEGER` with fractions to prevent float-based regressions.

## TDD evidence

### RED

Command:

```sh
npm --prefix frontend test -- --run tests/request-logs.spec.ts
```

Result: failed as expected before implementation — 2 new tests failed because `[data-test="log-summary-user-cost"]` was absent. Existing tests passed (13 passed, 2 failed).

### GREEN

Command:

```sh
npm --prefix frontend test -- --run tests/request-logs.spec.ts
```

Result: passed — 1 test file, 15/15 tests.

## Verification

Focused test command:

```sh
npm --prefix frontend test -- --run tests/request-logs.spec.ts
```

Result: passed — 1 file, 15/15 tests.

Full frontend test command:

```sh
npm --prefix frontend test
```

Result: passed — 22 files, 311/311 tests.

Additional checks:

- `npm --prefix frontend run typecheck`: passed.
- `git diff --check`: passed with no whitespace errors.
- `npm --prefix frontend run lint`: blocked by an unrelated pre-existing error in `frontend/tests/client-config.spec.ts:156` (`@typescript-eslint/no-unsafe-member-access` on `.providers`).

## Files changed

- `frontend/src/utils/decimal.ts`
- `frontend/src/views/RequestLogsView.vue`
- `frontend/tests/request-logs.spec.ts`

## Self-review and concerns

- Totals derive solely from the reactive `logs` array, which is replaced with each cursor page; no cross-page accumulation occurs.
- The large-number test validates exact aggregation without a `Number` conversion.
- `internalCostTotal` returns before accessing `cost_amount` for ordinary users, and the corresponding DOM element is admin-gated; member tests assert that it is absent.
- No task-specific concerns found. The unrelated untracked `docs/superpowers/plans/2026-09-07-model-management-pi-config.md` was not modified or staged.
