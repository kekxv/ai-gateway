from __future__ import annotations

import asyncio
import gzip
import os
import socket
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import orjson
import pyotp
import pytest
import uvicorn
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedOK

from ai_gateway.core.config import Settings
from ai_gateway.core.security import hash_password
from ai_gateway.db.base import Base
from ai_gateway.db.models import (
    Account,
    ApiKey,
    ApiKeyModel,
    ApiKeyProvider,
    AuthRateLimit,
    LedgerEntry,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    RequestLogDetail,
    User,
)
from ai_gateway.main import REQUIRED_MIGRATION_HEAD, create_app

ADMIN_PASSWORD = "e2e-admin-password"
USER_PASSWORD = "e2e-user-password"
INITIAL_CREDIT = Decimal("10.00000000")
EXPECTED_RESERVATION_TOTAL = Decimal("0.09200000")
EXPECTED_USAGE_COST = Decimal("0.07000000")


@dataclass(slots=True)
class FakeProviderState:
    provider_secret: str
    openai_requests: list[dict[str, Any]] = field(default_factory=list)
    claude_requests: list[dict[str, Any]] = field(default_factory=list)
    gemini_requests: list[dict[str, Any]] = field(default_factory=list)
    websocket_authorization: str | None = None
    websocket_model: str | None = None
    websocket_frame: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProvisionedGateway:
    admin_headers: dict[str, str]
    admin_refresh_token: str
    user_id: int
    provider_id: int
    model_id: int
    route_id: int
    api_key_id: int
    api_key: str
    alias: str
    upstream_model: str
    claude_model_id: int
    claude_route_id: int
    claude_alias: str
    claude_upstream_model: str
    gemini_model_id: int
    gemini_route_id: int
    gemini_alias: str
    gemini_upstream_model: str
    body_secret: str


