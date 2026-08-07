class EcoTwinBaseException(Exception):
    """Base exception for all EcoTwin domain errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "An unexpected error occurred") -> None:
        self.message = message
        super().__init__(message)


class NotFoundException(EcoTwinBaseException):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} not found: {identifier}")


class UnauthorizedException(EcoTwinBaseException):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenException(EcoTwinBaseException):
    status_code = 403
    code = "FORBIDDEN"


class ValidationException(EcoTwinBaseException):
    status_code = 422
    code = "VALIDATION_ERROR"


class ConflictException(EcoTwinBaseException):
    status_code = 409
    code = "CONFLICT"


class ServiceUnavailableException(EcoTwinBaseException):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class RegionNotFoundException(NotFoundException):
    def __init__(self, identifier: str) -> None:
        super().__init__("Region", identifier)


class LakeNotFoundException(NotFoundException):
    def __init__(self, identifier: str) -> None:
        super().__init__("Lake", identifier)


class EmbeddingNotFoundException(NotFoundException):
    def __init__(self, identifier: str) -> None:
        super().__init__("Embedding", identifier)
