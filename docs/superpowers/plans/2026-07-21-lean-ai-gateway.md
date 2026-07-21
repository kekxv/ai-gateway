# Lean AI Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个精简但可生产部署的多提供商 AI 网关，支持 OpenAI、Claude、Gemini 协议接入与转换、加权路由、认证授权、余额计费、压缩审计日志、代理和 WebSocket。

**Architecture:** 采用模块化单体：FastAPI 暴露管理 API 和三套兼容 API，协议适配器把跨协议 HTTP 请求转换为统一领域对象，同协议请求只重写模型、鉴权和目标地址后透传。MySQL 保存配置、路由状态、余额账本和 GZIP 日志；网关进程内完成加权选择、失败熔断、流式桥接和定时模型同步，第一版不引入 Redis、消息队列或独立 worker。

**Tech Stack:** Python 3.12、uv、FastAPI、Pydantic 2、SQLAlchemy 2 async、Alembic、MySQL 8.4、asyncmy、httpx、PyJWT、argon2-cffi、pyotp、cryptography、pytest、pytest-asyncio、respx、Docker Compose。

## Global Constraints

- 数据库固定使用 MySQL 8.4；金额和单价全部使用 `DECIMAL`/`Decimal`，禁止使用浮点数。
- Python 固定为 3.12，依赖和命令统一通过 `uv` 管理。
- 提供商凭据使用应用主密钥加密后入库；API Key 只保存前缀和 SHA-256 哈希，不保存明文。
- TOTP 初次注册和重新注册使用独立的待确认加密密钥；新密钥确认成功前保留当前有效密钥和启用状态，已启用 TOTP 的用户开始重新注册前必须验证当前 TOTP。
- OpenAI、Claude、Gemini 的 HTTP 非流式和流式聊天接口支持任意入口协议到任意上游协议的转换；同协议保留原始 JSON 和 SSE 事件，仅重写必要字段。
- 模型别名只用于入口解析和模型列表展示，绝不能发送给上游；完成选路后，HTTP、SSE 和 WebSocket 请求中的模型名必须统一改写为 `ModelRoute.upstream_model`，即该渠道实际接受的原始模型名。
- WebSocket 支持 OpenAI Realtime 和 Gemini Live 的透明中继；Claude 当前没有对应的官方 WebSocket 协议，路由到 Claude 时返回明确的 `unsupported_transport` 错误。
- 自动禁用只改变路由运行状态，不改变管理员配置的 `enabled`；冷却到期后允许半开探测。
- 请求详情默认 GZIP 后存入 MySQL `LONGBLOB`，敏感请求头、认证字段和提供商密钥必须在压缩前脱敏。
- 所有余额扣费、账本写入和请求结算必须在同一个数据库事务内完成，并用幂等键阻止重复扣费。
- 测试不得访问真实 AI 提供商；协议测试使用 `respx` 或本地 ASGI/WebSocket 假服务。
- 第一版为单进程可横向扩展的模块化单体，不加入 Redis、Celery、Kafka、前端 UI、充值支付、组织/租户、优惠券或 RPM/TPM 限流。

---

## File and Module Map

```text
.
├── pyproject.toml                     # uv 项目、运行与测试依赖、pytest/ruff/mypy 配置
├── docker-compose.yml                 # 本地 MySQL 8.4
├── .env.example                       # 可运行的配置样例
├── alembic.ini
├── migrations/                        # 数据库迁移
├── src/ai_gateway/
│   ├── main.py                        # FastAPI 应用工厂、生命周期、路由注册
│   ├── core/
│   │   ├── config.py                  # 环境配置
│   │   ├── errors.py                  # 统一异常与错误响应
│   │   ├── security.py                # 密码、JWT、TOTP、密钥加解密
│   │   └── enums.py                   # 协议、路由状态、作用域等枚举
│   ├── db/
│   │   ├── base.py                    # DeclarativeBase、时间/ID mixin
│   │   ├── session.py                 # async engine/session/事务依赖
│   │   └── models/                    # identity、catalog、billing、audit ORM 模型
│   ├── auth/                          # 登录、2FA、JWT/API Key 解析和权限判断
│   ├── admin/                         # 用户、Key、提供商、模型、路由、日志管理 API
│   ├── catalog/                       # 模型解析、别名、模型发现和同步
│   ├── routing/                       # 候选过滤、加权随机、失败熔断
│   ├── protocols/                     # canonical 类型及 OpenAI/Claude/Gemini 适配器
│   ├── transport/                     # HTTP/SSE/WebSocket 客户端和代理选择
│   ├── billing/                       # Token 用量提取、估算、定价、余额账本
│   ├── audit/                         # 脱敏、GZIP、请求日志生命周期
│   └── gateway/                       # 三协议入口、编排服务、错误映射
└── tests/
    ├── unit/                          # 纯函数与服务单测
    ├── integration/                   # MySQL、事务、API 集成测试
    └── contract/                      # 三协议、SSE、WebSocket 契约测试
```

---

### Task 1: Bootstrap the runnable service and MySQL test foundation

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `src/ai_gateway/main.py`
- Create: `src/ai_gateway/core/config.py`
- Create: `src/ai_gateway/core/errors.py`
- Create: `src/ai_gateway/db/base.py`
- Create: `src/ai_gateway/db/session.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_health.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI`, `get_settings() -> Settings`, `get_session() -> AsyncIterator[AsyncSession]`。

- [ ] **Step 1: Write the failing health test**

```python
from fastapi.testclient import TestClient
from ai_gateway.main import create_app


def test_health_returns_ready() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test and confirm the package is missing**

Run: `uv run pytest tests/unit/test_health.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_gateway'`.

- [ ] **Step 3: Add the project dependencies and configuration**

Set `requires-python = ">=3.12,<3.13"` and add these runtime packages: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncmy`, `alembic`, `httpx[socks]`, `websockets`, `pyjwt[crypto]`, `argon2-cffi`, `pyotp`, `cryptography`, `orjson`, `tiktoken`. Add test packages: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `freezegun`, `ruff`, `mypy`.

Create settings with these exact fields:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_", extra="ignore")
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway"
    jwt_secret: SecretStr
    jwt_issuer: str = "ai-gateway"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 30
    encryption_key: SecretStr
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str = "127.0.0.1,localhost"
    route_failure_threshold: int = 3
    route_cooldown_seconds: int = 60
    model_sync_interval_seconds: int = 3600
    audit_body_limit_bytes: int = 1_048_576
```

- [ ] **Step 4: Implement the app factory and health route**

