from ai_gateway.core.enums import ModelType
from ai_gateway.gateway.models import SelectableModel, _openai_model


def test_openai_model_response_exposes_optional_model_capabilities() -> None:
    response = _openai_model(
        SelectableModel(
            selectable_id="multimodal-model",
            canonical_name="multimodal-model",
            display_name="Multimodal Model",
            model_types=[ModelType.TEXT, ModelType.IMAGE],
            model_type=ModelType.TEXT,
        )
    )

    assert response == {
        "id": "multimodal-model",
        "object": "model",
        "owned_by": "gateway",
        "metadata": {},
        "model_types": ["text", "image"],
        "model_type": "text",
    }
