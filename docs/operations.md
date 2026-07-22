# Operations runbook

## Production baseline

- Use MySQL 8.4 with durable storage, automated backups, and TLS/private networking appropriate to
  your environment.
- Set `GATEWAY_ENVIRONMENT=production`, a unique high-entropy `GATEWAY_JWT_SECRET`, and a Fernet
  `GATEWAY_ENCRYPTION_KEY`. Production startup rejects the example secret values.
- Run one gateway process per container. Put multiple containers behind a load balancer that
  removes a replica when `/health` is not `200`.
- Run `alembic upgrade head` as a separate release job before starting the matching image.
- Keep `.env`, provider credentials, API keys, JWT secrets, database passwords, and proxy URLs in a
  secret manager; never bake them into the image.
- `compose.yaml` is the canonical Compose definition. It interpolates `MYSQL_DATABASE`,
  `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD`; its checked-in fallbacks are only for
  disposable local development. Use URL-safe characters in `MYSQL_PASSWORD` because the same
  value is embedded in `GATEWAY_DATABASE_URL` for the gateway container.
- Set strong MySQL passwords before the first startup that initializes a durable volume. Changing
  `MYSQL_PASSWORD` or `MYSQL_ROOT_PASSWORD` later does not alter users stored in that volume.
- The Compose MySQL port is bound only to `127.0.0.1:3306`. Use private networking rather than
  widening that host binding for remote access.

## MySQL password rotation for an existing volume

Do not edit the deployment environment first: the running database still knows only the old
credentials. Take and verify a backup, then connect with the old root password while disabling
client history:

```bash
docker compose exec mysql sh -c 'MYSQL_HISTFILE=/dev/null exec mysql -uroot -p'
```

At the MySQL prompt, enter the old root password interactively and replace both placeholders with
new URL-safe secrets from the secret manager:

```sql
ALTER USER
  'gateway'@'%' IDENTIFIED BY 'NEW_GATEWAY_PASSWORD',
  'root'@'localhost' IDENTIFIED BY 'NEW_ROOT_PASSWORD';
```

Only after that statement succeeds, update `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`,
`GATEWAY_DATABASE_URL`, and `GATEWAY_TEST_DATABASE_URL` where applicable. Recreate the MySQL
container so its authenticated healthcheck uses the new application password, then roll gateway
replicas onto the matching database URL. Verify `docker compose ps`, `/health`, an Alembic current
check, administrator login, and one low-cost provider request before retiring the old deployment
configuration. If `ALTER USER` fails, leave the environment unchanged and restore/test access with
the old credentials before retrying.

## Gateway API-key rotation

The rotate endpoint disables the old key and creates a same-scope replacement atomically. The raw
replacement is returned once:

```bash
curl --fail -X POST "$GATEWAY_URL/admin/api-keys/$API_KEY_ID/rotate" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Use this for an immediate cutover. Capture the new key, update the consumer, and verify a request;
the old key is already invalid. For a zero-downtime multi-consumer rollout, create a second key
with the same scope, distribute and verify it, then disable the original with:

```bash
curl --fail -X PATCH "$GATEWAY_URL/admin/api-keys/$OLD_API_KEY_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"is_active":false}'
```

Never write raw keys to tickets or logs. The database contains only a digest and prefix.

## Provider credential rotation

Patch only the credential after the provider has issued a replacement:

```bash
curl --fail -X PATCH "$GATEWAY_URL/admin/providers/$PROVIDER_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"credential":{"api_key":"REDACTED-NEW-PROVIDER-KEY"}}'
```

The response exposes only `has_credential`. Send a low-cost request, confirm the route remains
closed/healthy, then revoke the old credential at the provider. If the provider cannot overlap
credentials, schedule a short maintenance window.

## JWT signing-secret rotation

The current release accepts one JWT signing secret. Changing `GATEWAY_JWT_SECRET` invalidates all
access and refresh tokens, so rotate it with a coordinated restart of every replica and require
users to log in again. Do not run old/new JWT secrets concurrently behind one load balancer.

## Credential encryption-key rotation

`GATEWAY_ENCRYPTION_KEY` encrypts provider credentials, provider extra headers, active TOTP
secrets, and pending TOTP secrets. The current release accepts one Fernet key, so rotation must be
a coordinated maintenance operation, not a normal rolling restart.

1. Disable admin writes and stop every gateway replica.
2. Take and verify a MySQL backup.
3. Place old/new Fernet keys in a restricted one-shot environment. Do not put them in shell
   history.
4. Re-encrypt every encrypted column in one transaction using the offline command below.
5. Update the deployment secret to the new key, start all replicas, verify login/TOTP and one
   provider request, then securely destroy the old key after the rollback window.

```bash
export OLD_GATEWAY_ENCRYPTION_KEY='from-secret-manager'
export NEW_GATEWAY_ENCRYPTION_KEY='from-secret-manager'
export GATEWAY_DATABASE_URL='mysql+asyncmy://gateway:URL_SAFE_PASSWORD@mysql:3306/gateway'

