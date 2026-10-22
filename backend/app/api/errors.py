import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    AppError,
    ConflictError,
    ExternalServiceError,
    InvalidPasswordError,
    NotFoundError,
    UnauthorizedError,
)
from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES = {
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
}

# Порядок важен: берётся первый класс, к которому относится ошибка.
_APP_ERROR_STATUSES: tuple[tuple[type[AppError], int], ...] = (
    (UnauthorizedError, status.HTTP_401_UNAUTHORIZED),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (InvalidPasswordError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (ExternalServiceError, status.HTTP_502_BAD_GATEWAY),
)
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}

# Поля ошибки валидации, которые не отдаём клиенту: в input может оказаться пароль.
_HIDDEN_VALIDATION_FIELDS = frozenset({"input", "ctx", "url"})


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers=headers,
    )


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    status_code = next(
        (code for error_type, code in _APP_ERROR_STATUSES if isinstance(exc, error_type)),
        status.HTTP_400_BAD_REQUEST,
    )
    headers = _UNAUTHORIZED_HEADERS if isinstance(exc, UnauthorizedError) else None
    return error_response(status_code, exc.code, exc.message, headers=headers)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {key: value for key, value in error.items() if key not in _HIDDEN_VALIDATION_FIELDS}
        for error in exc.errors()
    ]
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Некорректные данные запроса",
        details=jsonable_encoder(details),
    )


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_ERROR_CODES.get(exc.status_code, f"http_{exc.status_code}")
    return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Необработанная ошибка: %s %s", request.method, request.url.path)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Внутренняя ошибка сервера",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
