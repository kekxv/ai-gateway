# Task 2 report: query credential isolation

## Status

Implemented and committed. Commit: pending (created after this report).

## Red/green evidence

Regression tests were added first in `tests/contract/gateway/test_websocket.py` for credential query-name variants (including duplicate parameters and percent-encoded names) and trusted query collision behavior. Before the production change, the focused run failed with 8 failures: camel-case, token, authorization, password, client-secret, percent-encoded API key, and trusted `alt`/`beta` overrides were forwarded upstream.

After implementation:

```text
uv run pytest -q tests/contract/gateway/test_websocket.py -k 'rewrite_upstream_url'
11 passed, 27 deselected

uv run pytest -q tests/contract/gateway/test_websocket.py -k 'rewrite_upstream_url' \
  tests/contract/gateway/test_non_streaming.py -k 'upstream_urls_use_native_generation_endpoints'
1 passed, 106 deselected

uv run ruff check src/ai_gateway/transport/upstream.py \
  src/ai_gateway/transport/websocket.py src/ai_gateway/gateway/service.py \
  tests/contract/gateway/test_websocket.py
All checks passed!
```

## Implementation

`merge_upstream_query` now parses provider and inbound query pairs, drops normalized client credential names (`key`, API-key variants, access/auth tokens, authorization, password, client secret/credential, token, and secret), preserves duplicate permitted extension parameters, and ignores inbound values that collide with configured provider parameters. HTTP gateway passthrough and WebSocket URL rewriting both use this helper.

`upstream_url` now parses configured base URLs so trusted query parameters survive endpoint path generation. Gemini's generated `alt=sse` remains authoritative when client query parameters attempt to override it.

## Compatibility notes

Non-authentication query extensions continue to pass through, including duplicates. Provider-configured query values remain intact. Model rewrites and Gemini streaming endpoint generation are preserved. The existing provider-authentication header path remains authoritative, so inbound gateway credentials cannot replace OpenAI, Claude, Gemini, or custom provider credentials.

## Concerns

The focused regression suite covers URL composition directly; full contract and integration suites should still be run by the parent task before merge.
