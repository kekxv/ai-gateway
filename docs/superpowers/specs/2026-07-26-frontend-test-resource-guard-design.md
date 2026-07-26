# Frontend Test Resource Guard Design

## Goal

Make `npm run test` the safe default frontend unit-test entry point: it must avoid host saturation by bounding concurrency, finish within a bounded wall-clock time, preserve complete failure reporting, and clean up its Vitest worker processes when the suite exceeds its deadline.

## Scope

This change applies to the Vitest unit-test command in `frontend/package.json`. The existing `npm run test:watch` command remains an intentionally long-lived watch-mode command. Playwright E2E execution remains governed by `frontend/playwright.config.ts` and is outside this change.

## Command Contract

- Developers and CI continue to invoke `npm run test`; no new normal-use command is required.
- Arguments after `npm run test --` are forwarded unchanged to Vitest.
- The default suite deadline is 120 seconds.
- A normal Vitest exit code is propagated unchanged.
- A suite deadline terminates the Vitest process group, escalates to a forced kill after a 10-second grace period, and returns exit code 124.
- User cancellation signals are forwarded so the wrapper does not leave worker processes behind.

## Resource Policy

Vitest runs at most two workers in both run and watch modes. File parallelism remains enabled, so two files may execute concurrently. Tests continue after individual failures so a normal run reports the complete failure set.

The following currently implicit per-operation limits become explicit configuration:

- Test timeout: 5 seconds
- Hook timeout: 10 seconds
- Teardown timeout: 10 seconds

These limits do not replace the 120-second suite deadline. The outer deadline covers collection, transformation, reporter work, and worker shutdown, which Vitest's per-test limits do not fully bound.

## Components

### Vitest configuration

`frontend/vite.config.ts` owns worker and per-operation limits. It sets `maxWorkers: 2`, `testTimeout: 5_000`, `hookTimeout: 10_000`, and `teardownTimeout: 10_000`. It does not enable fail-fast behavior.

### Test command wrapper

A small Node-based runner under `frontend/scripts/` launches the repository-local Vitest CLI in run mode. The wrapper owns the suite deadline, signal forwarding, process-group cleanup, exit-code propagation, and argument forwarding. It uses only Node standard-library APIs and adds no runtime dependency.

`frontend/package.json` changes only the implementation behind the existing `test` script. The `test:watch` and `e2e` commands retain their current meanings.

## Failure Handling

- If Vitest exits normally, its status or terminating signal determines the wrapper result.
- At 120 seconds, the wrapper writes one concise timeout message, requests graceful termination, then force-kills the process group after 10 seconds if needed.
- If the runner cannot start Vitest, it reports the startup error and exits nonzero.
- Cleanup timers are cleared after child exit so a successful run does not keep Node alive.

## Verification

Automated tests cover:

1. A short-lived child process exits normally and its exit code is propagated.
2. A child exceeding a short injected deadline is terminated and produces exit code 124.
3. CLI arguments are forwarded to the launched command.
4. The resolved Vitest configuration contains the two-worker and timeout limits.

Verification also runs lint, type checking, the focused runner/configuration tests, and the full `npm run test` entry point. Existing unrelated test failures, if still present, are reported separately rather than changed as part of this work.

## Non-goals

- Changing application behavior or existing frontend component tests.
- Making watch mode terminate automatically.
- Changing Playwright worker or global-timeout policy.
- Hiding failures by enabling Vitest `bail`.
