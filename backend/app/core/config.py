from functools import lru_cache

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32
CRON_FIELDS = 5


class DatabaseSettings(BaseSettings):
    """Настройки подключения к БД. Отдельно от остальных, чтобы миграциям не нужны были секреты."""

    model_config = SettingsConfigDict(
        env_prefix="JOBRADAR_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://jobradar:jobradar@localhost:5432/jobradar"


class AuthSettings(BaseModel):
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def _check_secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"секрет JWT должен быть не короче {MIN_JWT_SECRET_LENGTH} символов")
        return value


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"


class CollectorSettings(BaseModel):
    # Cron-выражение (минута, час, день месяца, месяц, день недели). Cron, а не интервал:
    # интервал beat отсчитывает от своего старта, и после перезапуска сбор откладывается.
    schedule_cron: str = "0 * * * *"
    request_timeout_seconds: float = 30.0
    http_max_attempts: int = 4
    http_backoff_seconds: float = 1.0
    # Больше 20 не ставить: страницы на 100 вакансий getmatch отдаёт по 2+ минуты и обрывает.
    getmatch_page_size: int = 20
    # Не чаще стольких запросов карточек вакансий на воркер (формат Celery: "30/m").
    details_rate_limit: str = "30/m"

    @field_validator("schedule_cron")
    @classmethod
    def _check_cron(cls, value: str) -> str:
        if len(value.split()) != CRON_FIELDS:
            raise ValueError(f"в cron-выражении должно быть {CRON_FIELDS} полей: {value!r}")
        return value


class Settings(DatabaseSettings):
    """Вложенные блоки задаются через `__`: JOBRADAR_AUTH__JWT_SECRET, JOBRADAR_REDIS__URL."""

    auth: AuthSettings
    redis: RedisSettings = RedisSettings()
    collector: CollectorSettings = CollectorSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # обязательные поля приходят из окружения