uv run python - <<'PY'
import asyncio
import os

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ai_gateway.db.models import Provider, ProviderProtocol, User


async def main() -> None:
    old = Fernet(os.environ["OLD_GATEWAY_ENCRYPTION_KEY"].encode())
    new = Fernet(os.environ["NEW_GATEWAY_ENCRYPTION_KEY"].encode())
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        for provider in await session.scalars(select(Provider).with_for_update()):
            provider.credential_encrypted = new.encrypt(old.decrypt(provider.credential_encrypted))
        for protocol in await session.scalars(select(ProviderProtocol).with_for_update()):
            if protocol.extra_headers_encrypted is not None:
                protocol.extra_headers_encrypted = new.encrypt(
                    old.decrypt(protocol.extra_headers_encrypted)
                )
        for user in await session.scalars(select(User).with_for_update()):
            if user.totp_secret_encrypted is not None:
                user.totp_secret_encrypted = new.encrypt(old.decrypt(user.totp_secret_encrypted))
            if user.pending_totp_secret_encrypted is not None:
                user.pending_totp_secret_encrypted = new.encrypt(
                    old.decrypt(user.pending_totp_secret_encrypted)
                )
    await engine.dispose()


asyncio.run(main())
PY

unset OLD_GATEWAY_ENCRYPTION_KEY NEW_GATEWAY_ENCRYPTION_KEY
```

If verification fails, stop replicas, restore the pre-rotation backup, restore the old key, and
investigate offline. Never commit a partially re-encrypted database.

## Backup

Create a transactionally consistent logical backup from the Compose MySQL service:

```bash
mkdir -p backups
docker compose exec -T mysql sh -c \
  'exec mysqldump --single-transaction --routines --triggers -uroot \
   -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  | gzip -9 > "backups/gateway-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
gzip -t backups/gateway-*.sql.gz
```

Store backups encrypted, off-host, with retention and restore tests. A backup is only valid if it
contains `alembic_version`, catalog/auth data, `accounts`, the complete `ledger_entries` history,
and `request_logs` required by policy.

## Restore

Restores are destructive. Restore into a new database/volume first whenever possible.

```bash
docker compose stop gateway
gunzip -c backups/gateway-YYYYMMDDTHHMMSSZ.sql.gz \
  | docker compose exec -T mysql sh -c \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
docker compose run --rm gateway alembic current
docker compose run --rm gateway alembic upgrade head
docker compose up -d gateway
curl --fail http://127.0.0.1:8000/health
```

Verify administrator login, balances/ledger totals, provider/model counts, a canary provider
request, and recent audit records before reopening traffic.

## Audit-log retention and deletion by date

Choose a UTC retention date from legal/security policy. Back up first, record the approved cutoff,
then delete in bounded batches to avoid a long transaction:

```bash
# Replace this literal UTC cutoff only after approval.
docker compose exec -T mysql sh -c \
  'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e \
  "SELECT COUNT(*) AS rows_to_delete FROM request_logs \
   WHERE created_at < '\''2026-04-01 00:00:00'\'';"'