```python
def create_app() -> FastAPI:
    app = FastAPI(title="Lean AI Gateway", version="0.1.0")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Add MySQL Compose and test fixtures**

Use image `mysql:8.4`, database/user/password `gateway`, healthcheck `mysqladmin ping -h localhost -ugateway -pgateway`, port `3306`, and a named volume. In `tests/conftest.py`, require `GATEWAY_TEST_DATABASE_URL`; create/drop tables once per test session and roll back one transaction per test.

- [ ] **Step 6: Verify bootstrap quality**

Run: `uv lock && uv run pytest tests/unit/test_health.py -v && uv run ruff check src tests && uv run mypy src`

Expected: health test PASS; Ruff and mypy exit 0.

- [ ] **Step 7: Initialize version control when the directory is not yet a repository**

Run: `git status`

Expected in the current empty workspace: FAIL with `not a git repository`. Run `git init` once, then verify `git status --short --branch` reports an empty branch.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .env.example docker-compose.yml src tests
git commit -m "chore: bootstrap gateway service"
```

---

### Task 2: Create the identity, provider, model, billing, and audit schema

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_initial_schema.py`
- Create: `src/ai_gateway/core/enums.py`
- Create: `src/ai_gateway/db/models/identity.py`
- Create: `src/ai_gateway/db/models/catalog.py`
- Create: `src/ai_gateway/db/models/billing.py`
- Create: `src/ai_gateway/db/models/audit.py`
- Create: `src/ai_gateway/db/models/__init__.py`
- Test: `tests/integration/test_schema.py`

**Interfaces:**
- Produces: ORM classes `User`, `ApiKey`, `ApiKeyProvider`, `ApiKeyModel`, `Provider`, `ProviderProtocol`, `Model`, `ModelAlias`, `ModelRoute`, `Account`, `LedgerEntry`, `RequestLog`。
- Produces enums: `Protocol`, `ApiKeyScope`, `RouteRuntimeState`, `LedgerKind`, `RequestStatus`, `UsageSource`。

- [ ] **Step 1: Write schema constraint tests**

```python
async def test_model_route_is_unique_per_model_provider_protocol(session):
    route = ModelRoute(model_id=1, provider_id=1, provider_protocol_id=1,
                       upstream_model="gpt-4.1-mini", weight=100)
    session.add_all([route, copy.copy(route)])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_money_columns_are_decimal(session):
    user = User(email="a@example.com", password_hash="x", role="user")
    user.account = Account(balance=Decimal("10.00000000"), total_spent=Decimal("0"))
    session.add(user)
    await session.commit()
    assert isinstance(user.account.balance, Decimal)
```

- [ ] **Step 2: Run the schema tests and confirm imports fail**

Run: `uv run pytest tests/integration/test_schema.py -v`

Expected: FAIL because the ORM classes do not exist.

- [ ] **Step 3: Define exact table fields and indexes**

Implement the following schema:

```text
users: id, email UNIQUE, password_hash, role(admin|user), is_active,
       totp_secret_encrypted NULL, totp_enabled, created_at, updated_at
accounts: id, user_id UNIQUE FK, balance DECIMAL(20,8), total_spent DECIMAL(20,8), version
api_keys: id, user_id FK, name, key_prefix, key_hash UNIQUE, scope,
          is_active, expires_at NULL, last_used_at NULL, created_at
api_key_providers: api_key_id FK, provider_id FK, PRIMARY KEY(api_key_id, provider_id)
api_key_models: api_key_id FK, model_id FK, PRIMARY KEY(api_key_id, model_id)
providers: id, name UNIQUE, credential_encrypted LONGBLOB, enabled,
           auto_load_models, model_sync_interval_seconds, last_model_sync_at NULL
provider_protocols: id, provider_id FK, protocol, base_url, websocket_url NULL,
                    extra_headers_encrypted LONGBLOB NULL, enabled,
                    UNIQUE(provider_id, protocol, base_url)
models: id, canonical_name UNIQUE, display_name, enabled,
        input_price_per_million DECIMAL(20,8), output_price_per_million DECIMAL(20,8),
        routing_strategy(weighted_random), created_at, updated_at
model_aliases: id, model_id FK, alias UNIQUE, enabled
model_routes: id, model_id FK, provider_id FK, provider_protocol_id FK,
              upstream_model, weight, enabled, runtime_state,
              consecutive_failures, disabled_until NULL, last_error_code NULL,
              last_error_at NULL, UNIQUE(model_id, provider_id, provider_protocol_id)
ledger_entries: id, account_id FK, request_id CHAR(36) NULL,
                idempotency_key UNIQUE, kind, amount DECIMAL(20,8),
                balance_after DECIMAL(20,8), metadata JSON, created_at
request_logs: id CHAR(36), user_id FK, api_key_id FK NULL, model_id FK NULL,
              provider_id FK NULL, model_route_id FK NULL, inbound_protocol,
              outbound_protocol NULL, transport, stream, status, http_status NULL,
              prompt_tokens, completion_tokens, usage_source NULL,
              cost DECIMAL(20,8), latency_ms NULL, first_token_ms NULL,
              error_code NULL, request_detail_gzip LONGBLOB NULL,
              response_detail_gzip LONGBLOB NULL, created_at, completed_at NULL
```

Add indexes on `(model_id, enabled, runtime_state)`, `(user_id, created_at)`, `(api_key_id, created_at)`, `(provider_id, created_at)`, and `(status, created_at)`.

- [ ] **Step 4: Generate and inspect the migration**

Run: `uv run alembic revision --autogenerate -m "initial schema"`

Expected: one migration containing all 12 tables, foreign keys, unique constraints, and indexes above. Rename it to `0001_initial_schema.py` and set `revision = "0001"`.

- [ ] **Step 5: Apply the migration and pass schema tests**

Run: `uv run alembic upgrade head && uv run pytest tests/integration/test_schema.py -v`

Expected: migration succeeds and tests PASS.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations src/ai_gateway/db src/ai_gateway/core/enums.py tests/integration/test_schema.py
git commit -m "feat: add gateway database schema"
```

---

### Task 3: Implement password login, JWT sessions, and TOTP enrollment

**Files:**
- Create: `src/ai_gateway/core/security.py`
- Create: `src/ai_gateway/auth/schemas.py`
- Create: `src/ai_gateway/auth/service.py`
- Create: `src/ai_gateway/auth/dependencies.py`
- Create: `src/ai_gateway/auth/router.py`
- Create: `migrations/versions/0002_pending_totp_secret.py`
- Modify: `src/ai_gateway/db/models/identity.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/unit/auth/test_security.py`
- Test: `tests/integration/auth/test_login_totp.py`

**Interfaces:**
- Produces: `hash_password`, `verify_password`, `issue_access_token`, `issue_refresh_token`, `decode_token`, `encrypt_secret`, `decrypt_secret`。
- Produces endpoints: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/totp/setup`, `POST /auth/totp/confirm`。
- Produces dependencies: `current_user()` and `admin_user()`。

- [ ] **Step 1: Write failing security tests**

```python
def test_password_hash_is_not_plaintext():
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)


