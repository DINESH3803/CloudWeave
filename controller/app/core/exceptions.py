"""Controller exceptions and their mapping to HTTP responses."""
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.exceptions import (
    ChecksumMismatchError,
    ChunkNotFoundError,
    CloudWeaveError,
    ConflictError,
    InvalidRequestError,
    NoHealthyWorkersError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    WorkerNotFoundError,
    WorkerUnavailableError,
)

logger = logging.getLogger(__name__)

__all__ = ["CloudWeaveError", "install_exception_handlers"]

_STATUS_BY_EXCEPTION: dict[type[Exception], int] = {
    ObjectNotFoundError: 404,
    ChunkNotFoundError: 404,
    WorkerNotFoundError: 404,
    InvalidRequestError: 400,
    ConflictError: 409,
    NoHealthyWorkersError: 503,
    WorkerUnavailableError: 503,
    ChecksumMismatchError: 500,
    ObjectIntegrityError: 500,
}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CloudWeaveError)
    async def _cloudweave_error(_: Request, exc: CloudWeaveError) -> JSONResponse:
        status = _STATUS_BY_EXCEPTION.get(type(exc), 500)
        msg = str(exc) or type(exc).__name__
        if isinstance(exc, ObjectNotFoundError) and not msg.startswith("Object "):
            msg = f"Object {msg} not found" if msg else "Object not found"
        return JSONResponse(status_code=status, content={"detail": msg})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        messages = []
        for err in exc.errors():
            loc = err.get("loc", ())
            field = str(loc[-1]) if loc else ""
            if field == "offset":
                messages.append("offset must be greater than or equal to 0")
            elif field == "limit":
                messages.append("limit must be between 1 and 1000")
            else:
                msg = err.get("msg", "Invalid value")
                messages.append(f"{field}: {msg}" if field else msg)

        detail = "; ".join(messages) if len(messages) > 1 else (messages[0] if messages else "Invalid request parameters")
        return JSONResponse(status_code=400, content={"detail": detail})

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc) or "Not implemented yet"})

    @app.exception_handler(Exception)
    async def _unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, StarletteHTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
