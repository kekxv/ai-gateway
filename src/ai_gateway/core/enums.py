from enum import StrEnum


class Protocol(StrEnum):
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"


class ModelType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    TEXT_TO_IMAGE = "text_to_image"
    AUDIO = "audio"
    VIDEO = "video"
    EMBEDDING = "embedding"


class ApiKeyScope(StrEnum):
    ALL = "all"
    PROVIDERS = "providers"
    MODELS = "models"
    PROVIDERS_AND_MODELS = "providers_and_models"


class RouteRuntimeState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RouteSource(StrEnum):
    MANUAL = "manual"
    DISCOVERED = "discovered"


class LedgerKind(StrEnum):
    RESERVATION = "reservation"
    RESERVATION_RELEASE = "reservation_release"
    USAGE = "usage"
    ADJUSTMENT = "adjustment"


class RequestStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CLIENT_DISCONNECTED = "client_disconnected"


class UsageSource(StrEnum):
    PROVIDER = "provider"
    ESTIMATED = "estimated"


def enum_values[EnumType: StrEnum](enum_type: type[EnumType]) -> list[str]:
    return [member.value for member in enum_type]