def test_access_token_has_subject_type_and_expiry(settings):
    token = issue_access_token(user_id=7, settings=settings)
    claims = decode_token(token, expected_type="access", settings=settings)
    assert claims["sub"] == "7"
    assert claims["type"] == "access"
    assert claims["iss"] == "ai-gateway"
```

- [ ] **Step 2: Run tests and confirm functions are missing**

Run: `uv run pytest tests/unit/auth/test_security.py -v`

Expected: FAIL on missing imports.

- [ ] **Step 3: Implement security primitives**

Use Argon2id for passwords, HS256 for JWT, Fernet for encrypted secrets, and `pyotp.TOTP(secret).verify(code, valid_window=1)` for TOTP. Access tokens contain `sub`, `type=access`, `iss`, `iat`, `exp`, and `jti`; refresh tokens contain the same fields with `type=refresh`.

- [ ] **Step 4: Write failing login and TOTP API tests**

Test these exact outcomes:

```text
valid password, TOTP disabled       -> 200 access_token + refresh_token
valid password, TOTP enabled/no code -> 401 code=totp_required
valid password, valid TOTP          -> 200 tokens
wrong password                      -> 401 code=invalid_credentials
disabled user                       -> 403 code=user_disabled
refresh token on /auth/refresh      -> 200 new access token
access token on /auth/refresh       -> 401 code=invalid_token_type
```

- [ ] **Step 5: Implement login and two-step TOTP enrollment**

Add nullable `users.pending_totp_secret_encrypted LONGBLOB` in migration `0002`. `/auth/totp/setup` creates a random secret and stores it only in the encrypted pending field; it does not overwrite `totp_secret_encrypted` or change `totp_enabled`. When TOTP is already enabled, setup requires and verifies `current_totp_code` against the active secret before issuing a new pending secret. `/auth/totp/confirm` verifies the new code against the pending secret, then atomically moves pending ciphertext to `totp_secret_encrypted`, clears the pending field, and sets `totp_enabled=true`. Never return the secret after confirmation.

- [ ] **Step 6: Run auth tests**

Run: `uv run pytest tests/unit/auth tests/integration/auth -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_gateway/core/security.py src/ai_gateway/auth src/ai_gateway/main.py tests/unit/auth tests/integration/auth
git commit -m "feat: add jwt and totp authentication"
```

---

### Task 4: Add user administration and scoped API Key management

**Files:**
- Create: `src/ai_gateway/admin/users.py`
- Create: `src/ai_gateway/admin/api_keys.py`
- Create: `src/ai_gateway/auth/api_key.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/integration/admin/test_users.py`
- Test: `tests/integration/admin/test_api_keys.py`
- Test: `tests/unit/auth/test_api_key_scope.py`

**Interfaces:**
- Produces endpoints: CRUD `/admin/users`, CRUD `/admin/api-keys`。
- Produces: `ApiKeyPrincipal`, `authenticate_api_key(raw_key)`, `authorize_scope(principal, model_id, provider_id)`。

- [ ] **Step 1: Write failing API Key lifecycle tests**

```python
async def test_created_api_key_is_returned_once(admin_client):
    response = await admin_client.post("/admin/api-keys", json={
        "user_id": 2, "name": "production", "scope": "models", "model_ids": [11]
    })
    assert response.status_code == 201
    raw_key = response.json()["key"]
    assert raw_key.startswith("sk-gw-")
    detail = await admin_client.get(f"/admin/api-keys/{response.json()['id']}")
    assert "key" not in detail.json()
```

- [ ] **Step 2: Define scope semantics with table-driven unit tests**

```text
scope=all:                      every enabled model and provider is allowed
scope=providers:                provider must be in api_key_providers
scope=models:                   model must be in api_key_models
scope=providers_and_models:     both memberships must match
inactive/expired key:           authentication fails before routing
inactive user:                  authentication fails before routing
```

- [ ] **Step 3: Implement secure key creation and lookup**

Generate `sk-gw-` plus 32 URL-safe random bytes. Persist only the first 12 characters and `sha256(raw_key).digest()`. Compare digests with `hmac.compare_digest`; update `last_used_at` after successful authentication.

Accept the gateway key from all three native client conventions: OpenAI `Authorization: Bearer sk-gw-*`, Claude `x-api-key: sk-gw-*`, and Gemini `x-goog-api-key: sk-gw-*`. If more than one credential header is present and their values differ, reject the request with `ambiguous_credentials`.

- [ ] **Step 4: Implement admin authorization and CRUD**

Admin user creation accepts `email`, `password`, `role`, `initial_balance`; account creation is in the same transaction. Key update may change name, active state, expiry, scope and relation rows, but never rotates the secret. Add `POST /admin/api-keys/{id}/rotate` to atomically revoke the old key and create a replacement.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/auth/test_api_key_scope.py tests/integration/admin/test_users.py tests/integration/admin/test_api_keys.py -v`

Expected: all tests PASS, including non-admin responses with HTTP 403.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/admin src/ai_gateway/auth src/ai_gateway/main.py tests
git commit -m "feat: add users and scoped api keys"
```

---

### Task 5: Add provider, protocol, model, alias, and route administration

**Files:**
- Create: `src/ai_gateway/admin/providers.py`
- Create: `src/ai_gateway/admin/models.py`
- Create: `src/ai_gateway/catalog/repository.py`
- Create: `src/ai_gateway/catalog/schemas.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/integration/admin/test_catalog.py`
- Test: `tests/unit/catalog/test_resolution.py`

**Interfaces:**
- Produces CRUD endpoints under `/admin/providers`, `/admin/models`, `/admin/model-routes`。
- Produces: `ResolvedModel(model_id, requested_name, canonical_name)`, `resolve_model(name)`。

- [ ] **Step 1: Write failing model resolution tests**

```python
@pytest.mark.parametrize("requested", ["gpt-4.1-mini", "fast-chat"])
async def test_canonical_name_and_alias_resolve_to_same_model(catalog, requested):
    resolved = await catalog.resolve_model(requested)
    assert resolved.model_id == 41
    assert resolved.canonical_name == "gpt-4.1-mini"
    assert resolved.requested_name == requested
