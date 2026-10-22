"""Ошибки предметной области.

HTTP-статусы здесь не задаются: соответствие «ошибка → статус» живёт в app/api/errors.py,
а сервисы и фоновые задачи не зависят от транспорта.
"""


class AppError(Exception):
    code = "bad_request"
    message = "Некорректный запрос"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class UnauthorizedError(AppError):
    pass


class NotAuthenticatedError(UnauthorizedError):
    code = "not_authenticated"
    message = "Требуется авторизация"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message = "Неверный email или пароль"


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"
    message = "Некорректный токен"


class NotFoundError(AppError):
    code = "not_found"
    message = "Не найдено"


class ConflictError(AppError):
    code = "conflict"
    message = "Конфликт с существующими данными"


class InvalidPasswordError(AppError):
    code = "invalid_password"
    message = "Пароль не подходит по требованиям"


class ExternalServiceError(AppError):
    """Сбой внешнего сервиса. `retryable` говорит, есть ли смысл повторять запрос."""

    code = "external_service_error"
    message = "Внешний сервис недоступен"
    retryable = False


class TransientExternalError(ExternalServiceError):
    """Временный сбой: таймаут, обрыв соединения, 429, 5xx."""

    retryable = True

    def __init__(self, message: str | None = None, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentExternalError(ExternalServiceError):
    """Повтор не поможет: 4xx (кроме 429), некорректный ответ."""


class ExternalAccessError(ExternalServiceError):
    """401/403: внешний сервис не пускает нас вообще (ключ, регион, блокировка).

    Это не проблема конкретного запроса — данные не помечаются как неудачные,
    их обработают, когда доступ восстановят.
    """

    code = "external_access_denied"
    message = "Внешний сервис отказал в доступе"


class LLMResponseError(PermanentExternalError):
    """Модель ответила не по схеме или несогласованно."""

    code = "llm_response_error"
    message = "Модель вернула некорректный ответ"


class LLMDisabledError(AppError):
    code = "llm_disabled"
    message = "LLM-оценка выключена"


class PaidUsageError(AppError):
    """Запрос к LLM оказался платным. Политика проекта: только бесплатные модели."""

    code = "paid_usage"
    message = "Запрос к LLM оказался платным — оценка остановлена"
