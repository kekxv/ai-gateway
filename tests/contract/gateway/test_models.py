from __future__ import annotations

from collections.abc import AsyncIterator
from hashlib import sha256

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.db.models import (
    ApiKey,
    ApiKeyModel,
    ApiKeyProvider,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    User,
)
from ai_gateway.db.session import get_session
from ai_gateway.gateway.models import router as models_router
from ai_gateway.gateway.service import native_error_response
from ai_gateway.main import create_app

HeaderValues = dict[str, str] | list[tuple[str, str]]


def _raw_key(scope: ApiKeyScope) -> str:
    return f"sk-gw-model-listing-{scope.value}"


def _api_key(scope: ApiKeyScope) -> tuple[User, ApiKey, str]:
    raw_key = _raw_key(scope)
    user = User(
        email=f"model-listing-{scope.value}@example.com",
        password_hash="unused",
    )
    api_key = ApiKey(
        name=scope.value,
        key_prefix=raw_key[:12],
        key_hash=sha256(raw_key.encode()).digest(),
        scope=scope,
    )
    user.api_keys.append(api_key)
    return user, api_key, raw_key


def _provider(name: str, *protocols: Protocol, enabled: bool = True) -> Provider:
    provider = Provider(
        name=name,
        credential_encrypted=b"unused",
        enabled=enabled,
    )
    provider.protocols.extend(
        ProviderProtocol(
            protocol=protocol,
            base_url=f"https://{name}.{protocol.value}.example",
        )
        for protocol in protocols
    )
    return provider


def _model(name: str, *, enabled: bool = True) -> Model:
    return Model(canonical_name=name, display_name=name.replace("-", " ").title(), enabled=enabled)


def _route(
    model: Model,
    provider: Provider,
    protocol: Protocol,
    *,
    enabled: bool = True,
) -> ModelRoute:
    provider_protocol = next(item for item in provider.protocols if item.protocol is protocol)
    return ModelRoute(
        model=model,
        provider=provider,
        provider_protocol=provider_protocol,
        upstream_model=model.canonical_name,
        enabled=enabled,
    )


def _client(
    session: AsyncSession,
    raw_key: str | None = None,
    *,
    headers: HeaderValues | None = None,
    app: FastAPI | None = None,
) -> AsyncClient:
    active_app = app or FastAPI()
    if app is None:
        active_app.include_router(models_router)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    active_app.dependency_overrides[get_session] = override_session
    client_headers: HeaderValues = headers or {}
    if raw_key is not None:
        if isinstance(client_headers, dict):
            client_headers = {"Authorization": f"Bearer {raw_key}", **client_headers}
        else:
            client_headers = [("Authorization", f"Bearer {raw_key}"), *client_headers]
    return AsyncClient(
        transport=ASGITransport(app=active_app),
        base_url="http://test",
        headers=client_headers,
    )