```

- [ ] **Step 2: Write failing provider validation tests**

Verify that a provider can contain multiple protocol rows, duplicate `(provider, protocol, base_url)` is rejected, a route's `provider_protocol_id` must belong to its `provider_id`, weight must be `1..10000`, and all prices must be non-negative decimals with at most 8 decimal places.

- [ ] **Step 3: Implement catalog CRUD and encrypted provider credentials**

Provider input accepts one credential object and a list of protocol configurations:

```json
{
  "name": "vendor-a",
  "credential": {"api_key": "secret"},
  "enabled": true,
  "auto_load_models": true,
  "protocols": [
    {"protocol": "openai", "base_url": "https://api.example.com/v1", "enabled": true},
    {"protocol": "claude", "base_url": "https://api.example.com", "enabled": true}
  ]
}
```

Encrypt credential and extra headers as canonical JSON bytes. Response models expose `has_credential: true` and never expose encrypted blobs or plaintext.

- [ ] **Step 4: Implement model, alias, and relation-table management**

Model create/update accepts canonical name, display name, input/output prices, enabled state, aliases, and routing strategy. Model-route create/update accepts model, provider, provider protocol, upstream model, weight and enabled state. Deleting a model or provider with ledger/log history returns HTTP 409; disabling is the supported archival action.

- [ ] **Step 5: Run catalog tests**

Run: `uv run pytest tests/unit/catalog tests/integration/admin/test_catalog.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/admin src/ai_gateway/catalog src/ai_gateway/main.py tests
git commit -m "feat: add provider and model catalog"
```

---

### Task 6: Define canonical chat contracts and protocol adapters

**Files:**
- Create: `src/ai_gateway/protocols/types.py`
- Create: `src/ai_gateway/protocols/base.py`
- Create: `src/ai_gateway/protocols/openai.py`
- Create: `src/ai_gateway/protocols/claude.py`
- Create: `src/ai_gateway/protocols/gemini.py`
- Create: `src/ai_gateway/protocols/registry.py`
- Test: `tests/contract/protocols/test_openai.py`
- Test: `tests/contract/protocols/test_claude.py`
- Test: `tests/contract/protocols/test_gemini.py`
- Test: `tests/contract/protocols/test_cross_conversion.py`

**Interfaces:**
- Produces immutable types `CanonicalRequest`, `CanonicalMessage`, `TextPart`, `ImagePart`, `ToolCallPart`, `ToolResultPart`, `CanonicalResponse`, `CanonicalUsage`, `StreamEvent`。
- Produces adapter methods `decode_request`, `encode_request`, `decode_response`, `encode_response`, `decode_stream_event`, `encode_stream_event`。

- [ ] **Step 1: Define canonical types in tests**

Use these exact core signatures:

```python
@dataclass(frozen=True, slots=True)
class CanonicalUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    model: str
    messages: Sequence[CanonicalMessage]
    system: Sequence[ContentPart]
    tools: Sequence[CanonicalTool]
    tool_choice: str | dict[str, Any] | None
    temperature: float | None
    top_p: float | None
    max_output_tokens: int | None
    stop_sequences: Sequence[str]
    stream: bool
    metadata: Mapping[str, Any]
