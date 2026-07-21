import pytest

from ai_gateway.auth.api_key import ApiKeyPrincipal, authorize_scope
from ai_gateway.core.enums import ApiKeyScope


@pytest.mark.parametrize(
    ("scope", "model_id", "provider_id", "expected"),
    [
        (ApiKeyScope.ALL, 999, 888, True),
        (ApiKeyScope.PROVIDERS, 999, 20, True),
        (ApiKeyScope.PROVIDERS, 10, 999, False),
        (ApiKeyScope.MODELS, 10, 999, True),
        (ApiKeyScope.MODELS, 999, 20, False),
        (ApiKeyScope.PROVIDERS_AND_MODELS, 10, 20, True),
        (ApiKeyScope.PROVIDERS_AND_MODELS, 10, 999, False),
        (ApiKeyScope.PROVIDERS_AND_MODELS, 999, 20, False),
    ],
)
def test_authorize_scope_semantics(
    scope: ApiKeyScope,
    model_id: int,
    provider_id: int,
    expected: bool,
) -> None:
    principal = ApiKeyPrincipal(
        api_key_id=1,
        user_id=2,
        scope=scope,
        model_ids=frozenset({10}),
        provider_ids=frozenset({20}),
    )

    assert authorize_scope(principal, model_id=model_id, provider_id=provider_id) is expected
