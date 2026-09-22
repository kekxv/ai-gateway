from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from ai_gateway.catalog.credentials import ProviderCredential
from ai_gateway.catalog.model_pricing import (
    ModelPriceError,
    fetch_upstream_pricing,
    parse_group_ratios,
    parse_model_prices,
    pricing_url,
    select_group_ratio,
    self_url,
)
from ai_gateway.core.enums import Protocol


def _credential(api_key: str = "sk-test") -> ProviderCredential:
    return ProviderCredential(
        api_key=api_key,
        auth_scheme="Bearer",
        auth_header=None,
        anthropic_version="2023-06-01",
    )


def _pricing_payload() -> dict[str, object]:
    return {
        "success": True,
        "data": [
            {
                "model_name": "gpt-4o",
                "quota_type": 0,
                "model_ratio": 1.25,
                "completion_ratio": 4,
                "model_price": 0,
            },
            {
                "model_name": "gpt-3.5-turbo",
                "quota_type": 0,
                "model_ratio": 0.5,
                "completion_ratio": 3,
            },
            {
                "model_name": "dall-e-3",
                "quota_type": 1,
                "model_ratio": 0,
                "model_price": 0.04,
            },
        ],
        "group_ratio": {"default": 1, "svip": 0.5},
        "usable_group": {"default": "默认分组"},
    }


def test_pricing_url_targets_the_upstream_root() -> None:
    assert pricing_url("https://newapi.example.com/v1") == "https://newapi.example.com/api/pricing"
    assert pricing_url("https://newapi.example.com/") == "https://newapi.example.com/api/pricing"
    assert self_url("https://newapi.example.com/v1beta") == (
        "https://newapi.example.com/api/user/self"
    )


def test_pricing_url_requires_a_base_url() -> None:
    with pytest.raises(ModelPriceError):
        pricing_url("  ")


def test_parse_model_prices_converts_ratios_into_token_prices() -> None:
    models = parse_model_prices(_pricing_payload())

    assert models["gpt-4o"].input_price_per_million == Decimal("2.50000000")
    assert models["gpt-4o"].output_price_per_million == Decimal("10.00000000")
    assert models["gpt-4o"].model_ratio == Decimal("1.25")
    assert models["gpt-3.5-turbo"].input_price_per_million == Decimal("1.00000000")
    assert models["gpt-3.5-turbo"].output_price_per_million == Decimal("3.00000000")


def test_parse_model_prices_keeps_fixed_price_models_out_of_token_pricing() -> None:
    models = parse_model_prices(_pricing_payload())

    fixed = models["dall-e-3"]
    assert fixed.quota_type == 1
    assert fixed.is_token_priced is False
    assert fixed.fixed_price == Decimal("0.04")
    assert fixed.input_price_per_million is None


def test_parse_model_prices_accepts_the_ratio_map_shape() -> None:
    payload = {
        "success": True,
        "data": {
            "model_ratio": {"gpt-4o": 1.25, "text-embedding-3-small": 0.02},
            "completion_ratio": {"gpt-4o": 4},
            "model_price": {"mj_imagine": 0.1},
            "group_ratio": {"default": 1, "svip": 0.5},
        },
    }

    models = parse_model_prices(payload)

    assert models["gpt-4o"].output_price_per_million == Decimal("10.00000000")
    assert models["text-embedding-3-small"].input_price_per_million == Decimal("0.04000000")
    assert models["text-embedding-3-small"].output_price_per_million == Decimal("0.04000000")
    assert models["mj_imagine"].quota_type == 1
    assert models["mj_imagine"].is_token_priced is False


def test_parse_model_prices_rejects_unknown_shapes() -> None:
    with pytest.raises(ModelPriceError):
        parse_model_prices({"success": True, "data": ["gpt-4o"]})
    with pytest.raises(ModelPriceError):
        parse_model_prices({"success": True, "data": {}})


def test_parse_model_prices_ignores_unusable_ratios() -> None:
    payload = {
        "data": [
            {"model_name": "broken", "model_ratio": "abc"},
            {"model_name": "negative", "model_ratio": -1},
            {"model_name": "boolean", "model_ratio": True},
            {"model_name": "huge", "model_ratio": 1e9},
            {"model_name": "ok", "model_ratio": 0.0333},
            {"model_name": 7, "model_ratio": 1},
        ]
    }

    models = parse_model_prices(payload)

    assert set(models) == {"ok"}
    assert models["ok"].input_price_per_million == Decimal("0.06660000")