```

- [ ] **Step 2: Add golden request/response fixtures**

For each protocol, cover text, system instructions, multi-turn roles, base64 and URL images, tool declarations, tool calls/results, stop reasons, usage, `temperature`, `top_p`, max tokens and streaming. Store sanitized fixtures in `tests/contract/fixtures/{openai,claude,gemini}/`.

- [ ] **Step 3: Write cross-conversion matrix tests**

Parametrize all nine pairs `(openai|claude|gemini) -> (openai|claude|gemini)`. Assert semantic equality after `decode_request -> encode_request -> decode_request`, allowing only documented protocol losses: unsupported vendor-specific metadata is retained under `metadata["vendor_extensions"]` but is not sent to a different provider.

- [ ] **Step 4: Implement same-protocol passthrough helpers**

`rewrite_passthrough_request(protocol, raw_body, upstream_model)` parses one JSON object, changes only the protocol's model field to `ModelRoute.upstream_model`, and preserves every other field. An inbound alias must never remain in the rewritten body. `rewrite_passthrough_sse` forwards event bytes unchanged. Unit tests compare JSON dictionaries and exact SSE byte sequences.

- [ ] **Step 5: Implement the three adapters**

Map roles, content blocks, tool calls/results, finish reasons and usage in both directions. Normalize finish reasons to `stop`, `length`, `tool_call`, `content_filter`, or `error`; encode the closest native value at the outbound boundary. Reject impossible conversions with HTTP 422 and code `unsupported_feature`, naming the field that cannot be represented.

- [ ] **Step 6: Run protocol contract tests**

Run: `uv run pytest tests/contract/protocols -v`

Expected: all nine conversion pairs pass for non-streaming and SSE fixtures.

- [ ] **Step 7: Commit**

```bash
git add src/ai_gateway/protocols tests/contract/protocols
git commit -m "feat: add ai protocol adapters"
```

---

### Task 7: Implement weighted routing, API Key filtering, and automatic route disablement

**Files:**
- Create: `src/ai_gateway/routing/types.py`
- Create: `src/ai_gateway/routing/service.py`
- Create: `src/ai_gateway/routing/health.py`
- Test: `tests/unit/routing/test_weighted.py`
- Test: `tests/integration/routing/test_health.py`

**Interfaces:**
- Consumes: `ResolvedModel`, `ApiKeyPrincipal`, `ModelRoute`。
- Produces: `RouteCandidate`, `select_route(model_id, principal, required_protocol=None)`, `record_success(route_id)`, `record_failure(route_id, failure)`。

- [ ] **Step 1: Write deterministic weighted-selection tests**

Inject `random.Random` into the router. With routes of weights `1` and `3`, 40,000 selections seeded with `20260721` must place the second route between 73% and 77%. Also assert disabled models/providers/protocols/routes, out-of-scope routes and routes with a future `disabled_until` are never returned.

- [ ] **Step 2: Write no-route behavior tests**

Assert `select_route` raises `NoRouteAvailable` with code `no_route_available`, requested model, and whether candidates were removed by API Key scope, transport capability, or health state. External responses must not reveal provider names or URLs.

- [ ] **Step 3: Implement candidate query and weighted choice**

Fetch eligible joins in one SQL query, filter API Key scope in SQL, lock nothing during selection, sort by route ID for deterministic tests, compute `ticket = rng.uniform(0, total_weight)`, and choose the first cumulative weight meeting the ticket.

- [ ] **Step 4: Write circuit-breaker transition tests**

```text
success                              -> failures=0, state=closed
HTTP 400/401/403/404/422             -> no health penalty
HTTP 408/429/500/502/503/504         -> increment failures
connect/read timeout, DNS, TLS error -> increment failures
third consecutive failure           -> state=open, disabled_until=now+60s
selection after cooldown             -> atomically state=half_open for one caller
half-open success                    -> closed
half-open failure                    -> open for another cooldown
```

- [ ] **Step 5: Implement atomic health updates**

Use SQL `UPDATE` expressions for failure increments and a conditional update `WHERE runtime_state='open' AND disabled_until <= now` to claim a half-open probe. The gateway must try at most the number of currently eligible candidates and must never retry after response bytes have been sent to a client.

- [ ] **Step 6: Run routing tests**

Run: `uv run pytest tests/unit/routing tests/integration/routing -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_gateway/routing tests/unit/routing tests/integration/routing
git commit -m "feat: add weighted routing and route health"
```

---

### Task 8: Build HTTP/HTTPS proxy selection with NO_PROXY host and CIDR support

**Files:**
- Create: `src/ai_gateway/transport/proxy.py`
- Create: `src/ai_gateway/transport/http.py`
- Test: `tests/unit/transport/test_proxy.py`
- Test: `tests/unit/transport/test_http_client.py`

**Interfaces:**
- Produces: `NoProxyMatcher.from_string(value)`, `matches(host, resolved_ips)`, `HttpClientFactory.client_for(url)`。

- [ ] **Step 1: Write NO_PROXY matcher tests**

Cover exact host, domain suffix `.example.com`, host plus port, IPv4, IPv6, `10.0.0.0/8`, `2001:db8::/32`, wildcard `*`, whitespace, and a hostname that resolves to an excluded CIDR. Patch `getaddrinfo`; do not perform external DNS.

- [ ] **Step 2: Implement safe matching**

Parse entries once with `ipaddress.ip_network(entry, strict=False)`. Compare normalized hostnames case-insensitively. Resolve DNS only when CIDR entries exist, cap resolution with a two-second timeout, and treat DNS failure as not excluded so normal transport error handling remains visible.

- [ ] **Step 3: Write proxy selection tests**

Assert HTTP uses `http_proxy`, HTTPS uses `https_proxy` with fallback to `http_proxy`, NO_PROXY returns a direct client, and credentials embedded in proxy URLs are removed from logs and exception text.

- [ ] **Step 4: Implement reusable httpx clients**

Create long-lived direct/http-proxy/https-proxy `httpx.AsyncClient` instances with HTTP/2, connection pooling, connect timeout 10s, read/write timeout 300s, and pool timeout 10s. Close them from FastAPI lifespan. Never create one client per request.

- [ ] **Step 5: Run transport tests**

Run: `uv run pytest tests/unit/transport -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/transport tests/unit/transport
git commit -m "feat: add proxy aware http transport"
```

---

### Task 9: Implement upstream authentication and model discovery

**Files:**
- Create: `src/ai_gateway/transport/upstream.py`
- Create: `src/ai_gateway/catalog/discovery.py`
- Create: `src/ai_gateway/catalog/scheduler.py`
- Create: `src/ai_gateway/admin/model_sync.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/contract/catalog/test_discovery.py`
- Test: `tests/integration/catalog/test_sync.py`

**Interfaces:**
- Produces: `build_upstream_request(route, inbound_headers, body)`, `discover_models(provider_protocol)`, `sync_provider_models(provider_id)`。
- Produces endpoint: `POST /admin/providers/{id}/sync-models`。

- [ ] **Step 1: Write protocol-specific auth tests**

Assert OpenAI sends `Authorization: Bearer`, Claude sends `x-api-key` plus `anthropic-version`, and Gemini sends `x-goog-api-key`. Strip inbound `authorization`, `x-api-key`, `cookie`, `host`, `content-length`, all hop-by-hop headers, and any configured provider header before merging encrypted provider headers.

- [ ] **Step 2: Write discovery contract tests**

Mock OpenAI `GET /models`, Claude `GET /v1/models`, and Gemini `GET /v1beta/models`. Normalize returned IDs by removing Gemini's `models/` prefix. Pagination must continue using each protocol's native cursor/page token until exhausted.

- [ ] **Step 3: Implement idempotent synchronization**

For every discovered upstream name, create the canonical model only when absent and create/update its `ModelRoute`. Never delete local models or aliases. Mark routes missing from a successful discovery as `enabled=false` only when they were previously created by auto-discovery; add `source=manual|discovered` to `model_routes` in a new migration `0004_route_source.py` with `down_revision = "0003"`.

- [ ] **Step 4: Implement scheduled auto-load**

At application startup, run an asyncio loop that selects enabled providers with `auto_load_models=true` and a due sync time. Use MySQL `GET_LOCK('model-sync:{provider_id}', 0)` so only one instance syncs a provider. Wake every 60 seconds; stop and await the task during shutdown.

- [ ] **Step 5: Run discovery and sync tests**

Run: `uv run pytest tests/contract/catalog tests/integration/catalog -v`

Expected: all tests PASS, including two concurrent schedulers producing one sync.

- [ ] **Step 6: Commit**

```bash
git add migrations src/ai_gateway/transport src/ai_gateway/catalog src/ai_gateway/admin/model_sync.py src/ai_gateway/main.py tests
git commit -m "feat: add provider model discovery"
```

---

### Task 10: Add request audit lifecycle, redaction, and GZIP storage

**Files:**
- Create: `src/ai_gateway/audit/redaction.py`
- Create: `src/ai_gateway/audit/codec.py`
- Create: `src/ai_gateway/audit/service.py`
- Create: `src/ai_gateway/admin/request_logs.py`
- Test: `tests/unit/audit/test_redaction.py`
- Test: `tests/unit/audit/test_codec.py`
- Test: `tests/integration/audit/test_request_logs.py`

**Interfaces:**
- Produces: `start_request(context: RequestContext, body: bytes) -> UUID`, `complete_request(request_id: UUID, result: RequestResult) -> None`, `fail_request(request_id: UUID, failure: RequestFailure) -> None`, `gzip_json(value: Mapping[str, Any]) -> bytes`, `gunzip_json(value: bytes) -> dict[str, Any]`。
- Produces endpoints: `GET /admin/request-logs`, `GET /admin/request-logs/{id}`。

- [ ] **Step 1: Write redaction tests**

Verify case-insensitive removal of `authorization`, `proxy-authorization`, `x-api-key`, `x-goog-api-key`, `cookie`, `set-cookie`; recursively replace JSON keys `api_key`, `access_token`, `refresh_token`, `password`, `secret`, and `credential` with `"[REDACTED]"`. Preserve non-sensitive message content.

- [ ] **Step 2: Write codec tests**

Canonicalize JSON with ORJSON sorted keys, truncate raw UTF-8 detail at `audit_body_limit_bytes` without producing invalid UTF-8, add `{ "truncated": true }` metadata, compress with `gzip.compress(payload, compresslevel=6, mtime=0)`, and verify deterministic round-trip.

- [ ] **Step 3: Implement request lifecycle writes**

Insert a `started` row before upstream I/O. Completion records provider/route, protocols, status, HTTP status, token usage, cost, latency and first-token latency. Client disconnect becomes `client_disconnected`; upstream errors become `failed`. Audit write failure is logged but must not replace a successful model response.

- [ ] **Step 4: Implement admin list and detail APIs**

List filters: request ID, user, API Key, model, provider, status, protocol, created time range; use cursor pagination `(created_at,id)` with maximum page size 200. List never decompresses blobs. Detail decompresses and returns redacted JSON to admins only.

- [ ] **Step 5: Run audit tests**

Run: `uv run pytest tests/unit/audit tests/integration/audit -v`

Expected: all tests PASS and compressed fixtures are smaller than their uncompressed repetitive payloads.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/audit src/ai_gateway/admin/request_logs.py tests/unit/audit tests/integration/audit
git commit -m "feat: add compressed request audit logs"
```

