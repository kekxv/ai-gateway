from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet

from ai_gateway.catalog.balance import (
    BalanceConfigError,
    BalanceProbe,
    BalanceQueryConfig,
    BalanceQueryError,
    balance_url,
    detect_balance_types,
    extract_json_path,
    parse_balance_response,
    query_balance,
    validate_balance_config,
)
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import BalanceQueryType, Protocol
from ai_gateway.core.security import encrypt_secret


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="unit-test-secret-at-least-32-bytes-long",
        encryption_key=Fernet.generate_key().decode(),
    )


def _probe(
    *,
    base_url: str = "https://upstream.example.com/v1",
    credential: dict[str, object] | None = None,
    config: BalanceQueryConfig | None = None,
    protocol: Protocol = Protocol.OPENAI,
) -> BalanceProbe:
    settings = _settings()
    payload = orjson.dumps(credential if credential is not None else {"api_key": "sk-test"})
    return BalanceProbe(
        base_url=base_url,
        credential_encrypted=encrypt_secret(payload.decode(), settings=settings),
        protocol=protocol,
        config=config or BalanceQueryConfig(),
    )


def test_balance_url_targets_each_upstream_root() -> None:
    assert (
        balance_url("https://newapi.example.com/v1", BalanceQueryType.NEW_API, BalanceQueryConfig())
        == "https://newapi.example.com/api/user/self"
    )
    assert (
        balance_url("https://api.deepseek.com/v1", BalanceQueryType.DEEPSEEK, BalanceQueryConfig())
        == "https://api.deepseek.com/user/balance"
    )
    assert (
        balance_url(
            "https://openrouter.ai/api/v1", BalanceQueryType.OPENROUTER, BalanceQueryConfig()
        )
        == "https://openrouter.ai/api/v1/credits"
    )
    assert (
        balance_url("https://openrouter.ai", BalanceQueryType.OPENROUTER, BalanceQueryConfig())
        == "https://openrouter.ai/api/v1/credits"
    )
    assert (
        balance_url(
            "https://proxy.example.com/v1",
            BalanceQueryType.CUSTOM,
            BalanceQueryConfig(path="/billing/balance"),
        )
        == "https://proxy.example.com/v1/billing/balance"
    )


def test_balance_url_prefers_configured_base_url_override() -> None:
    config = BalanceQueryConfig(base_url="https://override.example.com")
    assert (
        balance_url("https://ignored.example.com/v1", BalanceQueryType.NEW_API, config)
        == "https://override.example.com/api/user/self"
    )


def test_custom_balance_configuration_is_validated() -> None:
    with pytest.raises(BalanceConfigError):
        validate_balance_config(BalanceQueryType.CUSTOM, BalanceQueryConfig(path="/balance"))
    with pytest.raises(BalanceConfigError):
        validate_balance_config(
            BalanceQueryType.CUSTOM,
            BalanceQueryConfig(amount_path="data.balance"),
        )
    validate_balance_config(
        BalanceQueryType.CUSTOM,
        BalanceQueryConfig(path="/balance", amount_path="data.balance"),
    )


def test_balance_config_rejects_unknown_and_unsafe_fields() -> None:
    with pytest.raises(BalanceConfigError):
        BalanceQueryConfig.from_mapping({"unknown": "value"})
    with pytest.raises(BalanceConfigError):
        BalanceQueryConfig.from_mapping({"headers": {"Host": "evil.example.com"}})
    with pytest.raises(BalanceConfigError):
        BalanceQueryConfig.from_mapping({"headers": {"X-Test": "line\nbreak"}})
    with pytest.raises(BalanceConfigError):
        BalanceQueryConfig.from_mapping({"divisor": "not-a-number"})
    with pytest.raises(BalanceConfigError):
        BalanceQueryConfig.from_mapping({"method": "DELETE"})

    config = BalanceQueryConfig.from_mapping(
        {"headers": {"X-Test": "ok"}, "divisor": "500000", "method": "post", "user_id": "42"}
    )
    assert config.headers == {"X-Test": "ok"}
    assert config.divisor == Decimal("500000")
    assert config.method == "POST"
    assert config.to_mapping()["user_id"] == "42"


def test_extract_json_path_supports_nested_lists() -> None:
    payload = {"data": {"balance_infos": [{"total_balance": "12.5"}]}}
    assert extract_json_path(payload, "data.balance_infos[0].total_balance") == "12.5"
    with pytest.raises(BalanceQueryError):
        extract_json_path(payload, "data.missing")
    with pytest.raises(BalanceQueryError):
        extract_json_path(payload, "data.balance_infos[3].total_balance")
    with pytest.raises(BalanceQueryError):
        extract_json_path(payload, "")


def test_parse_new_api_quota_into_currency_units() -> None:
    result = parse_balance_response(
        BalanceQueryType.NEW_API,
        BalanceQueryConfig(),
        {"success": True, "data": {"quota": 1250000, "used_quota": 250000}},
    )
    assert result.amount == Decimal("2.50000000")
    assert result.used == Decimal("0.50000000")
    assert result.currency == "USD"