async def _listing_catalog(session: AsyncSession) -> tuple[dict[ApiKeyScope, str], Model]:
    openai_provider = _provider("listing-openai", Protocol.OPENAI)
    gemini_provider = _provider("listing-gemini", Protocol.GEMINI)
    claude_provider = _provider("listing-claude", Protocol.CLAUDE)
    disabled_provider = _provider("listing-disabled-provider", Protocol.OPENAI, enabled=False)
    disabled_protocol_provider = _provider("listing-disabled-protocol", Protocol.GEMINI)
    disabled_protocol_provider.protocols[0].enabled = False

    model = _model("gpt-4.1-mini")
    model.display_name = "GPT 4.1 Mini"
    model.aliases.extend(
        [
            ModelAlias(alias="fast-chat"),
            ModelAlias(alias="cheap-chat"),
            ModelAlias(alias="retired-chat", enabled=False),
        ]
    )
    disabled_model = _model("disabled-model", enabled=False)
    disabled_model.aliases.append(ModelAlias(alias="disabled-model-alias"))
    wrong_channel = _model("claude-only")
    no_route = _model("no-route")
    disabled_route = _model("disabled-route")
    disabled_provider_model = _model("disabled-provider-model")
    disabled_protocol_model = _model("disabled-protocol-model")

    session.add_all(
        [
            _route(model, openai_provider, Protocol.OPENAI),
            _route(model, gemini_provider, Protocol.GEMINI),
            _route(disabled_model, openai_provider, Protocol.OPENAI),
            _route(disabled_model, gemini_provider, Protocol.GEMINI),
            _route(wrong_channel, claude_provider, Protocol.CLAUDE),
            _route(disabled_route, openai_provider, Protocol.OPENAI, enabled=False),
            _route(disabled_route, gemini_provider, Protocol.GEMINI, enabled=False),
            _route(disabled_provider_model, disabled_provider, Protocol.OPENAI),
            _route(disabled_protocol_model, disabled_protocol_provider, Protocol.GEMINI),
            no_route,
        ]
    )

    raw_keys: dict[ApiKeyScope, str] = {}
    for scope in ApiKeyScope:
        user, api_key, raw_key = _api_key(scope)
        session.add(user)
        await session.flush()
        if scope in {ApiKeyScope.MODELS, ApiKeyScope.PROVIDERS_AND_MODELS}:
            session.add(ApiKeyModel(api_key_id=api_key.id, model=model))
        if scope in {ApiKeyScope.PROVIDERS, ApiKeyScope.PROVIDERS_AND_MODELS}:
            session.add(ApiKeyProvider(api_key_id=api_key.id, provider=openai_provider))
            session.add(ApiKeyProvider(api_key_id=api_key.id, provider=gemini_provider))
        raw_keys[scope] = raw_key
    await session.flush()
    return raw_keys, model


async def test_openai_and_gemini_list_selectable_aliases_in_native_shapes(
    session: AsyncSession,
) -> None:
    raw_keys, _ = await _listing_catalog(session)
    async with _client(session, raw_keys[ApiKeyScope.ALL]) as client:
        openai_response = await client.get("/v1/models")
        gemini_response = await client.get("/v1beta/models")

    assert openai_response.status_code == 200
    assert openai_response.json() == {
        "object": "list",
        "data": [
            {
                "id": "cheap-chat",
                "object": "model",
                "owned_by": "gateway",
                "metadata": {"canonical_model": "gpt-4.1-mini"},
            },
            {
                "id": "fast-chat",
                "object": "model",
                "owned_by": "gateway",
                "metadata": {"canonical_model": "gpt-4.1-mini"},
            },
            {
                "id": "gpt-4.1-mini",
                "object": "model",
                "owned_by": "gateway",
                "metadata": {},
            },
        ],
    }
    assert gemini_response.status_code == 200
    assert gemini_response.json() == {
        "models": [
            {
                "name": "models/cheap-chat",
                "displayName": "GPT 4.1 Mini",
                "supportedGenerationMethods": [
                    "generateContent",
                    "streamGenerateContent",
                ],
                "gatewayMetadata": {"canonical_model": "gpt-4.1-mini"},
            },
            {
                "name": "models/fast-chat",
                "displayName": "GPT 4.1 Mini",
                "supportedGenerationMethods": [
                    "generateContent",
                    "streamGenerateContent",
                ],
                "gatewayMetadata": {"canonical_model": "gpt-4.1-mini"},
            },
            {
                "name": "models/gpt-4.1-mini",
                "displayName": "GPT 4.1 Mini",
                "supportedGenerationMethods": [
                    "generateContent",
                    "streamGenerateContent",
                ],
                "gatewayMetadata": {},
            },
        ]
    }


async def test_openai_detail_preserves_alias_identity_and_scope(
    session: AsyncSession,
) -> None:
    raw_keys, _ = await _listing_catalog(session)
    async with _client(session, raw_keys[ApiKeyScope.MODELS]) as client:
        alias_response = await client.get("/v1/models/fast-chat")
        canonical_response = await client.get("/v1/models/gpt-4.1-mini")
        disabled_alias_response = await client.get("/v1/models/retired-chat")
        absent_response = await client.get("/v1/models/no-route")

    assert alias_response.status_code == 200
    assert alias_response.json() == {
        "id": "fast-chat",
        "object": "model",
        "owned_by": "gateway",
        "metadata": {"canonical_model": "gpt-4.1-mini"},
    }
    assert canonical_response.status_code == 200
    assert canonical_response.json() == {
        "id": "gpt-4.1-mini",
        "object": "model",
        "owned_by": "gateway",
        "metadata": {},
    }
    for response in (disabled_alias_response, absent_response):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "model_not_found"


