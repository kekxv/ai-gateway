# User Models and API Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authenticated regular users browse the enabled model catalog and fully manage only their own API keys without gaining any administrator capability.

**Architecture:** Keep every `/admin/*` permission boundary unchanged. Add authenticated `/user/models` and `/user/api-keys` routes; the server derives API-key ownership from the JWT user and applies ownership in every query. The existing Vue model and API-key pages become role-aware: administrators retain the full management UI, while regular users receive a read-only enabled-model view and self-service key workflow.

**Tech Stack:** FastAPI, SQLAlchemy asyncio, Pydantic v2, Vue 3, Pinia, Element Plus, Vitest/MSW, Playwright, MySQL 8.4.

## Global Constraints

- A regular user must never supply or select the API-key owner; ownership comes from the access token.
- Cross-user key lookup, update, rotation, and deletion return `404 api_key_not_found` to avoid disclosing existence.
- Regular users can create `all` or `models` scoped keys; provider-scoped keys remain administrator-only.
- The user model catalog contains enabled models and enabled aliases only and exposes no providers, routes, credentials, or upstream model names.
- Administrator endpoints and administrator console behavior remain backward compatible.
- Raw API keys appear only in create and rotate responses and must not enter test screenshots, traces, logs, or persistent browser storage.

---

### Task 1: Authenticated Read-Only Model Catalog

**Files:**
- Modify: `src/ai_gateway/admin/models.py`
- Modify: `src/ai_gateway/main.py`
- Create: `tests/integration/admin/test_self_service.py`

**Interfaces:**
- Consumes: `current_user`, `Model`, `ModelAlias`, and existing `ModelResponse` serialization.
- Produces: `GET /user/models -> list[ModelResponse]`, filtered to `Model.enabled = true` and enabled aliases.

- [ ] **Step 1: Write the failing integration test**

Create enabled and disabled models with enabled and disabled aliases. Request `/user/models` with `non_admin_client` and assert only the enabled model and enabled alias are returned. Assert `/admin/models` still returns the full administrator catalog.

- [ ] **Step 2: Verify the test fails for the missing route**

Run:

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest tests/integration/admin/test_self_service.py -k models -q
```

Expected: `404` for `/user/models`.

- [ ] **Step 3: Implement the authenticated catalog route**

Add a `user_models_router` with prefix `/user/models` and a list handler equivalent to:

```python
@user_models_router.get("", response_model=list[ModelResponse])
async def list_available_models(session: Session, _: CurrentUser) -> list[ModelResponse]:
    models = (
        await session.scalars(
            select(Model)
            .where(Model.enabled.is_(True))
            .options(selectinload(Model.aliases))
            .order_by(Model.id)
        )
    ).all()
    return [_model_response(model, enabled_aliases_only=True) for model in models]
```

Register this router in `create_app`. Do not change any `/admin/models` dependency.

- [ ] **Step 4: Verify the catalog test passes**

Run the command from Step 2 and expect all selected tests to pass.

- [ ] **Step 5: Commit the catalog slice**

```bash
git add src/ai_gateway/admin/models.py src/ai_gateway/main.py tests/integration/admin/test_self_service.py
git commit -m "feat: expose enabled models to users"
```

### Task 2: Ownership-Safe User API Key Endpoints

**Files:**
- Modify: `src/ai_gateway/admin/api_keys.py`
- Modify: `src/ai_gateway/main.py`
- Modify: `tests/integration/admin/test_self_service.py`

**Interfaces:**
- Consumes: existing API-key response schemas and key generation, hashing, relation validation, and rotation behavior.
- Produces: `GET/POST /user/api-keys`, `GET/PATCH/DELETE /user/api-keys/{id}`, and `POST /user/api-keys/{id}/rotate`.
- Produces request schemas `SelfApiKeyCreate` and `SelfApiKeyUpdate` without `user_id` or `provider_ids`.

- [ ] **Step 1: Write failing ownership and lifecycle tests**

Add tests that:

```python
created = await non_admin_client.post(
    "/user/api-keys",
    json={"name": "personal", "scope": "models", "model_ids": [enabled_model.id]},
)
assert created.status_code == 201
assert created.json()["user_id"] == regular_user_record.id
```

Then verify list, update, rotate, and delete work for that owner. Create a second user's key through `admin_client` and assert every regular-user item endpoint returns `404/api_key_not_found`, while the regular-user list excludes it. Assert payloads containing `user_id`, `provider_ids`, or provider-based scopes return `422`. Assert disabled model IDs are rejected.

- [ ] **Step 2: Verify the endpoint tests fail**

Run:

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest tests/integration/admin/test_self_service.py -k api_key -q
```

Expected: `404` for the new routes.

- [ ] **Step 3: Implement self-service routes with query-level ownership**

Add `self_router = APIRouter(prefix="/user/api-keys", tags=["user-api-keys"])`. Every item query must include both predicates:

```python
select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.user_id == user.id)
```

List must always include `where(ApiKey.user_id == user.id)`. Create must pass `user.id` to `_new_api_key`. Accept only `ApiKeyScope.ALL` and `ApiKeyScope.MODELS`, clear provider links, and validate selected model IDs with `Model.enabled.is_(True)`. Rotation must preserve the owner and current model restrictions while revoking the old key exactly once.

- [ ] **Step 4: Verify self-service and administrator regression tests**

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest tests/integration/admin/test_self_service.py tests/integration/admin/test_api_keys.py -q
```

- [ ] **Step 5: Commit the API-key slice**

```bash
git add src/ai_gateway/admin/api_keys.py src/ai_gateway/main.py tests/integration/admin/test_self_service.py
git commit -m "feat: let users manage their own api keys"
```

### Task 3: Regular-User Routes, Navigation, and Read-Only Models Page

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AdminLayout.vue`
- Modify: `frontend/src/api/models.ts`
- Modify: `frontend/src/views/ModelsView.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/tests/router.spec.ts`
- Modify: `frontend/tests/admin-layout.spec.ts`
- Modify: `frontend/tests/models.spec.ts`

