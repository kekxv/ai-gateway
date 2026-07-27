# User Catalog Import/Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned provider/model configuration bundle that administrators can export and merge-import, plus a legacy Go SQLite exporter that emits the same bundle for one selected user.

**Architecture:** A focused `configuration` module owns bundle schemas, deterministic export, and transactional merge import using stable names instead of database IDs. The current Python catalog remains global; the legacy script uses source ownership and channel bindings only to choose which provider/model graph belongs in the bundle. JSON exports omit secrets by default and include decrypted provider credentials and protocol headers only after an explicit option; imports never delete resources omitted from the bundle.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy/MySQL, stdlib `sqlite3`, Vue 3, TypeScript, Vitest/MSW, pytest.

## Global Constraints

- Bundle format identifier is exactly `ai-gateway.catalog` and version is exactly `1`.
- Bundle contents are limited to providers, provider protocols, models, aliases, model routes, prices, cache prices, and provider/model price multipliers; users, passwords, TOTP, balances, ledger entries, gateway API keys, request logs, conversations, skills, tools, and source channels are excluded.
- Current-project export and import endpoints are administrator-only and live under `/admin/configuration`.
- Export omits provider credentials and protocol extra headers by default; `include_secrets=true` is the only way to include them.
- A redacted provider credential is represented as `null`, not `{}`; importing `null` preserves an existing credential and creates a new provider with `{}`.
- A redacted protocol `extra_headers` value is `null`; import preserves existing headers for an existing protocol and stores no headers for a new protocol.
- Import mode is merge-only: update matching resources and create missing resources, but never delete providers, protocols, models, aliases, or routes that are absent from the bundle.
- Provider identity is `name`; model identity is `canonical_name`; protocol identity is `(provider name, protocol, base_url)`; route identity is `(model canonical_name, provider name, protocol, base_url)`.
- Alias conflicts across different canonical models reject the entire import transaction with HTTP 409.
- Legacy Go protocol name `anthropic` maps to current protocol name `claude`.
- Legacy Go model input/output prices are integer units of 1/10000 USD per 1K tokens and convert to current per-million USD using `Decimal(source_price) / Decimal("10")`.
- Legacy cache read/write prices are exported as `0`, and provider/model multipliers are exported as `1.00` because the legacy schema has no equivalent fields.
- The legacy exporter accepts a source user ID or email, follows owned channels plus API-key channel bindings to provider/model associations, includes directly owned providers/models, and adds unowned records only when `--include-unowned` is explicitly supplied.
- The legacy exporter writes UTF-8 JSON with mode `0600`, uses an atomic replace, never modifies SQLite, and includes provider API keys only with `--include-secrets`.
- All production behavior is developed test-first with a witnessed failing test before implementation.

---

### Task 1: Versioned Bundle Backend and Admin API

**Files:**
- Create: `src/ai_gateway/admin/configuration.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/integration/admin/test_configuration.py`

**Interfaces:**
- Produces: `CatalogBundle`, `export_catalog_bundle(session, settings, include_secrets)`, `import_catalog_bundle(session, settings, bundle)`, `GET /admin/configuration/export`, and `POST /admin/configuration/import`.
- Bundle provider objects contain `name`, `credential`, `enabled`, `auto_load_models`, `model_sync_interval_seconds`, `price_multiplier`, and `protocols`.
- Bundle model objects contain `canonical_name`, `display_name`, four per-million prices, `price_multiplier`, `enabled`, `routing_strategy`, `aliases`, and `routes`.
- Import response contains literal integer fields `providers_created`, `providers_updated`, `models_created`, `models_updated`, `routes_created`, and `routes_updated`.

- [ ] **Step 1: Write failing integration tests for deterministic redacted export**

  Seed an administrator, a provider with encrypted credential `{"api_key":"upstream-secret"}`, an encrypted protocol header `{"X-Tenant":"secret-tenant"}`, a provider multiplier `1.25`, a model with all four prices, multiplier `1.50`, one enabled and one disabled alias, and a route. Assert `GET /admin/configuration/export` returns:

  ```json
  {
    "format": "ai-gateway.catalog",
    "version": 1,
    "providers": [{"name": "provider-a", "credential": null}],
    "models": [{"canonical_name": "model-a"}]
  }
  ```

  Assert the complete literal fields, decimal JSON values, alias states, route reference names, deterministic name sorting, `content-disposition: attachment; filename="ai-gateway-catalog-v1.json"`, and absence of both secret strings.