@asynccontextmanager
async def running_server(app: FastAPI) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2048)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_config=None,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        else:
            raise RuntimeError("uvicorn did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=10)
        listener.close()


def fake_provider_app(state: FakeProviderState) -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        payload = await request.json()
        state.openai_requests.append(
            {
                "path": request.url.path,
                "authorization": request.headers.get("authorization"),
                "payload": payload,
            }
        )
        if payload.get("stream") is True:

            async def frames() -> AsyncIterator[bytes]:
                values: tuple[dict[str, Any] | str, ...] = (
                    {
                        "id": "chatcmpl-e2e-stream",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "native-e2e-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "id": "chatcmpl-e2e-stream",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "native-e2e-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "streamed reply"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "id": "chatcmpl-e2e-stream",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "native-e2e-model",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    },
                    {
                        "id": "chatcmpl-e2e-stream",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "native-e2e-model",
                        "choices": [],
                        "usage": {
                            "prompt_tokens": 4,
                            "completion_tokens": 3,
                            "total_tokens": 7,
                        },
                    },
                    "[DONE]",
                )
                for value in values:
                    encoded = value if isinstance(value, str) else orjson.dumps(value).decode()
                    yield f"data: {encoded}\n\n".encode()

            return StreamingResponse(frames(), media_type="text/event-stream")

        return JSONResponse(
            {
                "id": "chatcmpl-e2e-non-stream",
                "object": "chat.completion",
                "created": 1,
                "model": "native-e2e-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "non-stream reply"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }
        )

    @app.post("/v1/messages")
    async def messages(request: Request) -> Response:
        payload = await request.json()
        state.claude_requests.append(
            {
                "path": request.url.path,
                "api_key": request.headers.get("x-api-key"),
                "anthropic_version": request.headers.get("anthropic-version"),
                "payload": payload,
            }
        )
        return JSONResponse(
            {
                "id": "msg-e2e-native",
                "type": "message",
                "role": "assistant",
                "model": payload["model"],
                "content": [{"type": "text", "text": "native Claude reply"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 6, "output_tokens": 4},
                "secret": state.provider_secret,
            }
        )

    @app.post("/v1beta/models/{model}:generateContent")
    async def generate_content(model: str, request: Request) -> Response:
        payload = await request.json()
        state.gemini_requests.append(
            {
                "path": request.url.path,
                "api_key": request.headers.get("x-goog-api-key"),
                "payload": payload,
            }
        )
        return JSONResponse(
            {
                "modelVersion": model,
                "responseId": "response-e2e-native",
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": [{"text": "native Gemini reply"}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 6},
                "secret": state.provider_secret,
            }
        )

    @app.websocket("/realtime")
    async def realtime(websocket: WebSocket) -> None:
        state.websocket_authorization = websocket.headers.get("authorization")
        state.websocket_model = websocket.query_params.get("model")
        offered = websocket.headers.get("sec-websocket-protocol", "")
        selected = "realtime" if "realtime" in offered.split(", ") else None
        await websocket.accept(subprotocol=selected)
        state.websocket_frame = orjson.loads(await websocket.receive_text())
        await websocket.send_json(
            {
                "type": "response.done",
                "response": {
                    "id": "response-e2e-websocket",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                    "secret": state.provider_secret,
                },
            }
        )
        await websocket.close(code=1000, reason="complete")

    return app


async def bootstrap_admin(
    engine: AsyncEngine,
    *,
    email: str,
) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        admin = User(
            email=email,
            password_hash=hash_password(ADMIN_PASSWORD),
            role="admin",
        )
        admin.account = Account()
        session.add(admin)
        await session.commit()


async def provision_gateway(
    client: httpx.AsyncClient,
    *,
    suffix: str,
    admin_email: str,
    provider_base_url: str,
    provider_secret: str,
) -> ProvisionedGateway:
    login = await client.post(
        "/auth/login",
        json={"email": admin_email, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    user = await client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": f"user-{suffix}@example.test",
            "password": USER_PASSWORD,
            "role": "user",
        },
    )
    assert user.status_code == 201, user.text
    user_id = int(user.json()["id"])

    websocket_url = provider_base_url.replace("http://", "ws://") + "/realtime"
    provider = await client.post(
        "/admin/providers",
        headers=admin_headers,
        json={
            "name": f"provider-{suffix}",
            "credential": {"api_key": provider_secret},
            "protocols": [
                {
                    "protocol": "openai",
                    "base_url": f"{provider_base_url}/v1",
                    "websocket_url": websocket_url,
                },
                {"protocol": "claude", "base_url": f"{provider_base_url}/v1"},
                {"protocol": "gemini", "base_url": f"{provider_base_url}/v1beta"},
            ],
        },
    )
    assert provider.status_code == 201, provider.text
    assert provider_secret not in provider.text
    provider_body = provider.json()
    provider_id = int(provider_body["id"])
    protocol_ids = {str(item["protocol"]): int(item["id"]) for item in provider_body["protocols"]}

    async def create_model_route(protocol: str) -> tuple[int, int, str, str]:
        qualifier = "" if protocol == "openai" else f"-{protocol}"
        alias = f"friendly{qualifier}-{suffix}"
        upstream_model = f"native{qualifier}-{suffix}"
        model = await client.post(
            "/admin/models",
            headers=admin_headers,
            json={
                "canonical_name": f"canonical{qualifier}-{suffix}",
                "display_name": f"E2E {protocol} model",
                "input_price_per_million": "1000.00000000",
                "output_price_per_million": "2000.00000000",
                "aliases": [alias],
            },
        )
        assert model.status_code == 201, model.text
        model_id = int(model.json()["id"])
        route = await client.post(
            "/admin/model-routes",
            headers=admin_headers,
            json={
                "model_id": model_id,
                "provider_id": provider_id,
                "provider_protocol_id": protocol_ids[protocol],
                "upstream_model": upstream_model,
                "weight": 100,
            },
        )
        assert route.status_code == 201, route.text
        return model_id, int(route.json()["id"]), alias, upstream_model

    model_id, route_id, alias, upstream_model = await create_model_route("openai")
    (
        claude_model_id,
        claude_route_id,
        claude_alias,
        claude_upstream_model,
    ) = await create_model_route("claude")
    (
        gemini_model_id,
        gemini_route_id,
        gemini_alias,
        gemini_upstream_model,
    ) = await create_model_route("gemini")

    api_key = await client.post(
        "/admin/api-keys",
        headers=admin_headers,
        json={
            "user_id": user_id,
            "name": "e2e-key",
            "scope": "providers_and_models",
            "provider_ids": [provider_id],
            "model_ids": [model_id, claude_model_id, gemini_model_id],
        },
    )
    assert api_key.status_code == 201, api_key.text

    credit = await client.post(
        f"/admin/users/{user_id}/balance-adjustments",
        headers=admin_headers,
        json={
            "amount": str(INITIAL_CREDIT),
            "reason": "E2E test credit",
            "idempotency_key": f"e2e-credit-{suffix}",
        },
    )
    assert credit.status_code == 201, credit.text
    assert Decimal(str(credit.json()["balance"])) == INITIAL_CREDIT

    return ProvisionedGateway(
        admin_headers=admin_headers,
        admin_refresh_token=str(login.json()["refresh_token"]),
        user_id=user_id,
        provider_id=provider_id,
        model_id=model_id,
        route_id=route_id,
        api_key_id=int(api_key.json()["id"]),
        api_key=str(api_key.json()["key"]),
        alias=alias,
        upstream_model=upstream_model,
        claude_model_id=claude_model_id,
        claude_route_id=claude_route_id,
        claude_alias=claude_alias,
        claude_upstream_model=claude_upstream_model,
        gemini_model_id=gemini_model_id,
        gemini_route_id=gemini_route_id,
        gemini_alias=gemini_alias,
        gemini_upstream_model=gemini_upstream_model,
        body_secret=f"request-body-secret-{suffix}",
    )


async def exercise_admin_and_auth_regression(
    client: httpx.AsyncClient,
    state: ProvisionedGateway,
    *,
    suffix: str,
    provider_base_url: str,
    provider_secret: str,
) -> None:
    refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": state.admin_refresh_token},
    )
    assert refresh.status_code == 200, refresh.text
    state.admin_headers["Authorization"] = f"Bearer {refresh.json()['access_token']}"

    totp_setup = await client.post("/auth/totp/setup", headers=state.admin_headers)
    assert totp_setup.status_code == 200, totp_setup.text
    query = parse_qs(urlparse(totp_setup.json()["otpauth_uri"]).query)
    totp_secret = query["secret"][0]
    totp_confirm = await client.post(
        "/auth/totp/confirm",
        headers=state.admin_headers,
        json={"code": pyotp.TOTP(totp_secret).now()},
    )
    assert totp_confirm.status_code == 200, totp_confirm.text
    assert totp_confirm.json() == {"totp_enabled": True}
    current_totp_required = await client.post("/auth/totp/setup", headers=state.admin_headers)
    assert current_totp_required.status_code == 401
    assert current_totp_required.json()["detail"]["code"] == "current_totp_required"

    users = await client.get("/admin/users", headers=state.admin_headers)
    user = await client.get(f"/admin/users/{state.user_id}", headers=state.admin_headers)
    assert users.status_code == user.status_code == 200
    duplicate_user = await client.post(
        "/admin/users",
        headers=state.admin_headers,
        json={
            "email": user.json()["email"],
            "password": USER_PASSWORD,
        },
    )
    assert duplicate_user.status_code == 409
    updated_user = await client.patch(
        f"/admin/users/{state.user_id}",
        headers=state.admin_headers,
        json={
            "email": user.json()["email"],
            "password": USER_PASSWORD,
            "admin_totp_code": pyotp.TOTP(totp_secret).now(),
            "role": "user",
            "is_active": True,
        },
    )
    assert updated_user.status_code == 200, updated_user.text

    provider = await client.get(
        f"/admin/providers/{state.provider_id}", headers=state.admin_headers
    )
    providers = await client.get("/admin/providers", headers=state.admin_headers)
    assert provider.status_code == providers.status_code == 200
    protocol_inputs = [
        {
            "id": item["id"],
            "protocol": item["protocol"],
            "base_url": item["base_url"],
            "websocket_url": item["websocket_url"],
            "enabled": item["enabled"],
        }
        for item in provider.json()["protocols"]
    ]
    updated_provider = await client.patch(
        f"/admin/providers/{state.provider_id}",
        headers=state.admin_headers,
        json={
            "name": provider.json()["name"],
            "credential": {"api_key": provider_secret},
            "enabled": True,
            "auto_load_models": False,
            "model_sync_interval_seconds": 86_400,
            "protocols": protocol_inputs,
        },
    )
    assert updated_provider.status_code == 200, updated_provider.text
    assert provider_secret not in updated_provider.text
    duplicate_provider = await client.post(
        "/admin/providers",
        headers=state.admin_headers,
        json={
            "name": provider.json()["name"],
            "credential": {"api_key": provider_secret},
        },
    )
    assert duplicate_provider.status_code == 409

    model = await client.get(f"/admin/models/{state.model_id}", headers=state.admin_headers)
    models = await client.get("/admin/models", headers=state.admin_headers)
    assert model.status_code == models.status_code == 200
    updated_model = await client.patch(
        f"/admin/models/{state.model_id}",
        headers=state.admin_headers,
        json={
            "canonical_name": model.json()["canonical_name"],
            "display_name": model.json()["display_name"],
            "input_price_per_million": model.json()["input_price_per_million"],
            "output_price_per_million": model.json()["output_price_per_million"],
            "enabled": True,
            "aliases": [
                {"alias": item["alias"], "enabled": item["enabled"]}
                for item in model.json()["aliases"]
            ],
            "routing_strategy": "weighted_random",
        },
    )
    assert updated_model.status_code == 200, updated_model.text
    duplicate_model = await client.post(
        "/admin/models",
        headers=state.admin_headers,
        json={
            "canonical_name": model.json()["canonical_name"],
            "display_name": "Duplicate",
        },
    )
    assert duplicate_model.status_code == 409

    routes = await client.get(
        "/admin/model-routes",
        headers=state.admin_headers,
        params={"model_id": state.model_id, "provider_id": state.provider_id},
    )
    route = await client.get(f"/admin/model-routes/{state.route_id}", headers=state.admin_headers)
    assert routes.status_code == route.status_code == 200
    updated_route = await client.patch(
        f"/admin/model-routes/{state.route_id}",
        headers=state.admin_headers,
        json={
            "model_id": state.model_id,
            "provider_id": state.provider_id,
            "provider_protocol_id": route.json()["provider_protocol_id"],
            "upstream_model": state.upstream_model,
            "weight": 100,
            "enabled": True,
        },
    )
    assert updated_route.status_code == 200, updated_route.text
    duplicate_route = await client.post(
        "/admin/model-routes",
        headers=state.admin_headers,
        json={
            "model_id": state.model_id,
            "provider_id": state.provider_id,
            "provider_protocol_id": route.json()["provider_protocol_id"],
            "upstream_model": state.upstream_model,
        },
    )
    assert duplicate_route.status_code == 409

    keys = await client.get(
        "/admin/api-keys",
        headers=state.admin_headers,
        params={"user_id": state.user_id},
    )
    key = await client.get(f"/admin/api-keys/{state.api_key_id}", headers=state.admin_headers)
    assert keys.status_code == key.status_code == 200
    updated_key = await client.patch(
        f"/admin/api-keys/{state.api_key_id}",
        headers=state.admin_headers,
        json={
            "name": "e2e-key-updated",
            "scope": "providers_and_models",
            "is_active": True,
            "provider_ids": [state.provider_id],
            "model_ids": [
                state.model_id,
                state.claude_model_id,
                state.gemini_model_id,
            ],
        },
    )
    assert updated_key.status_code == 200, updated_key.text

    auxiliary_user = await client.post(
        "/admin/users",
        headers=state.admin_headers,
        json={
            "email": f"aux-{suffix}@example.test",
            "password": USER_PASSWORD,
        },
    )
    assert auxiliary_user.status_code == 201, auxiliary_user.text
    auxiliary_user_id = int(auxiliary_user.json()["id"])
    auxiliary_provider = await client.post(
        "/admin/providers",
        headers=state.admin_headers,
        json={
            "name": f"aux-provider-{suffix}",
            "credential": {"api_key": provider_secret},
            "protocols": [{"protocol": "openai", "base_url": f"{provider_base_url}/v1"}],
        },
    )
    assert auxiliary_provider.status_code == 201, auxiliary_provider.text
    auxiliary_provider_id = int(auxiliary_provider.json()["id"])
    auxiliary_protocol_id = int(auxiliary_provider.json()["protocols"][0]["id"])
    auxiliary_model = await client.post(
        "/admin/models",
        headers=state.admin_headers,
        json={
            "canonical_name": f"aux-model-{suffix}",
            "display_name": "Auxiliary model",
        },
    )
    assert auxiliary_model.status_code == 201, auxiliary_model.text
    auxiliary_model_id = int(auxiliary_model.json()["id"])
    auxiliary_route = await client.post(
        "/admin/model-routes",
        headers=state.admin_headers,
        json={
            "model_id": auxiliary_model_id,
            "provider_id": auxiliary_provider_id,
            "provider_protocol_id": auxiliary_protocol_id,
            "upstream_model": "aux-upstream",
        },
    )
    assert auxiliary_route.status_code == 201, auxiliary_route.text
    auxiliary_route_id = int(auxiliary_route.json()["id"])
    auxiliary_key = await client.post(
        "/admin/api-keys",
        headers=state.admin_headers,
        json={
            "user_id": auxiliary_user_id,
            "name": "auxiliary",
            "scope": "providers_and_models",
            "provider_ids": [auxiliary_provider_id],
            "model_ids": [auxiliary_model_id],
        },
    )
    assert auxiliary_key.status_code == 201, auxiliary_key.text
    auxiliary_key_id = int(auxiliary_key.json()["id"])
    rotated_key = await client.post(
        f"/admin/api-keys/{auxiliary_key_id}/rotate", headers=state.admin_headers
    )
    assert rotated_key.status_code == 201, rotated_key.text
    old_key_delete = await client.delete(
        f"/admin/api-keys/{auxiliary_key_id}", headers=state.admin_headers
    )
    assert old_key_delete.status_code == 204
    replacement_id = int(rotated_key.json()["id"])
    replacement_delete = await client.delete(
        f"/admin/api-keys/{replacement_id}", headers=state.admin_headers
    )
    route_delete = await client.delete(
        f"/admin/model-routes/{auxiliary_route_id}", headers=state.admin_headers
    )
    model_delete = await client.delete(
        f"/admin/models/{auxiliary_model_id}", headers=state.admin_headers
    )
    provider_delete = await client.delete(
        f"/admin/providers/{auxiliary_provider_id}", headers=state.admin_headers
    )
    user_delete = await client.delete(
        f"/admin/users/{auxiliary_user_id}", headers=state.admin_headers
    )
    assert [
        replacement_delete.status_code,
        route_delete.status_code,
        model_delete.status_code,
        provider_delete.status_code,
        user_delete.status_code,
    ] == [204, 204, 204, 204, 204]


async def exercise_http_protocols(
    client: httpx.AsyncClient,
    state: ProvisionedGateway,
) -> None:
    non_stream = await client.post(
        "/v1/messages",
        headers={"x-api-key": state.api_key, "x-request-id": "e2e-non-stream"},
        json={
            "model": state.alias,
            "messages": [{"role": "user", "content": "hello over Claude"}],
            "max_tokens": 8,
            "secret": state.body_secret,
        },
    )
    assert non_stream.status_code == 200, non_stream.text
    assert non_stream.json()["content"] == "non-stream reply"
    assert non_stream.json()["usage"] == {"input_tokens": 10, "output_tokens": 5}

    stream = await client.post(
        f"/v1beta/models/{state.alias}:streamGenerateContent",
        headers={"x-goog-api-key": state.api_key, "x-request-id": "e2e-stream"},
        json={
            "contents": [{"role": "user", "parts": [{"text": "hello over Gemini"}]}],
            "generationConfig": {"maxOutputTokens": 8},
            "secret": state.body_secret,
        },
    )
    assert stream.status_code == 200, stream.text
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "streamed reply" in stream.text
    assert '"promptTokenCount":4' in stream.text
    assert '"candidatesTokenCount":3' in stream.text

    native_claude = await client.post(
        "/v1/messages",
        headers={"x-api-key": state.api_key, "x-request-id": "e2e-native-claude"},
        json={
            "model": state.claude_alias,
            "messages": [{"role": "user", "content": "hello native Claude"}],
            "max_tokens": 8,
            "secret": state.body_secret,
        },
    )
    assert native_claude.status_code == 200, native_claude.text
    assert native_claude.json()["content"] == [{"type": "text", "text": "native Claude reply"}]
    assert native_claude.json()["usage"] == {"input_tokens": 6, "output_tokens": 4}

    native_gemini = await client.post(
        f"/v1beta/models/{state.gemini_alias}:generateContent",
        headers={"x-goog-api-key": state.api_key, "x-request-id": "e2e-native-gemini"},
        json={
            "contents": [{"role": "user", "parts": [{"text": "hello native Gemini"}]}],
            "generationConfig": {"maxOutputTokens": 8},
            "secret": state.body_secret,
        },
    )
    assert native_gemini.status_code == 200, native_gemini.text
    assert native_gemini.json()["candidates"][0]["content"]["parts"] == [
        {"text": "native Gemini reply"}
    ]
    assert native_gemini.json()["usageMetadata"] == {
        "promptTokenCount": 7,
        "candidatesTokenCount": 6,
    }


async def exercise_websocket(base_url: str, state: ProvisionedGateway) -> dict[str, Any]:
    websocket_url = base_url.replace("http://", "ws://") + (
        f"/v1/realtime?model={state.alias}&intent=e2e"
    )
    async with connect(
        websocket_url,
        additional_headers={"Authorization": f"Bearer {state.api_key}"},
        subprotocols=["realtime"],
        proxy=None,
    ) as websocket:
        await websocket.send(
            orjson.dumps(
                {
                    "type": "session.update",
                    "session": {"model": state.alias, "input_text": "websocket hello"},
                    "secret": state.body_secret,
                }
            ).decode()
        )
        frame = orjson.loads(await websocket.recv())
        with pytest.raises(ConnectionClosedOK) as closed:
            await websocket.recv()
        assert closed.value.rcvd is not None
        assert closed.value.rcvd.code == 1000
    return frame


async def assert_durable_results(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    state: ProvisionedGateway,
    fake: FakeProviderState,
    *,
    user_email: str,
) -> None:
    models = await client.get("/v1/models", headers={"Authorization": f"Bearer {state.api_key}"})
    assert models.status_code == 200, models.text
    listed = {item["id"]: item for item in models.json()["data"]}
    assert state.alias in listed
    assert listed[state.alias]["metadata"] == {
        "canonical_model": f"canonical-{state.alias.removeprefix('friendly-')}"
    }

    for route_id in (state.route_id, state.claude_route_id, state.gemini_route_id):
        route = await client.get(f"/admin/model-routes/{route_id}", headers=state.admin_headers)
        assert route.status_code == 200, route.text
        assert route.json()["runtime_state"] == "closed"
        assert route.json()["consecutive_failures"] == 0
        assert route.json()["last_error_code"] is None

    ledger = await client.get(f"/admin/users/{state.user_id}/ledger", headers=state.admin_headers)
    assert ledger.status_code == 200, ledger.text
    entries = ledger.json()
    assert len(entries) == 16
    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    entries_by_request: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        totals[entry["kind"]] += Decimal(str(entry["amount"]))
        counts[entry["kind"]] += 1
        if entry["request_id"] is not None:
            entries_by_request[str(entry["request_id"])].append(entry)
    assert counts == {
        "adjustment": 1,
        "reservation": 5,
        "reservation_release": 5,
        "usage": 5,
    }
    assert totals["adjustment"] == INITIAL_CREDIT
    assert totals["reservation"] == -EXPECTED_RESERVATION_TOTAL
    assert totals["reservation_release"] == EXPECTED_RESERVATION_TOTAL
    assert totals["usage"] == -EXPECTED_USAGE_COST
    assert len(entries_by_request) == 5
    for request_entries in entries_by_request.values():
        paired = {entry["kind"]: Decimal(str(entry["amount"])) for entry in request_entries}
        assert set(paired) == {"reservation", "reservation_release", "usage"}
        assert paired["reservation"] == -paired["reservation_release"]
        assert paired["usage"] < 0
    assert sum(totals.values(), Decimal("0")) == INITIAL_CREDIT - EXPECTED_USAGE_COST

    user_login = await client.post(
        "/auth/login", json={"email": user_email, "password": USER_PASSWORD}
    )
    assert user_login.status_code == 200, user_login.text
    balance = await client.get(
        "/me/balance",
        headers={"Authorization": f"Bearer {user_login.json()['access_token']}"},
    )
    assert balance.status_code == 200, balance.text
    assert Decimal(str(balance.json()["balance"])) == INITIAL_CREDIT - EXPECTED_USAGE_COST
    assert Decimal(str(balance.json()["total_spent"])) == EXPECTED_USAGE_COST

    request_logs: list[RequestLog] = []
    for _ in range(100):
        async with AsyncSession(engine) as session:
            request_logs = list(
                await session.scalars(
                    select(RequestLog)
                    .where(RequestLog.user_id == state.user_id)
                    .order_by(RequestLog.created_at, RequestLog.id)
                )
            )
        if len(request_logs) == 5 and all(
            item.status.value == "completed" for item in request_logs
        ):
            break
        await asyncio.sleep(0.02)
    assert len(request_logs) == 5
    assert sorted(item.cost for item in request_logs) == [
        Decimal("0.00700000"),
        Decimal("0.01000000"),
        Decimal("0.01400000"),
        Decimal("0.01900000"),
        Decimal("0.02000000"),
    ]
    assert {item.transport for item in request_logs} == {"http", "websocket"}
    assert {item.inbound_protocol.value for item in request_logs} == {
        "claude",
        "gemini",
        "openai",
    }
    assert {item.outbound_protocol.value for item in request_logs} == {
        "claude",
        "gemini",
        "openai",
    }
    assert all(item.provider_id == state.provider_id for item in request_logs)
    assert {item.model_route_id for item in request_logs} == {
        state.route_id,
        state.claude_route_id,
        state.gemini_route_id,
    }

    async with AsyncSession(engine) as session:
        stored_details = {
            item.id: item
            for item in await session.scalars(
                select(RequestLogDetail).where(
                    RequestLogDetail.id.in_([item.id for item in request_logs])
                )
            )
        }

    request_details: list[dict[str, Any]] = []
    response_details: list[dict[str, Any]] = []
    for item in request_logs:
        stored_detail = stored_details[item.id]
        assert stored_detail.request_detail_gzip is not None
        assert stored_detail.response_detail_gzip is not None
        request_detail = orjson.loads(gzip.decompress(stored_detail.request_detail_gzip))
        response_detail = orjson.loads(gzip.decompress(stored_detail.response_detail_gzip))
        assert isinstance(request_detail, dict)
        assert isinstance(response_detail, dict)
        for detail in (request_detail, response_detail):
            serialized = orjson.dumps(detail)
            assert state.api_key.encode() not in serialized
            assert state.body_secret.encode() not in serialized
            assert fake.provider_secret.encode() not in serialized
            assert "x-api-key" not in detail.get("headers", {})
            assert "x-goog-api-key" not in detail.get("headers", {})
            assert "authorization" not in detail.get("headers", {})
        if item.transport == "http":
            assert request_detail.get("body", {}).get("secret") == "[REDACTED]"
        request_details.append(request_detail)
        response_details.append(response_detail)

    assert any(b'"secret":"[REDACTED]"' in orjson.dumps(item) for item in response_details)

    for request_log, request_detail, response_detail in zip(
        request_logs, request_details, response_details, strict=True
    ):
        detail_response = await client.get(
            f"/admin/request-logs/{request_log.id}", headers=state.admin_headers
        )
        assert detail_response.status_code == 200, detail_response.text
        assert detail_response.json()["request_detail"] == request_detail
        assert detail_response.json()["response_detail"] == response_detail

    filtered_logs = await client.get(
        "/admin/request-logs",
        headers=state.admin_headers,
        params={
            "user_id": state.user_id,
            "api_key_id": state.api_key_id,
            "model_id": state.model_id,
            "provider_id": state.provider_id,
            "status": "completed",
            "protocol": "openai",
            "page_size": 1,
        },
    )
    assert filtered_logs.status_code == 200, filtered_logs.text
    assert len(filtered_logs.json()["items"]) == 1

    route_delete = await client.delete(
        f"/admin/model-routes/{state.route_id}", headers=state.admin_headers
    )
    model_delete = await client.delete(
        f"/admin/models/{state.model_id}", headers=state.admin_headers
    )
    provider_delete = await client.delete(
        f"/admin/providers/{state.provider_id}", headers=state.admin_headers
    )
    assert (
        route_delete.status_code == model_delete.status_code == provider_delete.status_code == 409
    )

    assert len(fake.openai_requests) == 2
    assert all(
        request["authorization"] == f"Bearer {fake.provider_secret}"
        for request in fake.openai_requests
    )
    assert all(
        request["payload"]["model"] == state.upstream_model for request in fake.openai_requests
    )
    assert {request["path"] for request in fake.openai_requests} == {"/v1/chat/completions"}
    assert {bool(request["payload"]["stream"]) for request in fake.openai_requests} == {
        False,
        True,
    }

    assert fake.claude_requests == [
        {
            "path": "/v1/messages",
            "api_key": fake.provider_secret,
            "anthropic_version": "2023-06-01",
            "payload": {
                "model": state.claude_upstream_model,
                "messages": [{"role": "user", "content": "hello native Claude"}],
                "max_tokens": 8,
                "secret": state.body_secret,
            },
        }
    ]
    assert fake.gemini_requests == [
        {
            "path": f"/v1beta/models/{state.gemini_upstream_model}:generateContent",
            "api_key": fake.provider_secret,
            "payload": {
                "contents": [{"role": "user", "parts": [{"text": "hello native Gemini"}]}],
                "generationConfig": {"maxOutputTokens": 8},
                "secret": state.body_secret,
            },
        }
    ]
    assert fake.websocket_authorization == f"Bearer {fake.provider_secret}"
    assert fake.websocket_model == state.upstream_model
    assert fake.websocket_frame is not None
    assert fake.websocket_frame["session"]["model"] == state.upstream_model
    assert fake.websocket_frame["secret"] == state.body_secret


async def cleanup_e2e_records(engine: AsyncEngine, suffix: str) -> None:
    async with AsyncSession(engine) as session:
        await session.execute(delete(AuthRateLimit))
        user_ids = list(
            await session.scalars(
                select(User.id).where(
                    User.email.in_(
                        [
                            f"admin-{suffix}@example.test",
                            f"user-{suffix}@example.test",
                            f"aux-{suffix}@example.test",
                        ]
                    )
                )
            )
        )
        provider_ids = list(
            await session.scalars(
                select(Provider.id).where(
                    Provider.name.in_([f"provider-{suffix}", f"aux-provider-{suffix}"])
                )
            )
        )
        model_ids = list(
            await session.scalars(
                select(Model.id).where(
                    Model.canonical_name.in_(
                        [
                            f"canonical-{suffix}",
                            f"canonical-claude-{suffix}",
                            f"canonical-gemini-{suffix}",
                            f"aux-model-{suffix}",
                        ]
                    )
                )
            )
        )
        api_key_ids = list(
            await session.scalars(select(ApiKey.id).where(ApiKey.user_id.in_(user_ids)))
        )
        account_ids = list(
            await session.scalars(select(Account.id).where(Account.user_id.in_(user_ids)))
        )

        if user_ids:
            await session.execute(delete(RequestLog).where(RequestLog.user_id.in_(user_ids)))
        if account_ids:
            await session.execute(
                delete(LedgerEntry).where(LedgerEntry.account_id.in_(account_ids))
            )
        if api_key_ids:
            await session.execute(
                delete(ApiKeyProvider).where(ApiKeyProvider.api_key_id.in_(api_key_ids))
            )
            await session.execute(
                delete(ApiKeyModel).where(ApiKeyModel.api_key_id.in_(api_key_ids))
            )
            await session.execute(delete(ApiKey).where(ApiKey.id.in_(api_key_ids)))
        if model_ids:
            await session.execute(delete(ModelRoute).where(ModelRoute.model_id.in_(model_ids)))
            await session.execute(delete(ModelAlias).where(ModelAlias.model_id.in_(model_ids)))
            await session.execute(delete(Model).where(Model.id.in_(model_ids)))
        if provider_ids:
            await session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id.in_(provider_ids))
            )
            await session.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
        if account_ids:
            await session.execute(delete(Account).where(Account.id.in_(account_ids)))
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


