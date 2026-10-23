import logging
import re
import time
import uuid

import structlog
from fastapi import Depends, FastAPI, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import HTTP_REQUEST_DURATION

logger = logging.getLogger("app.http")

REQUEST_ID_HEADER = "X-Request-ID"
# Чужой request_id принимаем, только если он похож на идентификатор: он попадёт в логи.
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Сюда зависимость маршрута кладёт шаблон пути. Вложенные роутеры FastAPI работают с копией
# scope, но копия поверхностная: общий словарь виден и middleware.
_ROUTE_KEY = "jobradar.route"
UNMATCHED = "unmatched"
# Метод в метке — из короткого списка: иначе запросы с выдуманным методом плодили бы метки.
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def route_template(path: str, path_params: dict[str, object]) -> str:
    """/api/v1/vacancies/12345 и {vacancy_id: 12345} → /api/v1/vacancies/{vacancy_id}."""
    names = {str(value): name for name, value in path_params.items()}
    return "/".join(f"{{{names[part]}}}" if part in names else part for part in path.split("/"))


def remember_route(request: Request) -> None:
    """Зависимость всех маршрутов: сообщает middleware шаблон найденного пути."""
    holder = request.scope.get(_ROUTE_KEY)
    if isinstance(holder, dict):
        holder["route"] = route_template(request.url.path, request.path_params)


class RequestContextMiddleware:
    """request_id в логах и заголовке ответа, время ответа в метриках.

    Метка маршрута — шаблон пути (из remember_route), а не сам путь: иначе метрик
    было бы столько же, сколько вакансий.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        incoming = next(
            (
                value.decode("latin-1")
                for name, value in scope["headers"]
                if name == REQUEST_ID_HEADER.lower().encode()
            ),
            "",
        )
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_code = 500
        holder: dict[str, str] = {}
        scope[_ROUTE_KEY] = holder

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_id)
        finally:
            elapsed = time.perf_counter() - started
            route = holder.get("route", UNMATCHED)
            method = scope["method"] if scope["method"] in _METHODS else "OTHER"
            HTTP_REQUEST_DURATION.labels(method, route, str(status_code)).observe(elapsed)
            if route != "/metrics":  # Prometheus опрашивает часто — не засоряем журнал
                logger.info(
                    "%s %s → %d за %.0f мс",
                    scope["method"],
                    scope["path"],
                    status_code,
                    elapsed * 1000,
                )
            structlog.contextvars.unbind_contextvars("request_id")


def register_request_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
    app.router.dependencies.append(Depends(remember_route))
