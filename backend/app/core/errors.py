"""Ошибки предметной области. Обработчики в app/api/errors.py превращают их в HTTP-ответы."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Некорректный запрос"
    headers: dict[str, str] | None = None

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class UnauthorizedError(AppError):
    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012  # не изменяется


class NotAuthenticatedError(UnauthorizedError):
    code = "not_authenticated"
    message = "Требуется авторизация"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message = "Неверный email или пароль"


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"
    message = "Некорректный токен"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Конфликт с существующими данными"


class InvalidPasswordError(AppError):
    status_code = 422
    code = "invalid_password"
    message = "Пароль не подходит по требованиям"
