# Catalog backup, restore, and legacy SQLite migration

Administrators can export and merge the global provider/model catalog from the **Providers** page
in the administration console. The portable JSON bundle has the fixed identifier
`ai-gateway.catalog` and `version` `1`.

## What a bundle contains

The bundle contains provider names and settings, provider protocols, canonical models, aliases,
model prices and multipliers, and routes. References use stable names and protocol/base-URL pairs,
not database IDs.

It deliberately excludes database IDs, users, API keys and their scopes, balances, ledger entries,
request and audit logs, sessions, and route runtime/health state. It is a catalog backup, not a
full database backup.

## Exporting and importing in the console

Use **Export backup** on the Providers page. The console always asks for confirmation before
requesting a secret-bearing export, then downloads `ai-gateway-catalog-v1.json`. The API supports
redacted exports by default (`GET /admin/configuration/export`); secrets are included only with
`?include_secrets=true`.

The import picker parses JSON locally before it asks for confirmation. After confirmation it sends
the unmodified object to `POST /admin/configuration/import` and refreshes the provider list.

Import is transactional and merge-only:

- Providers match by name, models by canonical name, provider protocols by provider name + protocol
  + base URL, and routes by model + provider protocol.
- Matching resources are updated and missing matching resources are created. Existing providers,
  protocols, models, aliases, and routes omitted from the bundle are never deleted.
- A `null` provider credential or protocol `extra_headers` does not overwrite an existing stored
  secret. For a newly created resource, a `null` secret means no secret is configured.
- Validation or a name/alias/route conflict rejects the whole bundle; no partial merge is retained.

Treat any file produced with `include_secrets=true` as a credential. Store it only in approved
encrypted storage, do not commit or attach it to tickets, restrict access while importing, and
securely remove it after a successful import.

## Migrating a legacy SQLite installation

The legacy exporter reads a SQLite file without modifying it and emits the same version-1 bundle.
Choose the legacy user by ID or email:

```bash
uv run python scripts/export_legacy_sqlite_catalog.py /path/to/ai-gateway.db \
  --user root \
  --include-unowned \
  --include-secrets \
  --output legacy-root-catalog.json
```

Use `--include-secrets` only when the destination needs the old upstream credentials; otherwise
they are redacted. `--include-unowned` is often necessary for legacy administrator-created records
because old releases did not consistently populate `userId`. It includes unowned legacy catalog
records and channels in the selected export graph; review the generated JSON before importing.

The current gateway catalog is global, not user-owned. The legacy `--user` selection only chooses
source records for the export; after import, providers and models are shared by every gateway user.
Do not use this migration as a way to isolate one user's catalog in the current gateway.
