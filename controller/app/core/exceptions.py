"""
Controller Exception Mapping.

Maps internal domain exceptions to appropriate HTTP status codes and JSON responses
according to the project specification (200, 201, 204, 400, 404, 409, 500, 503).
"""
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

# Mapping from domain exception classes to HTTP status codes
_STATUS_BY_EXCEPTION: dict[type[Exception], int] = {
    ObjectNotFoundError: 404,       # Requested object ID not found in metadata
    ChunkNotFoundError: 404,        # Requested chunk ID not found
    WorkerNotFoundError: 404,       # Worker ID not registered
    InvalidRequestError: 400,       # Bad input or malformed request parameters
    ConflictError: 409,             # Concurrent write or state conflict
    NoHealthyWorkersError: 503,     # Not enough active workers available for placement
    WorkerUnavailableError: 503,    # Worker node is dead or unreachable
    ChecksumMismatchError: 500,     # Data integrity corruption detected
}


def install_exception_handlers(app: FastAPI) -> None:
    """
    Register global exception handlers on the FastAPI app.
    
    Catches CloudWeave domain errors and validation errors, converting them into
    clean JSON error payloads with correct HTTP status codes.
    """
    @app.exception_handler(CloudWeaveError)
    async def _cloudweave_error(_: Request, exc: CloudWeaveError) -> JSONResponse:
        # Resolve status code from map, defaulting to 500 for unmapped errors
        status = _STATUS_BY_EXCEPTION.get(type(exc), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc) or type(exc).__name__})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Return 400 Bad Request on invalid request schemas/parameters
        return JSONResponse(status_code=400, content={"detail": str(exc.errors())})

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        # Return 501 Not Implemented
        return JSONResponse(status_code=501, content={"detail": str(exc) or "Not implemented yet"})
