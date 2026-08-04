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


async def test_shared_alias_resolves_every_enabled_target_in_model_id_order(
    session: AsyncSession,
) -> None:
    models = [
        Model(
            id=44,
            canonical_name="shared-disabled-model",
            display_name="Shared Disabled Model",
            enabled=False,
            aliases=[ModelAlias(alias="shared-chat", enabled=True)],
        ),
        Model(
            id=43,
            canonical_name="shared-model-b",
            display_name="Shared Model B",
            enabled=True,
            aliases=[ModelAlias(alias="shared-chat", enabled=True)],
        ),
        Model(
            id=42,
            canonical_name="shared-model-a",
            display_name="Shared Model A",
            enabled=True,
            aliases=[ModelAlias(alias="shared-chat", enabled=True)],
        ),
        Model(
            id=45,
            canonical_name="shared-disabled-alias",
            display_name="Shared Disabled Alias",
            enabled=True,
            aliases=[ModelAlias(alias="shared-chat", enabled=False)],
        ),
    ]
    session.add_all(models)
    await session.flush()

    resolved = await CatalogRepository(session).resolve_model("shared-chat")

    assert resolved.model_id == 42
    assert resolved.model_ids == (42, 43)
    assert resolved.requested_name == "shared-chat"
    assert resolved.canonical_name is None


async def test_canonical_name_and_matching_aliases_resolve_to_one_weighted_pool(
    session: AsyncSession,
) -> None:
    canonical = Model(
        id=46,
        canonical_name="canonical-first",
        display_name="Canonical First",
        enabled=True,
    )
    alias_target = Model(
        id=47,
        canonical_name="alias-target",
        display_name="Alias Target",
        enabled=True,
        aliases=[ModelAlias(alias="canonical-first", enabled=True)],
    )
    session.add_all([canonical, alias_target])
    await session.flush()

    resolved = await CatalogRepository(session).resolve_model("canonical-first")

    assert resolved.model_id == canonical.id
    assert resolved.model_ids == (canonical.id, alias_target.id)
    assert resolved.canonical_name is None
