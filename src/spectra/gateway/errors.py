import logging
from collections.abc import Callable, Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

from spectra.analysis.domain.errors import UnsupportedFormatError
from spectra.gateway.schemas import ErrorBody
from spectra.tracks.domain.errors import (
    EmptyUploadError,
    FileTooLargeError,
    InvalidTrackIdError,
    TrackNotFoundError,
)
from spectra.tracks.domain.track import FailureCode

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    NO_FILE = "no_file"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_FORMAT = "unsupported_format"
    UNDECODABLE = "undecodable"
    ANALYSIS_FAILED = "analysis_failed"
    TRACK_NOT_FOUND = "track_not_found"
    NOT_READY = "not_ready"
    INTERNAL = "internal"


STATUSES: Final[Mapping[ErrorCode, HTTPStatus]] = {
    ErrorCode.NO_FILE: HTTPStatus.BAD_REQUEST,
    ErrorCode.FILE_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.UNSUPPORTED_FORMAT: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.UNDECODABLE: HTTPStatus.UNPROCESSABLE_CONTENT,
    ErrorCode.ANALYSIS_FAILED: HTTPStatus.UNPROCESSABLE_CONTENT,
    ErrorCode.TRACK_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.NOT_READY: HTTPStatus.CONFLICT,
    ErrorCode.INTERNAL: HTTPStatus.INTERNAL_SERVER_ERROR,
}
FAILURE_CODES: Final[Mapping[FailureCode, ErrorCode]] = {
    FailureCode.UNDECODABLE: ErrorCode.UNDECODABLE,
    FailureCode.ANALYSIS_FAILED: ErrorCode.ANALYSIS_FAILED,
    FailureCode.INTERNAL: ErrorCode.INTERNAL,
}
DOMAIN_ERRORS: Final[Mapping[type[Exception], ErrorCode]] = {
    EmptyUploadError: ErrorCode.NO_FILE,
    FileTooLargeError: ErrorCode.FILE_TOO_LARGE,
    UnsupportedFormatError: ErrorCode.UNSUPPORTED_FORMAT,
    TrackNotFoundError: ErrorCode.TRACK_NOT_FOUND,
    InvalidTrackIdError: ErrorCode.TRACK_NOT_FOUND,
}


class GatewayError(Exception):
    pass


class GatewayNotConfiguredError(GatewayError):
    pass


class ApiError(GatewayError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_response(code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorBody(error=code.value, message=message)
    return JSONResponse(status_code=STATUSES[code], content=body.model_dump())


async def handle_api_error(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, ApiError):
        return await handle_unexpected_error(_request, error)
    return error_response(error.code, error.message)


async def handle_unexpected_error(_request: Request, error: Exception) -> JSONResponse:
    logger.error("unhandled error in the gateway", exc_info=error)
    return error_response(ErrorCode.INTERNAL, "internal server error")


async def handle_unreadable_request(_request: Request, _error: Exception) -> JSONResponse:
    return error_response(ErrorCode.NO_FILE, "the request has no readable file part")


async def handle_http_error(request: Request, error: Exception) -> Response:
    if isinstance(error, HTTPException) and error.status_code == HTTPStatus.BAD_REQUEST:
        return error_response(ErrorCode.NO_FILE, str(error.detail))
    if not isinstance(error, HTTPException):
        return await handle_unexpected_error(request, error)
    return await http_exception_handler(request, error)


def domain_handler(code: ErrorCode) -> Callable[[Request, Exception], JSONResponse]:
    def handle(_request: Request, error: Exception) -> JSONResponse:
        return error_response(code, str(error))

    return handle


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_unreadable_request)
    app.add_exception_handler(HTTPException, handle_http_error)
    for error_type, code in DOMAIN_ERRORS.items():
        app.add_exception_handler(error_type, domain_handler(code))
    app.add_exception_handler(Exception, handle_unexpected_error)
