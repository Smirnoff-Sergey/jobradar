from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.deps import SessionDep, SettingsDep
from app.services.metrics import render_metrics

# Вне /api/v1 и без авторизации: так его опрашивает Prometheus. nginx наружу его не отдаёт.
router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(session: SessionDep, settings: SettingsDep) -> Response:
    return Response(await render_metrics(session, settings.llm), media_type=CONTENT_TYPE_LATEST)
