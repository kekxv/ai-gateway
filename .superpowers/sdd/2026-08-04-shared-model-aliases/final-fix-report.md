# Final fix report: HALF_OPEN claim lifecycle

## Status

**COMPLETE WITH KNOWN OUT-OF-SCOPE TEST FAILURE.** Both reviewed gateway claim leaks are
fixed and all in-scope verification is green. The undiscriminated full suite still has the
previously documented refresh-token replay failure; authentication code and tests were not
changed.

## Commit

Implementation commit: `75ea57f85b7f65048445c27c66ca02cf0acbf392`
(`fix: release unstarted half-open route claims`)

The controller-owned untracked plan
`docs/superpowers/plans/2026-08-04-shared-model-aliases.md` was not staged or modified.

## Changes

- HTTP failure cleanup now conditionally releases the actual final attempt route, not only
  the original route. Stream-prefetch cancellation is annotated with its attempt route so
  the same cleanup owns retry-selected probes.
- WebSocket setup tracks whether upstream relay has started. A selected HALF_OPEN route is
  conditionally and neutrally released only when setup exits before relay.
- Existing conditional `release_half_open` semantics remain authoritative: a route already
  transitioned by health success/failure is not changed.
- Cancellation propagation, upstream-start boundaries, relay outcomes, and close/error
  behavior are unchanged.

## Strict TDD evidence

### HTTP retry-selected cancellation RED

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/gateway/test_failover.py::test_retry_selected_half_open_probe_is_released_when_cancelled -q
```

Before the production fix: exit `1`; both `send` and `stream_prefetch` cases failed because
the persisted retry route remained `RouteRuntimeState.HALF_OPEN` instead of returning to
`RouteRuntimeState.OPEN` (`2 failed in 0.65s`). Cancellation identity propagated and exactly
two upstream attempts occurred.

After the production fix: exit `0`; `2 passed in 0.55s`.

### WebSocket pre-relay insufficient balance RED

```bash
uv run pytest tests/contract/gateway/test_websocket.py::test_insufficient_balance_closes_4402_before_upstream_connect -q
```

Before the production fix: exit `1`; the selected HALF_OPEN route recorded no neutral release
(`[]` instead of `[1]`) while the relay remained uncalled.

After the production fix: exit `0`; `1 passed in 0.01s`. The existing 4402
`insufficient_balance` close remains unchanged, with no route success or failure recorded.

## Verification evidence

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/gateway/test_failover.py tests/contract/gateway/test_websocket.py -q
```

Exit `0`: `37 passed in 1.04s` on the final fresh run.

```bash
uv run ruff check src tests migrations
```

Exit `0`: `All checks passed!`

```bash
uv run mypy src
```

Exit `0`: `Success: no issues found in 85 source files`.

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -q
```

Exit `1`: `1 failed, 1140 passed in 32.96s`. The only failure was
`tests/integration/auth/test_login_totp.py::test_refresh_token_returns_new_access_token`,
where refresh-token replay returned HTTP 200 instead of the expected 401.

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/auth/test_login_totp.py::test_refresh_token_returns_new_access_token -q
```

Exit `1`: the same isolated auth assertion failed (`1 failed in 0.59s`).

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -q --deselect tests/integration/auth/test_login_totp.py::test_refresh_token_returns_new_access_token
```

Exit `0`: `1140 passed, 1 deselected in 32.91s`.

## Concerns

- The known refresh-token replay test remains red and is explicitly outside this final fix
  wave. Its file has no diff, and the instruction not to alter the auth test was preserved.
- No scoped implementation or verification concerns remain.
