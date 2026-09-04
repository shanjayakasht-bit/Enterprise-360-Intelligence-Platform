"""Domain exceptions and their FastAPI handlers -- every error response has
the same shape ({"error": "<code>", "message": "<safe, human text>"}), and
no handler ever forwards a raw Snowflake exception message or traceback to
the client (those are logged server-side only, via backend.core.logging).
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from backend.core.logging import get_logger

logger = get_logger("exceptions")


class NexoraAPIError(Exception):
    """Base class for every error this API raises deliberately."""

    error_code = "internal_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message):
        self.message = message
        super().__init__(message)


class ResourceNotFoundError(NexoraAPIError):
    error_code = "resource_not_found"
    status_code = status.HTTP_404_NOT_FOUND


class InvalidFilterError(NexoraAPIError):
    error_code = "invalid_filter"
    status_code = status.HTTP_400_BAD_REQUEST


class DatabaseError(NexoraAPIError):
    error_code = "database_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


def _error_body(code, message):
    return {"error": code, "message": message}


async def nexora_error_handler(request: Request, exc: NexoraAPIError):
    if exc.status_code >= 500:
        logger.error("%s %s -> %s: %s", request.method, request.url.path, exc.error_code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=_error_body(exc.error_code, exc.message))


async def unhandled_error_handler(request: Request, exc: Exception):
    # Never forward the raw exception (could contain a Snowflake stack
    # trace, a SQL fragment, or connection details) to the client -- log it
    # server-side, return a generic, safe message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("internal_error", "An unexpected error occurred. Please try again later."),
    )


def register_exception_handlers(app):
    app.add_exception_handler(NexoraAPIError, nexora_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