@pytest.mark.parametrize(
    ("path", "expected_id", "metadata"),
    [
        ("/v1/models/vendor/model", "vendor/model", {}),
        ("/v1/models/vendor%2Fmodel", "vendor/model", {}),
        (
            "/v1/models/fast/family",
            "fast/family",
            {"canonical_model": "vendor/model"},
        ),
        (
            "/v1/models/fast%2Ffamily",
            "fast/family",
            {"canonical_model": "vendor/model"},
        ),
    ],
)
async def test_openai_detail_accepts_slash_ids_from_list(
    session: AsyncSession,
    path: str,
    expected_id: str,
    metadata: dict[str, str],
) -> None:
    provider = _provider("slash-openai", Protocol.OPENAI)
    model = _model("vendor/model")
    model.aliases.append(ModelAlias(alias="fast/family"))
    session.add(_route(model, provider, Protocol.OPENAI))
    user, _, raw_key = _api_key(ApiKeyScope.ALL)
    session.add(user)
    await session.flush()

    async with _client(session, raw_key) as client:
        listing = await client.get("/v1/models")
        detail = await client.get(path)

    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["data"]] == [
        "fast/family",
        "vendor/model",
    ]
    assert detail.status_code == 200
    assert detail.json() == {
        "id": expected_id,
        "object": "model",
        "owned_by": "gateway",
        "metadata": metadata,
    }


@pytest.mark.parametrize("scope", list(ApiKeyScope))
async def test_all_api_key_scope_modes_filter_names_through_same_channel_route(
    session: AsyncSession,
    scope: ApiKeyScope,
) -> None:
    raw_keys, allowed_model = await _listing_catalog(session)
    other_provider = _provider(f"other-{scope.value}", Protocol.OPENAI, Protocol.GEMINI)
    other_model = _model(f"other-model-{scope.value}")
    other_model.aliases.append(ModelAlias(alias=f"other-alias-{scope.value}"))
    session.add_all(
        [
            _route(other_model, other_provider, Protocol.OPENAI),
            _route(other_model, other_provider, Protocol.GEMINI),
        ]
    )
    await session.flush()

    if scope is ApiKeyScope.ALL:
        expected_ids = {
            "cheap-chat",
            "fast-chat",
            "gpt-4.1-mini",
            f"other-alias-{scope.value}",
            f"other-model-{scope.value}",
        }
    else:
        expected_ids = {"cheap-chat", "fast-chat", allowed_model.canonical_name}

    async with _client(session, raw_keys[scope]) as client:
        openai_response = await client.get("/v1/models")
        gemini_response = await client.get("/v1beta/models")

    assert openai_response.status_code == 200
    assert {item["id"] for item in openai_response.json()["data"]} == expected_ids
    assert {
        item["name"].removeprefix("models/") for item in gemini_response.json()["models"]
    } == expected_ids


async def test_provider_scope_does_not_leak_a_model_from_a_different_channel_route(
    session: AsyncSession,
) -> None:
    openai_provider = _provider("correlated-openai", Protocol.OPENAI)
    gemini_provider = _provider("correlated-gemini", Protocol.GEMINI)
    model = _model("correlated-model")
    session.add_all(
        [
            _route(model, openai_provider, Protocol.OPENAI),
            _route(model, gemini_provider, Protocol.GEMINI),
        ]
    )
    user, api_key, raw_key = _api_key(ApiKeyScope.PROVIDERS)
    session.add(user)
    await session.flush()
    session.add(ApiKeyProvider(api_key_id=api_key.id, provider=gemini_provider))
    await session.flush()

    async with _client(session, raw_key) as client:
        openai_response = await client.get("/v1/models")
        gemini_response = await client.get("/v1beta/models")

    assert openai_response.json() == {"object": "list", "data": []}
    assert [item["name"] for item in gemini_response.json()["models"]] == [
        "models/correlated-model"
    ]