- [ ] **Step 2: Run the redacted export test and verify RED**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_configuration.py::test_admin_exports_deterministic_redacted_catalog_bundle -q
  ```

  Expected: FAIL because `/admin/configuration/export` is not registered.

- [ ] **Step 3: Add minimal bundle schemas and redacted export endpoint**

  Implement strict Pydantic bundle models in `configuration.py`, query providers with protocols and models with aliases/routes, decrypt only to decide/export secret values, serialize with `orjson`, and register the router in `main.py`. Route references must use names:

  ```python
  class CatalogRoute(BaseModel):
      model_config = ConfigDict(extra="forbid")

      provider: CatalogName
      protocol: Protocol
      base_url: BaseUrl
      upstream_model: CatalogName
      weight: int = Field(ge=1, le=10000)
      enabled: bool = True
  ```

- [ ] **Step 4: Run the redacted export test and verify GREEN**

  Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Write failing tests for explicit secret export and authorization**

  Assert `GET /admin/configuration/export?include_secrets=true` contains the literal decrypted credential and extra headers. Assert a regular user receives 403 from both export and import endpoints.

- [ ] **Step 6: Run the focused tests and verify RED**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_configuration.py -k 'secrets or requires_admin' -q
  ```

  Expected: FAIL because secret inclusion and/or import authorization behavior is missing.

- [ ] **Step 7: Implement explicit secret export and admin dependency**

  Use `admin_user`, `decrypt_secret`, and `orjson.loads`. Never log decrypted objects. Keep `include_secrets` defaulted to `False` in the endpoint signature.

- [ ] **Step 8: Run the focused tests and verify GREEN**

  Run the command from Step 6. Expected: PASS.

- [ ] **Step 9: Write failing merge-import and rollback tests**

  Cover these literal behaviors:

  - Empty database import creates provider, protocols, model, aliases, and route.
  - Re-import updates prices, cache prices, multipliers, enabled flags, route weight, and route upstream model without duplicates.
  - A bundle credential/header of `null` preserves existing encrypted values.
  - A new provider with credential `null` receives encrypted `{}`.
  - Existing resources absent from the bundle remain untouched.
  - An alias already owned by another model returns 409 code `catalog_import_conflict`, and no provider/model changes from the failed bundle commit.
  - Invalid format/version and dangling route references return 422 validation errors.

- [ ] **Step 10: Run merge-import tests and verify RED**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_configuration.py -k 'import' -q
  ```

  Expected: FAIL because merge import is not implemented.

- [ ] **Step 11: Implement transactional merge import**

  Validate all bundle references and global alias ownership before mutating. Upsert providers/protocols first, models/aliases second, and routes last. Use one session transaction and catch `IntegrityError` to rollback and raise:

  ```python
  raise_auth_error(
      status.HTTP_409_CONFLICT,
      "catalog_import_conflict",
      "The catalog bundle conflicts with existing provider, model, alias, or route names",
  )
  ```

  Existing protocols retain encrypted headers when incoming `extra_headers is None`; existing providers retain credentials when incoming `credential is None`. Imported routes use `RouteSource.MANUAL`, reset transient health to closed/zero/no-error on creation only, and do not overwrite health fields on update.

- [ ] **Step 12: Run the complete backend feature tests and verify GREEN**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_configuration.py -q
  ```

  Expected: all tests pass.

- [ ] **Step 13: Commit Task 1**

  ```bash
  git add src/ai_gateway/admin/configuration.py src/ai_gateway/main.py tests/integration/admin/test_configuration.py
  git commit -m "feat: add catalog configuration import export API"
  ```

---

### Task 2: Legacy Go SQLite User Exporter

**Files:**
- Create: `scripts/export_legacy_sqlite_catalog.py`
- Test: `tests/unit/test_export_legacy_sqlite_catalog.py`

**Interfaces:**
- Consumes: Task 1 bundle JSON contract.
- Produces: `export_legacy_catalog(database_path, user_selector, include_unowned, include_secrets) -> dict[str, object]` and CLI `python scripts/export_legacy_sqlite_catalog.py DATABASE --user USER --output FILE [--include-unowned] [--include-secrets]`.