---

### Task 11: Implement token pricing, reservation, settlement, and balance ledger

**Files:**
- Create: `src/ai_gateway/billing/pricing.py`
- Create: `src/ai_gateway/billing/usage.py`
- Create: `src/ai_gateway/billing/service.py`
- Create: `src/ai_gateway/admin/billing.py`
- Test: `tests/unit/billing/test_pricing.py`
- Test: `tests/unit/billing/test_usage.py`
- Test: `tests/integration/billing/test_settlement.py`

**Interfaces:**
- Produces: `calculate_cost(model, usage) -> Decimal`, `estimate_request_tokens`, `reserve_balance`, `settle_request`。
- Produces endpoints: `GET /admin/users/{id}/ledger`, `POST /admin/users/{id}/balance-adjustments`, `GET /me/balance`。

- [ ] **Step 1: Write exact decimal pricing tests**

```python
def test_cost_uses_decimal_without_float_rounding():
    usage = CanonicalUsage(input_tokens=1_250, output_tokens=375)
    cost = calculate_cost(
        input_price=Decimal("0.15000000"),
        output_price=Decimal("0.60000000"),
        usage=usage,
    )
    assert cost == Decimal("0.00041250")
```

Quantize final cost to 8 decimal places using `ROUND_HALF_UP`.

- [ ] **Step 2: Write usage extraction and fallback tests**

Extract OpenAI `usage.prompt_tokens/completion_tokens`, Claude `usage.input_tokens/output_tokens`, and Gemini `usageMetadata.promptTokenCount/candidatesTokenCount`. For missing usage, estimate request and response text with `tiktoken` `cl100k_base`, count tool schema JSON, and mark `usage_source=estimated`; provider-reported usage is `usage_source=provider`.

- [ ] **Step 3: Write transactional settlement tests**

Cover sufficient balance, insufficient balance before upstream call, exact-zero balance, admin credit/debit, two concurrent charges against the same account, duplicate settlement idempotency key, and negative adjustment rejection unless the admin debit remains within the current balance.

- [ ] **Step 4: Implement reservation and final settlement**

Before routing, estimate worst-case cost from input estimate plus requested max output tokens and insert a negative `reservation` ledger entry while locking the account row `FOR UPDATE`. On completion, insert a positive `reservation_release` and negative `usage` entry in one transaction. For missing max output tokens, use a configurable default of 4096. If the actual charge exceeds the reservation, permit settlement down to zero and mark the account exhausted; subsequent requests fail with HTTP 402 `insufficient_balance`.

- [ ] **Step 5: Implement admin adjustments and user balance view**

Adjustment requests require `amount`, `reason`, and `idempotency_key`; positive values credit and negative values debit. `/me/balance` returns balance and total spent but not other users' ledger entries.

- [ ] **Step 6: Run billing tests**

Run: `uv run pytest tests/unit/billing tests/integration/billing -v`

Expected: all tests PASS; concurrent test never produces a negative balance.

- [ ] **Step 7: Commit**

```bash
git add src/ai_gateway/billing src/ai_gateway/admin/billing.py tests/unit/billing tests/integration/billing
git commit -m "feat: add token billing and balance ledger"
```

---

### Task 12: Build the non-streaming gateway orchestration and three compatible endpoints

**Files:**
- Create: `src/ai_gateway/gateway/service.py`
- Create: `src/ai_gateway/gateway/dependencies.py`
- Create: `src/ai_gateway/gateway/openai.py`
- Create: `src/ai_gateway/gateway/claude.py`
- Create: `src/ai_gateway/gateway/gemini.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/contract/gateway/test_non_streaming.py`
- Test: `tests/integration/gateway/test_failover.py`

**Interfaces:**
- Consumes: API Key auth, catalog, router, adapters, transport, audit, billing。
- Produces endpoints: `POST /v1/chat/completions`, `POST /v1/messages`, `POST /v1beta/models/{model}:generateContent`。

- [ ] **Step 1: Write the nine-pair endpoint contract tests**

For every inbound protocol and configured outbound protocol, send a native request to the corresponding endpoint, assert the mock upstream receives the correct native body/auth, and assert the client receives its inbound protocol's native response shape. Include alias resolution and verify the upstream sees `ModelRoute.upstream_model`, never the alias; when `canonical_name` differs from `upstream_model`, verify the route value wins.

- [ ] **Step 2: Write same-protocol passthrough tests**

Assert unknown vendor JSON fields survive unchanged, model is rewritten, hop-by-hop/auth headers are replaced, response status/body/content-type are preserved, and malformed JSON returns the inbound protocol's native 400 error without calling upstream.

- [ ] **Step 3: Implement the orchestration order**

Execute in this exact order: authenticate API Key; resolve model/alias; estimate and reserve balance; create audit row; select in-scope route; build passthrough or canonical request; send upstream; record route success/failure; convert response when required; extract/estimate usage; settle balance; complete audit; return native response.

- [ ] **Step 4: Implement bounded pre-response failover**

Retry only connection failures, timeouts, 408, 429 and 5xx, selecting a different route each time. Do not retry 4xx validation/auth responses, and do not exceed the number of eligible routes. Each failed attempt updates route health; the request audit records the final route plus an ordered, redacted attempt summary.

- [ ] **Step 5: Map gateway errors into native response envelopes**

Use stable internal codes `invalid_api_key`, `model_not_found`, `no_route_available`, `insufficient_balance`, `unsupported_feature`, `upstream_error`, `upstream_timeout`. Return OpenAI `{error:{message,type,code}}`, Claude `{type:"error",error:{type,message}}`, and Gemini `{error:{code,message,status}}` shapes with correct HTTP status.

- [ ] **Step 6: Run non-streaming gateway tests**

Run: `uv run pytest tests/contract/gateway/test_non_streaming.py tests/integration/gateway/test_failover.py -v`

Expected: all tests PASS and no test reaches the public network.

- [ ] **Step 7: Commit**

```bash
git add src/ai_gateway/gateway src/ai_gateway/main.py tests/contract/gateway tests/integration/gateway
git commit -m "feat: add non streaming gateway endpoints"
```

---

### Task 13: Add SSE streaming conversion and disconnect-safe settlement

**Files:**
- Create: `src/ai_gateway/transport/sse.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/gateway/openai.py`
- Modify: `src/ai_gateway/gateway/claude.py`
- Modify: `src/ai_gateway/gateway/gemini.py`
- Test: `tests/unit/transport/test_sse.py`
- Test: `tests/contract/gateway/test_streaming.py`
- Test: `tests/integration/gateway/test_stream_disconnect.py`

**Interfaces:**
- Produces: `SSEDecoder.feed(chunk: bytes) -> list[SSEEvent]`, `stream_gateway_response(context: GatewayContext, upstream: httpx.Response) -> AsyncIterator[bytes]`。
- Consumes: one `source_adapter.create_stream_decoder()` and one `target_adapter.create_stream_encoder()` per upstream response stream. These two context objects are created once before iteration and retained until the actual upstream EOF/finalization path.