@pytest.mark.parametrize(
    ("path", "header_name"),
    [
        ("/v1/models", "x-api-key"),
        ("/v1beta/models", "x-goog-api-key"),
    ],
)
async def test_native_api_key_headers_authenticate_model_lists(
    session: AsyncSession,
    path: str,
    header_name: str,
) -> None:
    raw_keys, _ = await _listing_catalog(session)
    raw_key = raw_keys[ApiKeyScope.ALL]
    async with _client(session, headers={header_name: raw_key}) as client:
        response = await client.get(path)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        [
            ("Authorization", f"Bearer {_raw_key(ApiKeyScope.ALL)}"),
            ("Authorization", "Bearer sk-gw-conflicting-duplicate"),
        ],
        [
            ("Authorization", f"Bearer {_raw_key(ApiKeyScope.ALL)}"),
            ("x-api-key", "sk-gw-conflicting-multiple"),
        ],
    ],
)
async def test_conflicting_credentials_use_native_openai_error(
    session: AsyncSession,
    headers: HeaderValues,
) -> None:
    async with _client(session, headers=headers) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Credential headers contain different API keys",
            "type": "authentication_error",
            "code": "invalid_api_key",
        }
    }
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize(
    ("headers", "expected_message"),
    [
        ({}, "An API key is required"),
        ({"Authorization": "Bearer sk-gw-invalid-model-key"}, "Invalid or expired API key"),
    ],
)
async def test_missing_and_invalid_auth_preserve_bearer_challenge(
    session: AsyncSession,
    headers: HeaderValues,
    expected_message: str,
) -> None:
    async with _client(session, headers=headers) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "message": expected_message,
            "type": "authentication_error",
            "code": "invalid_api_key",
        }
    }


def test_native_error_response_copies_only_safe_http_exception_headers() -> None:
    response = native_error_response(
        Protocol.OPENAI,
        HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Invalid API key"},
            headers={
                "WWW-Authenticate": "Bearer realm=gateway",
                "Retry-After": "5",
                "Set-Cookie": "gateway-secret=must-not-copy",
                "Location": "https://unsafe.example",
            },
        ),
    )

    assert response.headers["www-authenticate"] == "Bearer realm=gateway"
    assert response.headers["retry-after"] == "5"
    assert "set-cookie" not in response.headers
    assert "location" not in response.headers


async def test_create_app_registers_model_routes_with_app_session_override(
    session: AsyncSession,
) -> None:
    provider = _provider("create-app-openai", Protocol.OPENAI)
    model = _model("create-app-model")
    session.add(_route(model, provider, Protocol.OPENAI))
    user, _, raw_key = _api_key(ApiKeyScope.ALL)
    session.add(user)
    await session.flush()
    app = create_app()

    async with _client(session, raw_key, app=app) as client:
        listing = await client.get("/v1/models")
        detail = await client.get("/v1/models/create-app-model")

    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["data"]] == ["create-app-model"]
    assert detail.status_code == 200
    assert detail.json()["id"] == "create-app-model"


async def test_claude_endpoint_returns_claude_format_with_anthropic_version_header(
    session: AsyncSession,
) -> None:
    """Return Claude format when the anthropic-version header is present."""
    provider = _provider("claude-listing", Protocol.CLAUDE)
    model = _model("claude-3-opus")
    model.display_name = "Claude 3 Opus"
    session.add(_route(model, provider, Protocol.CLAUDE))
    user, _, raw_key = _api_key(ApiKeyScope.ALL)
    session.add(user)
    await session.flush()

    # Claude endpoint with anthropic-version header
    async with _client(session, raw_key, headers={"anthropic-version": "2023-06-01"}) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "id": "claude-3-opus",
                "display_name": "Claude 3 Opus",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
    }


