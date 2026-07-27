# Frontend Test Resource Guard Design

## Goal

Keep `npm run test` as the standard Vitest entry point while preventing routine frontend unit-test runs from saturating the host. Bound worker concurrency and individual test operations in Vitest itself without adding a suite-level process manager.

## Simplified Decision

The user chose normal frontend/Vitest process behavior. The application does not launch Vitest through a custom runner, track its process tree, or impose a global wall-clock deadline. A CI system or other external job supervisor may bound an entire test run when that environment requires one.

This decision replaces the earlier custom suite-runner design. The remaining resource policy is expressed entirely through standard Vitest configuration.

## Scope

This change applies to the Vitest unit-test commands in `frontend/package.json` and the `test` section of `frontend/vite.config.ts`. The existing `npm run test:watch` command remains an intentionally long-lived watch-mode command. Playwright E2E execution remains governed by `frontend/playwright.config.ts` and is outside this change.

## Command Contract

- `npm run test` directly runs `vitest run`.
- Arguments after `npm run test --` are handled by the standard npm-to-Vitest forwarding path.
- Vitest's normal exit and signal behavior is preserved.
- `npm run test:watch` remains `vitest`.
- There is no application-owned suite deadline, timeout-specific exit-code translation, signal relay, or process-tree cleanup layer.

## Resource Policy

Vitest runs at most two workers in both run and watch modes. File parallelism remains enabled, so two files may execute concurrently. Tests continue after individual failures so a normal run reports the complete failure set.

The explicit per-operation limits are:

- Test timeout: 5 seconds
- Hook timeout: 10 seconds
- Teardown timeout: 10 seconds

These are operation limits, not a bound on collection, transformation, reporting, or total suite duration. Environments that require a whole-run limit should configure it in CI or another external job supervisor.

## Components

### Vitest configuration

`frontend/vite.config.ts` owns worker and per-operation limits. It sets `maxWorkers: 2`, `testTimeout: 5_000`, `hookTimeout: 10_000`, and `teardownTimeout: 10_000`. It does not enable fail-fast behavior.

### Package commands

`frontend/package.json` keeps the normal commands direct: `test` is `vitest run` and `test:watch` is `vitest`. No helper script or additional runtime dependency is required.

### Configuration regression

`frontend/tests/test-runtime-config.spec.ts` asserts the worker and per-operation settings. Process-runner, deadline, and platform-specific process-tree tests are intentionally absent because that behavior is no longer owned by the frontend application.

## Failure Handling

Vitest reports failures and determines the process exit status using its standard behavior. The frontend package does not reinterpret exit codes or attempt to terminate descendant processes. CI cancellation and job-level timeout handling remain external concerns.

## Verification

Verification covers the focused runtime-policy regression, the full direct `npm run test` command, type checking, owned lint targets, and diff hygiene. The final tree is also checked for removed custom runner, process-tree, and deadline artifacts.

## Non-goals

- Enforcing a total suite duration from application code.
- Owning cross-platform process discovery or termination.
- Making watch mode terminate automatically.
- Changing Playwright worker or global-timeout policy.
- Hiding failures by enabling Vitest `bail`.
