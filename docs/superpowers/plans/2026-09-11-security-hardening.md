# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute sequential tasks with task-scoped review and one final review.

**Goal:** Repair audit items 1, 2, 4, 5, 6, 8, 9 while preserving intentional administrator network access and user model visibility.
**Architecture:** Validate production secrets at startup; normalize audit credential keys; sanitize untrusted inbound query authentication separately from trusted provider authentication; make deployments require unique secrets and bind HTTP to loopback; provide TLS proxy configuration; update verified vulnerable dependencies and pin container sources.
**Tech Stack:** Python 3.12, FastAPI, httpx, pytest, Docker Compose, Vue/Vite/npm.
**Spec:** User instruction in current conversation, dated 2026-09-11. No separate spec file.

## Global Constraints

- Fix only audit items 1, 2, 4, 5, 6, 8, 9; administrator access to internal networks and logged-in user catalog visibility are intentional and must remain unchanged.
- Preserve provider authentication for OpenAI, Claude, Gemini, custom headers, and administrator-configured URL credentials; never fall back to forwarding client credentials to avoid a 401.
- Do not rotate existing secrets, touch live services/data, push, or merge. Existing encrypted data needs its existing encryption key; document deliberate migration steps.
- Use failing regression tests before behavior changes, focused checks after each change, and report exact commands/results. No subagents may be spawned by workers.
- Each worker edits only its task scope in /root/projects/ai-gateway/.worktrees/security-hardening and commits its changes; preserve unrelated user files.

### Task 1: Production secret validation and audit redaction

**Files:** src/ai_gateway/core/config.py, core/security.py or a small core secret-validation module, main.py; src/ai_gateway/audit/redaction.py; tests/unit/auth/test_security.py or new test_runtime_settings.py; tests/unit/audit/test_redaction.py. Avoid deployment files (Task 3).
**Interfaces:** Preserve validate_runtime_settings(settings) entry point and redaction function signatures. Validation is production-only; test/development continue accepting intentional fixtures.

- [ ] Add and run failing tests: production rejects JWT <32 UTF-8 bytes, whitespace/known placeholders (including former example JWT), repeated/predictable weak values; Fernet malformed or constant decoded bytes (including former example key). Accept secrets.token_urlsafe(32) JWT and Fernet.generate_key(). Error messages must not include secret input. Preserve strong existing keys; cannot prove entropy from a string, so document heuristics honestly rather than claiming certification.
- [ ] Implement focused production validation, preserving the existing startup call. Reject structurally invalid Fernet keys with strict URL-safe Base64 decoding and exactly 32 decoded bytes, and obviously weak decoded byte patterns. JWT must be at least 32 bytes, non-placeholder, not obviously repeated/low-diversity. Do not invent arbitrary character-class requirements that reject random hex strings.
- [ ] Add and run failing recursive redaction tests: apiKey, API-KEY, accessToken, refreshToken, clientSecret, authToken, privateKey, credential(s), nested maps/lists are redacted; preserve ordinary content, model keys, max_tokens and token counts; do not mask all text containing 'token'.
- [ ] Normalize known credential keys consistently across case, underscore and hyphen. Retain existing redacted keys and immutability behavior; extend exact normalized key set rather than indiscriminate substring matching.
- [ ] Run focused pytest and ruff checks; commit; write task-1-report.md with red/green evidence, decisions and validation limitations.

### Task 2: Query credential isolation without upstream 401 regressions

**Files:** src/ai_gateway/gateway/service.py, gateway/websocket.py if equivalent query path exists, transport/upstream.py or a focused shared query helper; tests/contract/gateway/test_non_streaming.py, test_streaming.py, test_websocket.py; relevant transport tests.
**Interfaces:** ProviderCredential.auth_headers remains authoritative. Trusted base_url/websocket_url query parameters stay intact. Inbound protocol tuning params (beta, api-version, alt=sse etc.) retain compatibility unless colliding with trusted configured params.

