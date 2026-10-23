from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.evaluation import EvaluationStatus
from app.domain.letters import LetterFact


class LetterRead(BaseModel):
    """Черновик письма. facts — утверждения письма с цитатами из резюме, которые их подтверждают."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: EvaluationStatus
    text: str | None
    facts: list[LetterFact] | None
    model: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class LetterAccepted(BaseModel):
    task_id: str
    letter_id: int