**Mandatory stream-adapter contract:**

- Never call the isolated `decode_stream_event` or `encode_stream_event` helpers to convert a complete stream; they intentionally have no cross-frame state.
- For every native SSE frame, fan out the full tuple returned by `stream_decoder.decode(frame)` in order. For every canonical event, fan out every frame returned by `stream_encoder.encode(event)` in order.
- Skip `NO_STREAM_OUTPUT`/empty encoded frames. Empty encoder output is a target-native no-op, not a frame to feed back into a decoder.
- Call Gemini `stream_decoder.decode(b"")` exactly once and only when the upstream HTTP body reaches actual EOF. Never use empty bytes for an ordinary SSE event or encoder no-op.
- Preserve partial OpenAI/Claude tool argument fragments through the canonical stream. Assemble/buffer them only inside the target Gemini encoder, because Gemini function-call parts require a complete JSON argument object.
- When Claude is the target and input-token usage is known or estimated before the first frame, call `stream_encoder.set_initial_usage(input_tokens)` before encoding `message_start`. Claude input usage belongs on `message_start`; the encoder retains the terminal finish until cumulative final usage arrives and emits output usage on the final `message_delta`, without buffering the response body.

- [ ] **Step 1: Write incremental SSE parser tests**

Cover CRLF/LF, event split across arbitrary byte chunks, multi-line `data:`, comments/heartbeats, `event:`, empty data, UTF-8 split across chunks, OpenAI `[DONE]`, Claude named events, and Gemini JSON data frames.

- [ ] **Step 2: Write all nine streaming conversion tests**

Assert text deltas, parallel tool-call argument deltas, start/end events, finish reasons and final cumulative usage are converted into the inbound protocol's expected event sequence. Tests must retain one decoder and encoder context for the entire sequence, exercise tuple/frame fan-out, and cover Gemini EOF separately from ordinary no-output events. Same-protocol tests assert exact upstream bytes, including Claude input usage on `message_start` and output usage on the final `message_delta`.

- [ ] **Step 3: Implement streaming without buffering full responses**

Read `aiter_bytes()`, parse only when protocols differ, and emit each non-empty encoded frame immediately. Create the persistent decoder/encoder pair before the loop; do not recreate either context per frame. At actual EOF, invoke the Gemini decoder's empty-input terminal exactly once when Gemini is the source. Record first-token latency on the first non-heartbeat content event, and accumulate only cumulative usage plus a redacted audit preview capped by the configured byte limit.

- [ ] **Step 4: Implement disconnect and error finalization**

Put upstream close, balance settlement/reservation release, audit completion and route health update in `try/except/finally`. A disconnect settles using observed provider usage when present or estimated emitted content. Never retry after the first byte has been yielded.

- [ ] **Step 5: Run streaming tests**

Run: `uv run pytest tests/unit/transport/test_sse.py tests/contract/gateway/test_streaming.py tests/integration/gateway/test_stream_disconnect.py -v`

Expected: all tests PASS; a disconnect leaves no outstanding reservation.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/transport/sse.py src/ai_gateway/gateway tests
git commit -m "feat: add sse streaming gateway"
```

---

### Task 14: Expose model listings including aliases

**Files:**
- Create: `src/ai_gateway/gateway/models.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/contract/gateway/test_models.py`

**Interfaces:**
- Produces endpoints: `GET /v1/models`, `GET /v1/models/{id}`, `GET /v1beta/models`。

- [ ] **Step 1: Write model-listing contract tests**

Create one model `gpt-4.1-mini` with aliases `fast-chat` and `cheap-chat`. Assert all three names are returned as separately selectable IDs, each alias includes `canonical_model: gpt-4.1-mini` in gateway-owned metadata, disabled models/aliases are absent, and API Key model scope filters all names consistently.

- [ ] **Step 2: Implement native response shapes**

OpenAI returns `{object:"list", data:[{id,object:"model",owned_by:"gateway",metadata}]}`. Gemini returns `{models:[{name:"models/{id}",displayName,supportedGenerationMethods:["generateContent","streamGenerateContent"],gatewayMetadata}]}`. Sort by ID and alias for stable pagination.

- [ ] **Step 3: Run model listing tests**

Run: `uv run pytest tests/contract/gateway/test_models.py -v`

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/ai_gateway/gateway/models.py src/ai_gateway/main.py tests/contract/gateway/test_models.py
git commit -m "feat: expose models and aliases"
```

---

### Task 15: Add OpenAI Realtime and Gemini Live WebSocket relay

**Files:**
- Create: `src/ai_gateway/transport/websocket.py`
- Create: `src/ai_gateway/gateway/websocket.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/contract/gateway/test_websocket.py`
- Test: `tests/integration/gateway/test_websocket_billing.py`

**Interfaces:**
- Produces endpoints: `WS /v1/realtime`, `WS /v1beta/live`。
- Produces: `relay_websocket(client_ws, route, initial_request)`。

- [ ] **Step 1: Write transparent relay tests**

Use a local fake WebSocket server. Assert text and binary frames pass in both directions, close codes/reasons propagate, ping/pong keeps the connection alive, provider auth is injected upstream, client auth is not forwarded, and proxy selection matches HTTP rules.

- [ ] **Step 2: Write capability and scope tests**

The model is supplied through query string or the protocol's initial session message. Resolve aliases before route selection and rewrite the upstream query/initial session frame to `ModelRoute.upstream_model`; never forward the alias. Filter routes by API Key scope and protocol capability. Claude-only candidates close with application code `4400` and JSON code `unsupported_transport`; invalid keys close with `4401`; insufficient balance closes with `4402` before upstream connect.

- [ ] **Step 3: Implement bidirectional structured concurrency**

Use an AnyIO task group with one client-to-upstream task and one upstream-to-client task. When either side closes or fails, cancel the peer task, close both sockets once, update route health only for upstream/network failures, and finalize audit/billing in a shielded cancel scope.

- [ ] **Step 4: Implement WebSocket usage and billing**

Parse native OpenAI/Gemini usage events when available. Otherwise estimate text/audio metadata defined by the provider response and mark it estimated. Reserve balance before connect and periodically settle every 60 seconds or 100,000 tokens, whichever comes first, so long sessions cannot exceed available balance without detection.

- [ ] **Step 5: Run WebSocket tests**

Run: `uv run pytest tests/contract/gateway/test_websocket.py tests/integration/gateway/test_websocket_billing.py -v`