while :; do
  deleted="$(docker compose exec -T mysql sh -c \
    'mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e \
    "DELETE FROM request_logs WHERE created_at < '\''2026-04-01 00:00:00'\'' \
     LIMIT 10000; SELECT ROW_COUNT();"')"
  [ "$deleted" = 0 ] && break
  sleep 1
done
```

The GZIP request/response blobs are columns on `request_logs`, so deleting the row deletes its
details. Do not delete `ledger_entries` as log retention; the ledger is the financial source of
truth and needs a separate approved retention policy.

## Diagnose a failed/open route

1. Get route state and last error:

   ```bash
   curl --fail "$GATEWAY_URL/admin/model-routes/$ROUTE_ID" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

2. Query recent request logs for the provider/status and inspect a detail record:

   ```bash
   curl --fail \
     "$GATEWAY_URL/admin/request-logs?provider_id=$PROVIDER_ID&status=failed&page_size=50" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   curl --fail "$GATEWAY_URL/admin/request-logs/$REQUEST_ID" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

3. Interpret `last_error_code`: `http_429`/`http_5xx` are provider capacity/service failures;
   `connect_timeout`/`read_timeout` indicate latency; `dns_error`/`tls_error` indicate network or
   certificate configuration; `websocket_*` indicates handshake/network/penalizing close failure.
4. Confirm provider and protocol are enabled, base/WebSocket URL and upstream model are correct,
   API-key scope includes the route, DNS works from the gateway network, and proxy/NO_PROXY rules
   produce the intended path.
5. Fix the dependency and wait until `disabled_until`. One replica will atomically claim the
   half-open probe. A success resets the route to closed; do not repeatedly toggle replicas.

For emergency recovery after verifying the provider outside the gateway, an operator may reset
one route directly. This bypasses the circuit-breaker cooldown and must be audited:

```sql
UPDATE model_routes
SET runtime_state='closed', consecutive_failures=0, disabled_until=NULL,
    last_error_code=NULL, last_error_at=NULL
WHERE id = :route_id;
```

## HTTP/HTTPS proxy and NO_PROXY/CIDR

HTTP provider traffic uses `GATEWAY_HTTP_PROXY`. HTTPS uses `GATEWAY_HTTPS_PROXY`, falling back to
the HTTP proxy when the HTTPS value is absent. WebSocket `ws`/`wss` follows the same choice.

```dotenv
GATEWAY_HTTP_PROXY=http://proxy.internal:3128
GATEWAY_HTTPS_PROXY=http://proxy.internal:3128
GATEWAY_NO_PROXY=127.0.0.1,localhost,mysql,.svc.cluster.local,10.0.0.0/8,192.168.0.0/16,2001:db8::/32,provider.internal:8443
```

`NO_PROXY` accepts exact hosts, `.suffix` host rules, optional ports, IPv4/IPv6 addresses,
IPv4/IPv6 CIDRs, and `*`. Hostnames are resolved when CIDR matching is needed. Put proxy
credentials in the secret manager; a credential-bearing proxy URL must never be printed.

## Safe rolling deployment

1. Review migrations and compatibility. Current binaries require the exact migration head they
   were built for. A schema-changing release must use an expand/contract sequence compatible with
   both versions or a maintenance deployment; do not mix binaries that require different heads.
2. Back up MySQL and build the immutable image by digest.
3. Run `alembic upgrade head` once with the new image. Confirm `alembic current` reports the
   expected head.
4. Start one canary replica with the new image. Wait for `/health`, login, model listing, one
   non-stream request, one stream request, and a balance/audit check.
5. Drain one old replica at a time at the load balancer. Allow HTTP requests to finish and close or
   deliberately drain long-lived WebSockets before stopping the process.
6. Start its replacement, wait for health, and continue. Monitor 5xx/429, route-open count,
   uncollected billing metadata, request-log failures, and database saturation.
7. Keep the previous image and pre-migration backup through the rollback window. Application-only
   rollback is safe only while schema compatibility is preserved.

Because model-sync election, route half-open claims, and account mutations are MySQL-coordinated,
replicas may overlap during a normal same-head rolling deployment.