- [ ] Trace HTTP/WebSocket query composition and write failing tests showing client key/api_key/apiKey/access_token/authToken/authorization/password/client_secret variants never enter upstream URL; include duplicate and percent-encoded keys.
- [ ] Filter normalized credential parameter names only on untrusted client query input. Preserve trusted configured query values and provider protocol-generated parameters (Gemini streaming alt=sse) against client override. Retain permitted non-auth params, duplicates where supported, and route model rewrites. Do not apply a narrow whitelist that breaks provider extensions.
- [ ] Verify authentication using a mock upstream that returns 401 unless it receives the configured provider credential, then assert successful proxied requests for OpenAI bearer, Claude x-api-key, Gemini x-goog-api-key, and custom-header/provider-URL auth. Include streaming and WebSocket coverage where queries are merged. Confirm real upstream 401 behavior remains the existing behavior; never replace provider credentials with inbound gateway keys.
- [ ] Run affected contract/transport tests and lint, commit, write task-2-report.md with test evidence and compatibility notes.

### Task 3: Secure Compose defaults, database credentials and HTTPS deployment

**Files:** compose.yaml, example/compose.yaml, .env.example, example/.env.example if useful, Dockerfile only if necessary for deployment, new deploy/Caddyfile and compose.https.yaml if needed, README.md, README.zh-CN.md, example/README.md, docs/operations.md, tests/unit/test_compose_config.py. Task 4 owns final image digests.
**Interfaces:** Production settings validation from Task 1. Both deployment variants must require nonempty explicit JWT/Fernet/MySQL passwords; gateway HTTP binding defaults to 127.0.0.1. Development may explicitly choose development environment but example must not force it or ship usable fixed secrets.

- [ ] Add/run failing Compose config tests for missing secrets rejection and loopback published gateway port, preserving existing bootstrap isolation and migration dependency behavior. Use explicit synthetic test secrets to render configs; never print actual .env values.
- [ ] Remove password/secret fallbacks from both Compose files and .env.example. Require explicit secrets via ${VAR:?message}, use production environment for deployed gateway, remove implicit gateway:gateway database URL default or ensure it cannot be silently used in production. Document generating distinct random URL-safe passwords/JWT and Fernet key; avoid silent regeneration of existing keys.
- [ ] Bind unencrypted HTTP to loopback. Provide an executable, optional HTTPS reverse-proxy Compose overlay/config with HTTP->HTTPS redirect, certificate automation for supplied domain, WebSocket/streaming support and security headers that do not break the Vue console. For container proxy, connect over Docker service name, not localhost. Keep healthchecks working. Validate config where tooling exists; document domain/DNS requirements without claiming a live certificate was issued.
- [ ] Resolve database least privilege concretely: separate migration/setup privileges from runtime SELECT/INSERT/UPDATE/DELETE privileges if practical using an initialization script; preserve existing-volume upgrade instructions and safe SQL parameter handling. Do not silently break migration/bootstrap or test schema setup; disposable test schema privileges must not leak to runtime production DB. Record any deliberate narrower resolution.
- [ ] Update English/Chinese quickstarts and operations instructions to match actual env names, commands, local vs public URLs and initialization order. Warn users replacing JWT invalidates sessions and changing Fernet requires re-encryption; changing .env MySQL credentials alone does not update existing users.
- [ ] Validate root/example/HTTPS Compose configs and focused regression tests; commit and write task-3-report.md including runtime/TLS verification limitations.

### Task 4: Verified dependency remediation and immutable images

**Files:** frontend/package.json, frontend/package-lock.json, Dockerfile, compose*.yaml, example/compose.yaml as needed for image digest pins; docs/operations.md for maintenance notes.
**Interfaces:** Preserve Task 3's deployment semantics; inspect actual advisories instead of assuming prior audit report versions/severity are accurate.

- [ ] Run npm audit --json and npm audit --omit=dev --json; save exact advisory/package findings. Inspect npm dependency paths and patched releases.
- [ ] Update vulnerable dependency resolutions narrowly to supported patched versions (including build-only findings), keeping lockfile reproducible; use overrides only when necessary and explain them. Never hide vulnerabilities via audit ignores.
- [ ] Resolve immutable multi-platform image manifest digests from registries for all Dockerfile FROM/COPY --from external images and Compose image sources (including TLS proxy introduced by Task 3). Pin tag@sha256 digest, retain supported versions and explain refresh commands. Do not fabricate digests or replace multi-arch images with host-only manifests.
- [ ] Run npm ci, npm audit, frontend build/typecheck and relevant frontend tests; Dockerfile/Compose syntax validation. If registry access blocks anything, report actual evidence and remaining work.
- [ ] Commit, write task-4-report.md with advisory before/after and resolved digest verification evidence.