Expected: all tests PASS and cancellation leaves no connection/task or reservation leak.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/transport/websocket.py src/ai_gateway/gateway/websocket.py src/ai_gateway/main.py tests
git commit -m "feat: add websocket gateway relay"
```

---

### Task 16: Harden concurrency, migrations, startup, and observability

**Files:**
- Create: `src/ai_gateway/core/logging.py`
- Create: `src/ai_gateway/core/middleware.py`
- Create: `tests/integration/test_concurrency.py`
- Create: `tests/integration/test_startup.py`
- Create: `tests/unit/test_error_redaction.py`
- Modify: `src/ai_gateway/main.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: request correlation middleware and structured JSON application logs。

- [ ] **Step 1: Write startup and migration tests**

Assert application startup checks database connectivity and required migration head, fails fast in production when JWT/encryption secrets use example values, starts/closes shared HTTP clients and scheduler exactly once, and `/health` reports `503` when the database is unavailable.

- [ ] **Step 2: Write concurrency tests**

Run concurrent model sync, route half-open claims, balance settlements and API Key rotations against MySQL. Assert one half-open probe, one key replacement, no duplicate discovered routes, no duplicate ledger idempotency keys, and no negative balances.

- [ ] **Step 3: Add correlation and structured logs**

Accept or create `x-request-id`, validate it as a UUID, return it on HTTP responses, and include it in every application log. JSON logs contain timestamp, level, logger, event, request ID, route ID and exception class; they never contain bodies, API keys, tokens, provider URLs with credentials, or encrypted values.

- [ ] **Step 4: Add global error handlers**

Convert validation, auth, database, timeout and unexpected exceptions to stable native envelopes. Unexpected errors return a generic message and correlation ID; stack traces remain only in server logs.

- [ ] **Step 5: Run hardening tests**

Run: `uv run pytest tests/integration/test_concurrency.py tests/integration/test_startup.py tests/unit/test_error_redaction.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/core src/ai_gateway/main.py .env.example tests
git commit -m "feat: harden gateway runtime"
```

---

### Task 17: Add full regression, Docker deployment, CI, and operator documentation

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `compose.yaml`
- Create: `.github/workflows/ci.yml`
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/protocol-compatibility.md`
- Create: `docs/operations.md`
- Create: `scripts/create_admin.py`
- Create: `tests/e2e/test_gateway.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: production container, local app+MySQL Compose stack, CI pipeline, bootstrap-admin command and operator runbook。

- [ ] **Step 1: Write an end-to-end acceptance test**

The test starts the app against MySQL and a fake multi-protocol provider, creates an admin/user/provider/model/alias/route/API Key, credits the user, calls one non-streaming conversion, one streaming conversion and one WebSocket relay, then verifies exact ledger totals, route health, alias model listing and decompressible redacted request logs.

- [ ] **Step 2: Add a non-root production image**

Use a multi-stage `python:3.12-slim` build, install locked dependencies with `uv sync --frozen --no-dev`, copy `.venv` and source into the runtime stage, create user `gateway`, expose 8000, and run `uvicorn ai_gateway.main:app --host 0.0.0.0 --port 8000 --proxy-headers`.

- [ ] **Step 3: Add deployment Compose**

Define `gateway` and `mysql` services, MySQL healthcheck, gateway dependency on healthy MySQL, persistent database volume, read-only root filesystem for the app, `/tmp` tmpfs, dropped Linux capabilities, environment file, and a gateway healthcheck against `/health`.

- [ ] **Step 4: Add CI gates**

On pull requests and pushes, start MySQL 8.4, run `uv sync --frozen`, `uv run alembic upgrade head`, `uv run ruff check src tests`, `uv run mypy src`, and `uv run pytest --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90`. Build the Docker image after tests.

- [ ] **Step 5: Write operator documentation**

README includes local startup, migration, admin creation, curl examples for all three HTTP protocols and both WebSocket endpoints. Architecture docs include the request sequence, schema ownership and transaction boundaries. Compatibility docs list mapped fields and explicit losses. Operations docs include key rotation, credential encryption-key rotation procedure, backup/restore, log retention deletion by date, failed-route diagnosis, proxy/CIDR examples and safe rolling deployment.

- [ ] **Step 6: Run the complete delivery gate**

Run:

```bash
docker compose up -d mysql
uv run alembic upgrade head
uv run ruff check src tests
uv run mypy src
uv run pytest --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
docker build -t lean-ai-gateway:test .
docker compose config --quiet
```

Expected: every command exits 0, coverage is at least 90%, and no test uses real provider credentials or public network access.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore compose.yaml .github README.md docs scripts tests/e2e pyproject.toml uv.lock
git commit -m "docs: add deployment and complete regression suite"
```

---

## Delivery Milestones

1. **Foundation (Tasks 1-5):** 可登录、管理用户/Key/提供商/模型/别名/路由，数据库迁移稳定。
2. **Gateway Core (Tasks 6-9):** 协议转换、加权路由、熔断、代理和模型发现可独立测试。
3. **Accounting and Audit (Tasks 10-11):** GZIP 详情日志、Token 计费和并发安全余额上线。
4. **Serving (Tasks 12-15):** 非流、SSE、模型列表和 WebSocket 完整接入。
5. **Production Gate (Tasks 16-17):** 并发、部署、文档、CI、90% 覆盖率全部通过。

## Requirement Traceability

| Requirement | Tasks |
|---|---:|
| OpenAI、Gemini、Claude 多提供商与多协议 | 5, 6, 9, 12 |
| 基于权重随机路由、失败自动禁用 | 7, 12 |
| 三协议自动转换、同协议透传 | 6, 12, 13 |
| JWT、API Key、TOTP | 3, 4 |
| Token 成本与余额管理 | 2, 11, 12, 13, 15 |
| 完整请求日志、GZIP 详情 | 2, 10 |
| HTTP/HTTPS 代理、NO_PROXY、CIDR | 8 |
| 流、非流、WebSocket | 12, 13, 15 |
| 提供商多协议、自动加载模型开关 | 5, 9 |
| 模型与渠道关系表、权重、启用状态 | 2, 5, 7 |
| 模型别名、价格、策略、models 返回别名 | 5, 11, 14 |
| 别名请求转换为渠道原始模型名 | 5, 6, 12, 13, 15 |
| 独立 API Key 与渠道/模型范围 | 4, 7, 14 |
| 用户、API Key 关联、消费金额 | 2, 4, 11 |
| MySQL、Python、uv、Docker | 1, 2, 17 |
| 完善测试 | 每个任务的 TDD 步骤，最终覆盖率门槛 90% |

## Implementation Notes

- 建议先完成 Tasks 1-5 后做一次 schema/API 评审；表结构进入生产后再修改的成本最高。
- Tasks 6-9 可作为第二个评审点，重点核对协议 fixture 与真实官方协议文档，不把提供商私有字段误当成通用能力。
- Tasks 10-15 完成后进行一次故障注入测试：超时、429、5xx、客户端断流、MySQL 短暂不可用、代理不可达、进程取消。
- 第一版部署建议单进程多副本；模型同步用 MySQL named lock、余额用行锁、路由半开用条件更新，因此不依赖进程内共享状态。