def test_parse_new_api_reports_upstream_failure() -> None:
    with pytest.raises(BalanceQueryError, match="invalid access token"):
        parse_balance_response(
            BalanceQueryType.NEW_API,
            BalanceQueryConfig(),
            {"success": False, "message": "invalid access token"},
        )
    with pytest.raises(BalanceQueryError):
        parse_balance_response(BalanceQueryType.NEW_API, BalanceQueryConfig(), {"success": True})


def test_parse_deepseek_selects_requested_currency() -> None:
    payload = {
        "is_available": True,
        "balance_infos": [
            {"currency": "CNY", "total_balance": "9.99"},
            {"currency": "USD", "total_balance": "3.50"},
        ],
    }
    result = parse_balance_response(
        BalanceQueryType.DEEPSEEK, BalanceQueryConfig(currency="USD"), payload
    )
    assert result.amount == Decimal("3.50000000")
    assert result.currency == "USD"
    assert result.is_available is True

    default_result = parse_balance_response(
        BalanceQueryType.DEEPSEEK, BalanceQueryConfig(), payload
    )
    assert default_result.currency == "CNY"
    assert default_result.amount == Decimal("9.99000000")


def test_parse_openrouter_subtracts_usage_from_credits() -> None:
    result = parse_balance_response(
        BalanceQueryType.OPENROUTER,
        BalanceQueryConfig(),
        {"data": {"total_credits": 20, "total_usage": 7.25}},
    )
    assert result.amount == Decimal("12.75000000")
    assert result.used == Decimal("7.25000000")


def test_parse_custom_applies_divisor_and_used_path() -> None:
    config = BalanceQueryConfig(
        amount_path="result.remaining",
        used_path="result.spent",
        divisor=Decimal("100"),
        currency="EUR",
    )
    result = parse_balance_response(
        BalanceQueryType.CUSTOM, config, {"result": {"remaining": 1234, "spent": 100}}
    )
    assert result.amount == Decimal("12.34000000")
    assert result.used == Decimal("1.00000000")
    assert result.currency == "EUR"


@pytest.mark.asyncio
async def test_query_balance_sends_provider_credential_and_user_header() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"success": True, "data": {"quota": 500000}})

    config = BalanceQueryConfig(user_id="7", headers={"X-Trace": "1"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await query_balance(
            _probe(base_url="https://newapi.example.com/v1", config=config),
            BalanceQueryType.NEW_API,
            client=client,
            settings=_settings(),
        )

    assert result.amount == Decimal("1.00000000")
    request = captured[0]
    assert str(request.url) == "https://newapi.example.com/api/user/self"
    assert request.headers["authorization"] == "Bearer sk-test"
    assert request.headers["new-api-user"] == "7"
    assert request.headers["x-trace"] == "1"


@pytest.mark.asyncio
async def test_query_balance_prefers_configured_credential_override() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"is_available": True, "balance_infos": []})

    probe = _probe(config=BalanceQueryConfig(api_key="access-token"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BalanceQueryError):
            await query_balance(
                probe, BalanceQueryType.DEEPSEEK, client=client, settings=_settings()
            )

    assert captured[0].headers["authorization"] == "Bearer access-token"


@pytest.mark.asyncio
async def test_detect_balance_types_returns_only_responding_upstreams() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/user/self":
            return httpx.Response(200, json={"data": {"quota": 500000}})
        if path == "/user/balance":
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(404, json={"error": "not found"})

    failures: dict[BalanceQueryType, BaseException] = {}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resolved = await detect_balance_types(
            _probe(base_url="https://newapi.example.com/v1"),
            client=client,
            settings=_settings(),
            failures=failures,
        )

    assert [item.query_type for item in resolved] == [BalanceQueryType.NEW_API]
    assert set(failures) == {BalanceQueryType.DEEPSEEK, BalanceQueryType.OPENROUTER}
    rejected = failures[BalanceQueryType.DEEPSEEK]
    assert isinstance(rejected, httpx.HTTPStatusError)
    assert rejected.response.status_code == 401

    async def openrouter_first(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=(
                {"data": {"total_credits": 5, "total_usage": 1}}
                if request.url.path.endswith("/credits")
                else {"data": {"quota": 500000}}
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(openrouter_first)) as client:
        resolved = await detect_balance_types(
            _probe(base_url="https://openrouter.ai/api/v1"),
            client=client,
            settings=_settings(),
        )

    assert [item.query_type for item in resolved] == [
        BalanceQueryType.OPENROUTER,
        BalanceQueryType.NEW_API,
    ]


@pytest.mark.asyncio
async def test_query_balance_propagates_upstream_status_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await query_balance(
                _probe(), BalanceQueryType.NEW_API, client=client, settings=_settings()
            )
