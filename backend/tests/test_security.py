from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import AuthSettings, Settings
from app.core.errors import InvalidTokenError
from app.core.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    password_hash = hash_password("s3cret-password")

    assert password_hash != "s3cret-password"
    assert verify_password("s3cret-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_token_roundtrip(settings: Settings) -> None:
    token = create_token(42, "access", settings.auth)

    assert decode_token(token, "access", settings.auth) == 42


def test_token_type_is_checked(settings: Settings) -> None:
    refresh = create_token(42, "refresh", settings.auth)

    with pytest.raises(InvalidTokenError, match="тип"):
        decode_token(refresh, "access", settings.auth)


def test_expired_token_is_rejected(settings: Settings) -> None:
    long_ago = datetime.now(UTC) - timedelta(days=365)
    token = create_token(42, "access", settings.auth, now=long_ago)

    with pytest.raises(InvalidTokenError, match="истёк"):
        decode_token(token, "access", settings.auth)


def test_token_with_foreign_signature_is_rejected(settings: Settings) -> None:
    now = datetime.now(UTC)
    payload = {"sub": "42", "type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    forged = jwt.encode(payload, "another-secret-" + "y" * 40, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_token(forged, "access", settings.auth)


def test_garbage_token_is_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-jwt", "access", settings.auth)


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="секрет JWT"):
        AuthSettings(jwt_secret="short")
