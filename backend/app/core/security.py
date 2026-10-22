from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import InvalidTokenError

TokenType = Literal["access", "refresh"]

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 256

_password_hash = PasswordHash.recommended()


# Argon2 намеренно медленный и занимает CPU: из async-кода вызывать через asyncio.to_thread.
def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


# Хеш для проверки пароля несуществующего пользователя: время ответа не должно выдавать,
# зарегистрирован ли email. Считается при импорте, чтобы первый запрос не был медленнее.
DUMMY_PASSWORD_HASH = hash_password(uuid4().hex)


def create_token(
    user_id: int,
    token_type: TokenType,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    if token_type == "access":
        ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    else:
        ttl = timedelta(days=settings.refresh_token_ttl_days)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "jti": uuid4().hex,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, expected_type: TokenType, settings: Settings) -> int:
    """Проверяет подпись, срок и тип токена. Возвращает id пользователя."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Срок действия токена истёк") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError from exc

    if payload["type"] != expected_type:
        raise InvalidTokenError("Неверный тип токена")
    try:
        return int(payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError from exc
