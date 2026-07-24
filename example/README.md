# Docker Compose quick-start example

This directory is a disposable local demonstration. It builds the project from the parent
directory, starts MySQL, applies all Alembic migrations, creates an administrator idempotently,
and then starts the gateway with the compiled administration console.

```bash
cd example
docker compose up
```

After the `gateway` service becomes healthy, open:

- Administration console: <http://127.0.0.1:8000/console/>
- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/health>

Default local administrator:

- Email: `admin@example.com`
- Password: `change-me-now`
- TOTP secret: `JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP`

Add that Base32 secret manually to an authenticator app (account `admin@example.com`, issuer
`ai-gateway`) and enter its current six-digit code when signing in. The fixed secret is public and
is suitable only for this local demonstration.

Override the account or host port without editing the Compose file:

```bash
GATEWAY_BOOTSTRAP_ADMIN_EMAIL='operator@example.com' \
GATEWAY_BOOTSTRAP_ADMIN_PASSWORD='a-better-local-password' \
GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ' \
GATEWAY_PORT=8080 \
docker compose up
```

Set `GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET=''` explicitly to create the administrator without TOTP.
If any one of the three bootstrap variables is explicitly set, the example switches to override
mode: email and password must both be non-empty, and omitted values do not fall back to the public
demo credentials. TOTP may be explicitly empty to disable it.
For a given email address, all three bootstrap values are used only when that administrator is
created for the first time. Later starts never replace its password or TOTP configuration. Using a
new email address creates a different administrator. To change the initial values for the default
administrator, set the variables before first startup, or run `docker compose down --volumes` to
clear the example data and then reinitialize it.

The fixed database credentials, JWT secret, encryption key, and administrator password are for
local evaluation only. Do not deploy this example to a shared or public environment. Use the
root [`compose.yaml`](../compose.yaml), [`.env.example`](../.env.example), and
[operations runbook](../docs/operations.md) for a real deployment.

Stop the example while retaining its MySQL volume:

```bash
docker compose down
```

Remove the example and all of its local database data:

```bash
docker compose down --volumes
```
