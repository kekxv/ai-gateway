from ai_gateway.core.enums import Protocol
from ai_gateway.gateway.service import upstream_url


def test_systemone_upstream_url_uses_v1_systemone() -> None:
    assert upstream_url(Protocol.SYSTEMONE, "https://api.typesafe.ai", "jev-latest") == (
        "https://api.typesafe.ai/v1/systemone"
    )