def test_parse_group_ratios_reads_both_payload_shapes() -> None:
    assert parse_group_ratios(_pricing_payload()) == {
        "default": Decimal("1"),
        "svip": Decimal("0.5"),
    }
    assert parse_group_ratios(
        {"data": {"model_ratio": {"a": 1}, "group_ratio": {"vip": "0.8"}}}
    ) == {"vip": Decimal("0.8")}
    assert parse_group_ratios({"data": []}) == {}


def test_select_group_ratio_prefers_the_requested_group() -> None:
    ratios = {"default": Decimal("1"), "svip": Decimal("0.5")}

    assert select_group_ratio(ratios, "svip") == ("svip", Decimal("0.5"))
    assert select_group_ratio(ratios, "unknown") == ("default", Decimal("1"))
    assert select_group_ratio({}, "svip") == ("svip", Decimal("1"))


@pytest.mark.asyncio
async def test_fetch_upstream_pricing_uses_the_token_group() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/user/self":
            return httpx.Response(200, json={"success": True, "data": {"group": "svip"}})
        return httpx.Response(200, json=_pricing_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pricing = await fetch_upstream_pricing(
            base_url="https://newapi.example.com/v1",
            credential=_credential("sk-relay"),
            group_credential=_credential("access-token"),
            protocol=Protocol.OPENAI,
            user_id="25",
            extra_headers={"X-Trace": "1"},
            client=client,
        )

    assert pricing.group == "svip"
    assert pricing.group_ratio == Decimal("0.5")
    assert pricing.models["gpt-4o"].input_price_per_million == Decimal("2.50000000")
    assert str(captured[0].url) == "https://newapi.example.com/api/pricing"
    assert captured[0].headers["authorization"] == "Bearer sk-relay"
    assert captured[0].headers["x-trace"] == "1"
    assert str(captured[1].url) == "https://newapi.example.com/api/user/self"
    assert captured[1].headers["authorization"] == "Bearer access-token"
    assert captured[1].headers["new-api-user"] == "25"


@pytest.mark.asyncio
async def test_fetch_upstream_pricing_retries_the_price_list_with_the_console_token() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/pricing":
            if request.headers["authorization"] == "Bearer sk-relay":
                return httpx.Response(401, json={"success": False, "message": "unauthorized"})
            return httpx.Response(200, json=_pricing_payload())
        return httpx.Response(200, json={"success": True, "data": {"group": "svip"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pricing = await fetch_upstream_pricing(
            base_url="https://newapi.example.com",
            credential=_credential("sk-relay"),
            group_credential=_credential("access-token"),
            protocol=Protocol.OPENAI,
            client=client,
        )

    assert pricing.models["gpt-4o"].input_price_per_million == Decimal("2.50000000")
    assert [request.headers["authorization"] for request in captured] == [
        "Bearer sk-relay",
        "Bearer access-token",
        "Bearer access-token",
    ]


@pytest.mark.asyncio
async def test_fetch_upstream_pricing_falls_back_to_the_default_group() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/user/self":
            return httpx.Response(401, json={"success": False, "message": "unauthorized"})
        return httpx.Response(200, json=_pricing_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pricing = await fetch_upstream_pricing(
            base_url="https://newapi.example.com",
            credential=_credential(),
            protocol=Protocol.OPENAI,
            client=client,
        )

    assert pricing.group == "default"
    assert pricing.group_ratio == Decimal("1")


@pytest.mark.asyncio
async def test_fetch_upstream_pricing_reports_a_missing_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"success": False, "message": "not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelPriceError, match="/api/pricing"):
            await fetch_upstream_pricing(
                base_url="https://openai.example.com/v1",
                credential=_credential(),
                protocol=Protocol.OPENAI,
                client=client,
            )


@pytest.mark.asyncio
async def test_fetch_upstream_pricing_raises_on_non_json_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>nope</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelPriceError, match="not valid JSON"):
            await fetch_upstream_pricing(
                base_url="https://newapi.example.com",
                credential=_credential(),
                protocol=Protocol.OPENAI,
                client=client,
            )


@pytest.mark.asyncio
async def test_fetch_upstream_pricing_propagates_upstream_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_upstream_pricing(
                base_url="https://newapi.example.com",
                credential=_credential(),
                protocol=Protocol.OPENAI,
                client=client,
            )