- [ ] **Step 1: Write a failing real-SQLite fixture test for user graph selection**

  Build a temporary SQLite database with the legacy quoted table names and camelCase columns: `User`, `Provider`, `ProviderType`, `Channel`, `ChannelProvider`, `ChannelAllowedModel`, `GatewayApiKey`, `GatewayApiKeyChannel`, `Model`, `ModelAlias`, and `ModelRoute`. Seed two users and unrelated graphs. For the selected user, seed one owned channel linked to one provider and one model plus a second directly owned model. Assert the exported literal provider/model names include only the selected graph and that source channels/API keys are absent from JSON.

- [ ] **Step 2: Run the graph test and verify RED**

  Run:

  ```bash
  uv run pytest tests/unit/test_export_legacy_sqlite_catalog.py::test_exports_only_selected_user_catalog_graph -q
  ```

  Expected: FAIL because the script module does not exist.

- [ ] **Step 3: Implement schema inspection, user resolution, and graph selection**

  Open SQLite with URI read-only mode `file:{quoted_path}?mode=ro`. Resolve `--user` as an integer ID when decimal, otherwise by exact email. Seed selected channel IDs from `Channel.userId` and `GatewayApiKeyChannel` joined through `GatewayApiKey.userId`; seed provider/model IDs from direct ownership and channel association tables. Include only routes whose model and provider are both selected. Missing optional legacy tables must behave as empty sets; missing core `User`, `Provider`, or `Model` tables must raise `LegacyExportError`.

- [ ] **Step 4: Run the graph test and verify GREEN**

  Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Write failing conversion, global-data, and secret tests**

  Assert:

  - `inputTokenPrice=30` exports `input_price_per_million="3"` and `outputTokenPrice=60` exports `"6"`.
  - Cache prices export as `"0"`; model/provider multipliers export as `"1.00"`.
  - `anthropic` becomes `claude`, while `openai` and `gemini` remain unchanged.
  - Provider types prefer `ProviderType` rows and fall back to `types`, then deprecated `type`, then `openai`; duplicate `(protocol, base_url)` rows collapse deterministically.
  - Default export sets provider `credential` to `null`; `--include-secrets` emits `{"api_key":"legacy-secret"}`.
  - Unowned records are excluded by default and included only with `--include-unowned`.
  - Alias duplicates within one model collapse, but one alias used by different models raises `LegacyExportError`.
  - A route exports `upstream_model` equal to the legacy model `name`, with `enabled = not disabled` and original weight clamped only by rejecting values outside 1..10000.

- [ ] **Step 6: Run conversion tests and verify RED**

  Run:

  ```bash
  uv run pytest tests/unit/test_export_legacy_sqlite_catalog.py -k 'price or protocol or secret or unowned or alias or route' -q
  ```

  Expected: FAIL because conversion behavior is incomplete.

- [ ] **Step 7: Implement deterministic legacy conversion**

  Use `Decimal` for prices, `json.loads` for legacy `types`, sorted output, and the exact Task 1 bundle keys. Do not import application database modules so the script remains usable next to only the old SQLite file.

- [ ] **Step 8: Run conversion tests and verify GREEN**

  Run the command from Step 6. Expected: PASS.

- [ ] **Step 9: Write failing CLI behavior tests**

  Execute `main([...])` against the real fixture and assert:

  - Successful output parses as JSON, is mode `0600`, and reports counts without printing secrets.
  - Existing output requires `--force`.
  - Unknown user, invalid database, and malformed legacy JSON return exit code 1 with a concise stderr error.
  - Atomic write leaves no partial output when serialization/write is forced to fail.

- [ ] **Step 10: Run CLI tests and verify RED**

  Run:

  ```bash
  uv run pytest tests/unit/test_export_legacy_sqlite_catalog.py -k 'cli or output or unknown or atomic' -q
  ```

  Expected: FAIL because the CLI and atomic writer are missing.

- [ ] **Step 11: Implement the CLI and atomic mode-0600 writer**

  Add `--force`, create a sibling temporary file with `tempfile.mkstemp`, apply `os.fchmod(fd, 0o600)`, write with `os.fdopen`, flush plus `os.fsync`, and finish with `os.replace`. On failure, unlink only the exact temporary file created by the process.

