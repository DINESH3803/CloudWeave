"""Controller exceptions and their mapping to HTTP responses."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from shared.exceptions import (
    ChecksumMismatchError,
    ChunkNotFoundError,
    CloudWeaveError,
    ConflictError,
    InvalidRequestError,
    NoHealthyWorkersError,
    ObjectNotFoundError,
    WorkerNotFoundError,
    WorkerUnavailableError,
)

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
}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CloudWeaveError)
    async def _cloudweave_error(_: Request, exc: CloudWeaveError) -> JSONResponse:
        status = _STATUS_BY_EXCEPTION.get(type(exc), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc) or type(exc).__name__})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc.errors())})

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc) or "Not implemented yet"})
