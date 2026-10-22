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


FREE_MODEL_SUFFIX = ":free"


def is_free_model(model: str) -> bool:
    return model.endswith(FREE_MODEL_SUFFIX)


class LLMSettings(BaseModel):
    """LLM через OpenAI-совместимый API (по умолчанию OpenRouter). Только бесплатные модели."""

    base_url: str = "https://openrouter.ai/api/v1"
    # Без ключа оценка вакансий выключена, остальной сервис работает.
    api_key: SecretStr | None = None
    # Порядок важен: если модель недоступна, OpenRouter переходит к следующей.
    # В переменной окружения — JSON-массив: JOBRADAR_LLM__MODELS='["a:free", "b:free"]'.
    models: list[str] = [
        "xingchen-agi/xing4.0-29b-a4b:free",
        "google/gemma-4-31b-it:free",
        "dots-studio/dots-3-note-preview:free",
    ]
    # Бесплатный тариф OpenRouter — 50 запросов в сутки (UTC); остаток — на scripts/eval.py.
    daily_request_limit: int = 35
    request_timeout_seconds: float = 120.0
    rate_limit: str = "10/m"
    max_description_chars: int = 12_000
    # Просить OpenRouter не направлять запросы провайдерам, которые сохраняют и обучаются
    # на данных: в запросе — текст резюме. Проверено: бесплатные модели остаются доступны.
    deny_data_collection: bool = True

    @property
    def enabled(self) -> bool:
        return self.api_key is not None

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value: object) -> object:
        # «JOBRADAR_LLM__API_KEY=» в .env означает «ключа нет», а не ключ из пустой строки.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("models")
    @classmethod
    def _only_free_models(cls, value: list[str]) -> list[str]:
        # Политика проекта: платные модели запрещены. Проверка здесь не даёт даже запуститься
        # с ошибкой в конфиге; клиент дополнительно проверяет стоимость каждого ответа.
        if not value:
            raise ValueError("нужна хотя бы одна модель")
        if paid := [model for model in value if not is_free_model(model)]:
            raise ValueError(f"разрешены только бесплатные модели ({FREE_MODEL_SUFFIX}): {paid}")
        return value


class Settings(DatabaseSettings):
    """Вложенные блоки задаются через `__`: JOBRADAR_AUTH__JWT_SECRET, JOBRADAR_REDIS__URL."""

    auth: AuthSettings
    redis: RedisSettings = RedisSettings()
    collector: CollectorSettings = CollectorSettings()
    llm: LLMSettings = LLMSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # обязательные поля приходят из окружения