@pytest.mark.e2e
async def test_gateway_end_to_end_against_mysql_and_local_provider() -> None:
    database_url = os.getenv("GATEWAY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.fail("GATEWAY_TEST_DATABASE_URL is required for the E2E test")

    suffix = uuid4().hex
    admin_email = f"admin-{suffix}@example.test"
    user_email = f"user-{suffix}@example.test"
    provider_secret = f"provider-secret-{suffix}"
    fake = FakeProviderState(provider_secret=provider_secret)
    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        await connection.execute(text("DELETE FROM alembic_version"))
        await connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": REQUIRED_MIGRATION_HEAD},
        )
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        jwt_secret="e2e-jwt-secret-at-least-32-bytes-long",
        encryption_key=Fernet.generate_key().decode(),
        no_proxy="127.0.0.1,localhost",
        model_sync_interval_seconds=86_400,
        billing_default_max_output_tokens=8,
        billing_recovery_interval_seconds=60,
    )

    try:
        await bootstrap_admin(engine, email=admin_email)
        async with running_server(fake_provider_app(fake)) as provider_url:
            async with running_server(create_app(settings)) as gateway_url:
                async with httpx.AsyncClient(
                    base_url=gateway_url,
                    timeout=10,
                    trust_env=False,
                ) as client:
                    state = await provision_gateway(
                        client,
                        suffix=suffix,
                        admin_email=admin_email,
                        provider_base_url=provider_url,
                        provider_secret=provider_secret,
                    )
                    await exercise_admin_and_auth_regression(
                        client,
                        state,
                        suffix=suffix,
                        provider_base_url=provider_url,
                        provider_secret=provider_secret,
                    )
                    await exercise_http_protocols(client, state)
                    websocket_frame = await exercise_websocket(gateway_url, state)
                    assert websocket_frame["response"]["usage"] == {
                        "input_tokens": 3,
                        "output_tokens": 2,
                    }
                    await assert_durable_results(
                        client,
                        engine,
                        state,
                        fake,
                        user_email=user_email,
                    )
    finally:
        await cleanup_e2e_records(engine, suffix)
        await engine.dispose()