**Interfaces:**
- Consumes: `GET /user/models` from Task 1 and `auth.isAdmin`.
- Produces: regular-user access to `/models`, a “可用模型” navigation item, and a read-only model view.

- [ ] **Step 1: Write failing router and page tests**

Assert a regular user can navigate to `/models` and `/api-keys`, while `/`, `/providers`, `/users`, and `/request-logs` still redirect to `/security`. Assert regular navigation contains “可用模型”, “接口密钥”, and “安全设置” only. Mount `ModelsView` with a regular-user Pinia store and assert it requests `/user/models` but never `/admin/providers` or `/admin/model-routes`; create/edit/delete/route controls and drawers must be absent.

- [ ] **Step 2: Verify the frontend tests fail**

```bash
cd frontend
npm test -- tests/router.spec.ts tests/admin-layout.spec.ts tests/models.spec.ts
```

Expected: regular-user route redirects and missing navigation/read-only behavior failures.

- [ ] **Step 3: Implement role-aware navigation and model loading**

Remove `requiresAdmin` from the `models` and `api-keys` route metadata. Keep administrator-only metadata on every other management route. Add `listAvailableModels()` calling `/user/models`. In `ModelsView`, load the administrator catalog exactly as before for administrators; for regular users load only `listAvailableModels()`, keep provider/routes arrays empty, change the heading to “可用模型”, and omit every mutation control and drawer. Add a `readonly` prop to `ModelCard` that hides model actions and the complete routes section.

- [ ] **Step 4: Verify the frontend slice passes**

Run the command from Step 2 and expect all selected tests to pass.

- [ ] **Step 5: Commit the model-page slice**

```bash
git add frontend/src/router/index.ts frontend/src/layouts/AdminLayout.vue frontend/src/api/models.ts \
  frontend/src/views/ModelsView.vue frontend/src/components/models/ModelCard.vue \
  frontend/tests/router.spec.ts frontend/tests/admin-layout.spec.ts frontend/tests/models.spec.ts
git commit -m "feat: show users the available model catalog"
```

### Task 4: Role-Aware API Key Page

**Files:**
- Modify: `frontend/src/api/apiKeys.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/views/ApiKeysView.vue`
- Modify: `frontend/src/components/api-keys/ApiKeyFormDrawer.vue`
- Modify: `frontend/tests/api-keys.spec.ts`

**Interfaces:**
- Consumes: user API-key endpoints from Task 2, `GET /user/models`, and `auth.user`.
- Produces: self-service list/create/update/rotate/delete calls and a form that fixes ownership to the current user.

- [ ] **Step 1: Write failing self-service page tests**

Mount `ApiKeysView` as a regular user. Assert it calls `/user/api-keys` and `/user/models`, makes no calls to `/admin/users` or `/admin/providers`, hides the owner selector and provider scopes, and creates with the literal body:

```json
{"name":"personal","scope":"models","is_active":true,"expires_at":null,"model_ids":[1]}
```

Assert edit, rotation, and deletion use `/user/api-keys/{id}`. Keep the one-time secret lifecycle assertions used by administrator tests.

- [ ] **Step 2: Verify the API-key page test fails**

```bash
cd frontend
npm test -- tests/api-keys.spec.ts
```

- [ ] **Step 3: Implement role-aware API functions and form**

Add `SelfApiKeyCreate`/`SelfApiKeyUpdate` types that omit owner and provider fields. Add self-service API functions under `/user/api-keys`. In `ApiKeysView.load`, branch by `auth.isAdmin`: preserve the four administrator requests; regular users request only their own keys and available models. Pass a fixed owner to `ApiKeyFormDrawer`; render the owner as non-editable text and restrict the scope options to `all` and `models`. Strip `user_id` before sending a regular-user create request.

- [ ] **Step 4: Verify API-key tests pass**

Run the command from Step 2 and expect all API-key tests to pass.

- [ ] **Step 5: Commit the API-key page slice**

```bash
git add frontend/src/api/apiKeys.ts frontend/src/api/types.ts frontend/src/views/ApiKeysView.vue \
  frontend/src/components/api-keys/ApiKeyFormDrawer.vue frontend/tests/api-keys.spec.ts
git commit -m "feat: add self-service api key console"
```

### Task 5: Documentation, Browser Acceptance, and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `example/README.md`
- Modify: `frontend/e2e/admin-console.spec.ts`

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: documented user capabilities and one browser journey proving role boundaries and self-owned key creation.

- [ ] **Step 1: Extend browser acceptance coverage**

Create a regular user through the administrator console, log in as that user, assert only available models/API keys/security navigation is present, create one self-owned key, acknowledge and remove the one-time secret, and assert administrator routes redirect. Do not enable Playwright screenshots, traces, or video for the secret-bearing test file.

- [ ] **Step 2: Update user-facing documentation**

Document that regular users can browse enabled models and manage only their own keys, while provider/user/model configuration remains administrator-only.

- [ ] **Step 3: Run complete verification**

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
uv run ruff check src tests migrations scripts
uv run ruff format --check src tests migrations scripts
uv run mypy src scripts
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
npm run e2e
```

Also run both Compose configuration checks and `git diff --check` from the repository root.

- [ ] **Step 4: Commit documentation and acceptance coverage**

```bash
git add README.md README.zh-CN.md example/README.md frontend/e2e/admin-console.spec.ts
git commit -m "test: cover regular user self service"
```
