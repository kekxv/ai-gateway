# Docker Compose quick-start example

This directory is a disposable local demonstration. It builds the project from the parent
directory, starts MySQL, applies all Alembic migrations, and then starts the gateway with the
compiled console. It contains no built-in administrator email, password, or TOTP secret.

```bash
cd example
docker compose up
```

After the `gateway` service becomes healthy:

1. Open <http://127.0.0.1:8000/console/register>.
2. Register the first account. The first committed registration becomes the administrator.
3. Later registrations become regular users and can manage only their own password and TOTP
   settings.
4. Return to <http://127.0.0.1:8000/console/login> for later sign-ins.

Other endpoints:

- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/health>

Override the host port without editing the Compose file:

```bash
GATEWAY_PORT=8080 docker compose up
```

The fixed database credentials, JWT secret, and encryption key are for local evaluation only.
Do not deploy this example to a shared or public environment. Use the root
[`compose.yaml`](../compose.yaml), [`.env.example`](../.env.example), and
[operations runbook](../docs/operations.md) for a real deployment. The root deployment retains
an optional non-interactive administrator bootstrap for automated environments.

Stop the example while retaining its MySQL volume:

```bash
docker compose down
```

Remove the example and all of its local database data:

```bash
docker compose down --volumes
```
