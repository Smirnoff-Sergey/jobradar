from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32


class DatabaseSettings(BaseSettings):
    """Настройки подключения к БД. Отдельно от остальных, чтобы миграциям не нужны были секреты."""

    model_config = SettingsConfigDict(env_prefix="JOBRADAR_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://jobradar:jobradar@localhost:5432/jobradar"


class Settings(DatabaseSettings):
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # обязательные поля приходят из окружения