- [ ] **Step 12: Run all exporter tests and verify GREEN**

  Run:

  ```bash
  uv run pytest tests/unit/test_export_legacy_sqlite_catalog.py -q
  ```

  Expected: all tests pass.

- [ ] **Step 13: Commit Task 2**

  ```bash
  git add scripts/export_legacy_sqlite_catalog.py tests/unit/test_export_legacy_sqlite_catalog.py
  git commit -m "feat: export legacy sqlite user catalog"
  ```

---

### Task 3: Administration Console and Migration Documentation

**Files:**
- Create: `frontend/src/api/configuration.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/views/ProvidersView.vue`
- Modify: `frontend/tests/providers.spec.ts`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Create: `docs/catalog-import-export.md`

**Interfaces:**
- Consumes: Task 1 endpoints and Task 2 CLI.
- Produces: `exportCatalog(includeSecrets: boolean): Promise<Blob>` and `importCatalog(bundle: unknown): Promise<CatalogImportResult>`.

- [ ] **Step 1: Write failing frontend tests for secure export and file import**

  Add MSW handlers and assert:

  - Clicking `data-test="export-catalog"` first opens a warning confirmation that the backup may contain upstream API keys.
  - Confirming calls `/admin/configuration/export?include_secrets=true`, creates a download named `ai-gateway-catalog-v1.json`, and revokes the object URL.
  - Cancelling sends no request.
  - Selecting a JSON file through `data-test="import-catalog-input"` parses it, asks for merge confirmation, posts the exact object to `/admin/configuration/import`, refreshes provider data, and displays the literal created/updated counts.
  - Invalid local JSON displays an error and sends no import request.

- [ ] **Step 2: Run frontend tests and verify RED**

  Run:

  ```bash
  npm --prefix frontend test -- --run frontend/tests/providers.spec.ts
  ```

  Expected: FAIL because the controls and client do not exist.

- [ ] **Step 3: Implement typed API client and provider-page controls**

  Reuse the existing authenticated client for JSON import. For export, use the client response as a Blob without converting it to text. Keep the hidden file input reset after every attempt so selecting the same file twice works. Place import/export buttons beside the existing create-provider action and disable them while their operation is active.

- [ ] **Step 4: Run frontend tests and verify GREEN**

  Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Document the bundle and legacy migration command**

  Document exact exclusions, merge semantics, secret behavior, global-catalog ownership limitation, and commands:

  ```bash
  uv run python scripts/export_legacy_sqlite_catalog.py /path/to/ai-gateway.db \
    --user root \
    --include-unowned \
    --include-secrets \
    --output legacy-root-catalog.json
  ```

  Explain that `--include-unowned` is often needed for legacy administrator-created records because old versions did not consistently populate `userId`, and that secret-bearing files must be protected and removed after import.

- [ ] **Step 6: Run focused frontend and backend feature tests**

  Run:

  ```bash
  npm --prefix frontend test -- --run frontend/tests/providers.spec.ts
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_configuration.py tests/unit/test_export_legacy_sqlite_catalog.py -q
  ```

  Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

  ```bash
  git add frontend/src/api/configuration.ts frontend/src/api/types.ts frontend/src/views/ProvidersView.vue frontend/tests/providers.spec.ts README.md README.zh-CN.md docs/catalog-import-export.md
  git commit -m "feat: add catalog backup controls and migration guide"
  ```

---

### Task 4: Full Quality Gate

**Files:**
- Modify only files required to fix failures introduced by Tasks 1-3.

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: verified branch suitable for review.

- [ ] **Step 1: Run full backend tests**

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -q
  ```

  Expected: all tests pass.

- [ ] **Step 2: Run backend static checks**

  ```bash
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy
  ```

  Expected: all commands exit 0.

- [ ] **Step 3: Run frontend quality checks**

  ```bash
  npm --prefix frontend test -- --run
  npm --prefix frontend run lint
  npm --prefix frontend run build
  ```

  Expected: all commands exit 0.

- [ ] **Step 4: Review the requirement checklist and branch diff**

  Confirm the diff contains no database migration, user ownership column, password/key/balance/log export, plaintext secret logging, or destructive import behavior. Confirm `git status --short` contains only intended tracked files.

- [ ] **Step 5: Commit quality-gate fixes if needed**

  ```bash
  git add <only-files-changed-to-fix-quality-gate>
  git commit -m "fix: satisfy catalog import export quality gate"
  ```
