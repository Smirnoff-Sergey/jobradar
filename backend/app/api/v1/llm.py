from fastapi import APIRouter

from app.api.deps import CurrentUserDep, EvaluationSchedulerDep
from app.schemas.llm import LLMUsageRead

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/usage")
async def get_usage(_: CurrentUserDep, scheduler: EvaluationSchedulerDep) -> LLMUsageRead:
    """Расход дневного лимита запросов к LLM (сутки по UTC) и аварийная остановка."""
    return LLMUsageRead.model_validate(await scheduler.budget.usage())
