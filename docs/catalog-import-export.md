# Catalog backup, restore, and legacy SQLite migration

Administrators can export and merge the global provider/model catalog from the **Providers** page
in the administration console. The portable JSON bundle has the fixed identifier
`ai-gateway.catalog` and `version` `1`.

## What a bundle contains

The bundle contains provider names and settings, provider protocols, canonical models, aliases,
model prices and multipliers, and routes. References use stable names and protocol/base-URL pairs,
not database IDs.

It deliberately excludes database IDs; users and their passwords or TOTP configuration; API keys
and their scopes; balances and ledger entries; request and audit logs; sessions; conversations;
skills; tools; source channels; and route runtime/health state. It is a catalog backup, not a full
database backup. Legacy channels are used only to select the provider/model graph and are never
emitted in the bundle.

## Exporting and importing in the console

Use **Export backup** on the Providers page. The console always asks for confirmation before
requesting a secret-bearing export, then downloads `ai-gateway-catalog-v1.json`. The API supports
redacted exports by default (`GET /admin/configuration/export`); secrets are included only with
`?include_secrets=true`.

The import picker parses JSON locally only to validate its syntax before it asks for confirmation.
After confirmation it sends the original JSON text unchanged as `application/json` to
`POST /admin/configuration/import`, preserving all supported decimal price precision, and refreshes
the provider list.

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

Use the [legacy SQLite exporter](../scripts/export_legacy_sqlite_catalog.py) to move one user's
channel/provider/model graph from the legacy Go project
[`kekxv/ai-gateway`](https://github.com/kekxv/ai-gateway) into the current gateway. The migration
deliberately uses a portable JSON bundle between the two applications instead of writing either
database directly:

```text
legacy Go gateway SQLite (read-only) -> ai-gateway.catalog JSON -> current gateway import
```

This migrates catalog configuration only. It does not migrate users, API keys, balances, request
history, sessions, or other runtime data.

### 1. Take a stable copy of the old database

Stop writes to the old gateway or use a filesystem/database snapshot, then copy its SQLite file to
a protected working location. Keep this untouched copy as the original rollback source. The
exporter opens SQLite with `mode=ro` and never modifies it, but a stable copy prevents an export
from observing an application write in progress.

If the legacy user ID is unknown, list the users with the SQLite CLI:

```bash
sqlite3 /path/to/ai-gateway.db 'SELECT id, email FROM "User" ORDER BY id;'
```

The `--user` option accepts either the numeric user ID or the exact legacy email value.

### 2. Export the selected user's catalog

Run the exporter from the root of this repository:

```bash
uv run python scripts/export_legacy_sqlite_catalog.py /path/to/ai-gateway.db \
  --user admin@example.com \
  --include-unowned \
  --include-secrets \
  --output legacy-user-catalog.json
```

Options:

- `--include-unowned` also includes providers, models, channels, and API-key channel associations
  whose legacy `userId` is `NULL`. It is commonly needed because older releases did not
  consistently assign administrator-created records to a user.
- `--include-secrets` includes upstream credentials. Omit it for a review-only or redacted backup.
- `--force` permits replacing an existing output path. Without it, the exporter refuses to
  overwrite a file.
- `--output` is required. The file is written atomically with mode `0600`.

The exporter follows the selected user's owned channels plus the associated provider/model graph,
deduplicates aliases, and validates conflicts before writing anything. Legacy `anthropic`
protocols become `claude`; legacy token prices are converted to the current per-million-token
units; missing cache prices default to zero; and missing provider/model multipliers default to
`1.00`.

Review the generated JSON before importing. In particular, verify provider names, base URLs,
protocols, canonical model names, aliases, route weights, prices, and whether credentials are
present as intended. Do not commit a secret-bearing bundle to source control.

### 3. Back up the destination catalog

Before importing, export the current destination catalog from **Providers -> Export backup**. Use
a secret-bearing export only if an encrypted rollback copy of existing upstream credentials is
required. Because catalog import is merge-only, re-importing this backup can restore matching
values but will not delete resources newly created by the migration; use a normal MySQL backup when
an exact database rollback is required.

### 4. Import into the current gateway

The recommended method is **Providers -> Import backup** in the administration console. Select the
generated JSON file, review the confirmation dialog, and import it.

The same operation can be performed through the administration API with an administrator access
token:

```bash
curl --fail-with-body \
  -X POST "$GATEWAY_URL/admin/configuration/import" \
  -H "authorization: Bearer $ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  --data-binary @legacy-user-catalog.json
```

Import runs in one transaction. Existing resources with the same stable identity are updated,
missing resources are created, and resources omitted from the bundle are not deleted. Any
validation, alias, provider, protocol, or route conflict rejects the entire import.

### 5. Verify and retire the migration file

After import:

1. Confirm the expected providers, protocols, models, aliases, prices, multipliers, and routes in
   the console.
2. Send a request using at least one migrated alias and confirm the selected route rewrites it to
   the configured upstream model.
3. Review the request log and billing result for the smoke-test request.
4. Securely remove the JSON file if it contains credentials, or move it to approved encrypted
   backup storage.

### Ownership limitation

The current gateway catalog is global, not user-owned. The legacy `--user` selection only chooses
source records for the export; after import, providers and models are shared by every gateway user.
Do not use this migration as a way to isolate one user's catalog in the current gateway.