async def test_dedicated_anthropic_model_routes_do_not_require_version_header(
    session: AsyncSession,
) -> None:
    claude_provider = _provider("dedicated-claude", Protocol.CLAUDE)
    openai_provider = _provider("dedicated-openai", Protocol.OPENAI)
    claude_model = _model("claude-dedicated")
    claude_model.display_name = "Claude Dedicated"
    claude_model.aliases.append(ModelAlias(alias="claude-friendly"))
    openai_model = _model("openai-only")
    session.add_all(
        [
            _route(claude_model, claude_provider, Protocol.CLAUDE),
            _route(openai_model, openai_provider, Protocol.OPENAI),
        ]
    )
    user, _, raw_key = _api_key(ApiKeyScope.ALL)
    session.add(user)
    await session.flush()

    async with _client(session, headers={"x-api-key": raw_key}) as client:
        listing = await client.get("/anthropic/v1/models")
        alias = await client.get("/anthropic/v1/models/claude-friendly")
        canonical = await client.get("/anthropic/v1/models/claude-dedicated")
        openai_only = await client.get("/anthropic/v1/models/openai-only")
        missing = await client.get("/anthropic/v1/models/missing")

    assert listing.status_code == 200
    assert listing.json() == {
        "data": [
            {
                "id": "claude-dedicated",
                "display_name": "Claude Dedicated",
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": "claude-friendly",
                "display_name": "Claude Dedicated",
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]
    }
    assert alias.status_code == 200
    assert alias.json()["id"] == "claude-friendly"
    assert canonical.status_code == 200
    assert canonical.json()["id"] == "claude-dedicated"
    for response in (openai_only, missing):
        assert response.status_code == 404
        assert response.json()["type"] == "error"
        assert response.json()["error"]["type"] == "model_not_found"


async def test_openai_endpoint_without_anthropic_version_returns_openai_format(
    session: AsyncSession,
) -> None:
    """Return OpenAI format when the anthropic-version header is absent."""
    provider = _provider("openai-backward-compat", Protocol.OPENAI)
    model = _model("gpt-4")
    session.add(_route(model, provider, Protocol.OPENAI))
    user, _, raw_key = _api_key(ApiKeyScope.ALL)
    session.add(user)
    await session.flush()

    # OpenAI endpoint without anthropic-version header
    async with _client(session, raw_key) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "id": "gpt-4",
                "object": "model",
                "owned_by": "gateway",
                "metadata": {},
            }
        ],
    }


async def test_claude_endpoint_filters_by_claude_protocol_routes(
    session: AsyncSession,
) -> None:
    """Test that Claude endpoint only returns models with CLAUDE protocol routes."""
    openai_provider = _provider("mixed-openai", Protocol.OPENAI)
    claude_provider = _provider("mixed-claude", Protocol.CLAUDE)

    openai_model = _model("gpt-4-turbo")
    claude_model = _model("claude-3-sonnet")

    session.add_all(
        [
            _route(openai_model, openai_provider, Protocol.OPENAI),
            _route(claude_model, claude_provider, Protocol.CLAUDE),
        ]
    )
    user, _, raw_key = _api_key(ApiKeyScope.ALL)
    session.add(user)
    await session.flush()

    # Claude endpoint should only return Claude models
    async with _client(session, raw_key, headers={"anthropic-version": "2023-06-01"}) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["id"] == "claude-3-sonnet"


async def test_claude_endpoint_respects_api_key_scopes(
    session: AsyncSession,
) -> None:
    """Test that Claude endpoint respects API key scope restrictions."""
    provider = _provider("scoped-claude", Protocol.CLAUDE)
    allowed_model = _model("claude-3-haiku")
    denied_model = _model("claude-3-opus-2")

    session.add_all(
        [
            _route(allowed_model, provider, Protocol.CLAUDE),
            _route(denied_model, provider, Protocol.CLAUDE),
        ]
    )
    user, api_key, raw_key = _api_key(ApiKeyScope.MODELS)
    session.add(user)
    await session.flush()
    session.add(ApiKeyModel(api_key_id=api_key.id, model=allowed_model))
    await session.flush()

    async with _client(session, raw_key, headers={"anthropic-version": "2023-06-01"}) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["id"] == "claude-3-haiku"


async def test_claude_endpoint_handles_authentication_errors(
    session: AsyncSession,
) -> None:
    """Test that Claude endpoint returns proper authentication errors."""
    # Missing authentication
    async with _client(session, headers={"anthropic-version": "2023-06-01"}) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 401
    assert "error" in response.json()

    # Invalid API key
    async with _client(
        session, headers={"anthropic-version": "2023-06-01", "x-api-key": "sk-gw-invalid-key"}
    ) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 401
    assert "error" in response.json()
