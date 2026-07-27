from ai_gateway.catalog.schemas import ProviderProtocolInput
from ai_gateway.core.enums import Protocol


def test_openai_protocol_defaults_to_native_responses_support() -> None:
    protocol = ProviderProtocolInput(
        protocol=Protocol.OPENAI,
        base_url="https://api.openai.com/v1",
    )

    assert protocol.supports_responses is True


def test_openai_protocol_accepts_explicit_responses_fallback() -> None:
    protocol = ProviderProtocolInput(
        protocol=Protocol.OPENAI,
        base_url="https://legacy-openai.example/v1",
        supports_responses=False,
    )

    assert protocol.supports_responses is False
