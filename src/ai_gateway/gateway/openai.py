from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ai_gateway.core.enums import Protocol
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.service import GatewayService, OpenAIOperation, native_error_response

router = APIRouter()


async def _native_openai_operation(
    request: Request,
    service: GatewayService,
    *,
    endpoint_path: str,
    openai_operation: OpenAIOperation,
) -> Response:
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path=endpoint_path,
                openai_operation=openai_operation,
                required_protocol=Protocol.OPENAI,
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/chat/completions",
                openai_operation="chat_completions",
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/responses")
async def responses(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    """OpenAI Responses API - unified interface for chat completions and other features."""
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/responses",
                openai_operation="responses",
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    """OpenAI Embeddings API - generate text embeddings."""
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/embeddings",
                openai_operation="embeddings",
                required_protocol=Protocol.OPENAI,
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/completions")
async def completions(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    """OpenAI Completions API (Legacy) - text completions."""
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/completions",
                openai_operation="completions",
                required_protocol=Protocol.OPENAI,
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/audio/speech")
async def audio_speech(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    return await _native_openai_operation(
        request,
        service,
        endpoint_path="/v1/audio/speech",
        openai_operation="audio_speech",
    )


@router.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    return await _native_openai_operation(
        request,
        service,
        endpoint_path="/v1/audio/transcriptions",
        openai_operation="audio_transcriptions",
    )


@router.post("/v1/audio/translations")
async def audio_translations(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    return await _native_openai_operation(
        request,
        service,
        endpoint_path="/v1/audio/translations",
        openai_operation="audio_translations",
    )


@router.post("/v1/images/generations")
async def image_generations(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    return await _native_openai_operation(
        request,
        service,
        endpoint_path="/v1/images/generations",
        openai_operation="images_generations",
    )


@router.post("/v1/images/edits")
async def image_edits(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    return await _native_openai_operation(
        request,
        service,
        endpoint_path="/v1/images/edits",
        openai_operation="images_edits",
    )


@router.post("/v1/images/variations")
async def image_variations(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    return await _native_openai_operation(
        request,
        service,
        endpoint_path="/v1/images/variations",
        openai_operation="images_variations",
    )
