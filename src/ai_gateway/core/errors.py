class GatewayError(Exception):
    """Base exception for errors that can be exposed by the gateway API."""

    code = "gateway_error"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
