import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.catalog.repository import CatalogRepository, ModelNotFound
from ai_gateway.db.models import Model, ModelAlias


@pytest_asyncio.fixture
async def catalog(session: AsyncSession) -> CatalogRepository:
    model = Model(
        id=41,
        canonical_name="gpt-4.1-mini",
        display_name="GPT 4.1 Mini",
        enabled=True,
    )
    model.aliases = [ModelAlias(alias="fast-chat", enabled=True)]
    session.add(model)
    await session.flush()
    return CatalogRepository(session)


@pytest.mark.parametrize("requested", ["gpt-4.1-mini", "fast-chat"])
async def test_canonical_name_and_alias_resolve_to_same_model(
    catalog: CatalogRepository,
    requested: str,
) -> None:
    resolved = await catalog.resolve_model(requested)

    assert resolved.model_id == 41
    assert resolved.canonical_name == "gpt-4.1-mini"
    assert resolved.requested_name == requested


async def test_disabled_models_and_aliases_do_not_resolve(
    session: AsyncSession,
) -> None:
    disabled_model = Model(
        canonical_name="disabled-model",
        display_name="Disabled Model",
        enabled=False,
    )
    enabled_model = Model(
        canonical_name="enabled-model",
        display_name="Enabled Model",
        enabled=True,
        aliases=[ModelAlias(alias="disabled-alias", enabled=False)],
    )
    session.add_all([disabled_model, enabled_model])
    await session.flush()
    catalog = CatalogRepository(session)

    for name in ("disabled-model", "disabled-alias"):
        with pytest.raises(ModelNotFound) as error:
            await catalog.resolve_model(name)
        assert error.value.requested_name == name
