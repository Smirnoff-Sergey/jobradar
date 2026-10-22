import pytest

from app.core.errors import ConflictError, InvalidPasswordError
from app.core.security import PASSWORD_MAX_LENGTH, verify_password
from app.db.models import User
from app.services.auth import AuthService
from tests.constants import USER_EMAIL


async def test_create_user_normalizes_email_and_hashes_password(
    auth_service: AuthService,
) -> None:
    user = await auth_service.create_user(" New@Example.com ", "long-password")

    assert user.id is not None
    assert user.email == "new@example.com"
    assert user.is_active
    assert verify_password("long-password", user.password_hash)


async def test_create_user_rejects_duplicate_email(auth_service: AuthService, user: User) -> None:
    with pytest.raises(ConflictError):
        await auth_service.create_user(USER_EMAIL.upper(), "another-password")


async def test_session_is_usable_after_duplicate(auth_service: AuthService, user: User) -> None:
    with pytest.raises(ConflictError):
        await auth_service.create_user(USER_EMAIL, "another-password")

    other = await auth_service.create_user("other@example.com", "another-password")

    assert other.id is not None


@pytest.mark.parametrize("password", ["1234567", "x" * (PASSWORD_MAX_LENGTH + 1)])
async def test_create_user_rejects_password_length(
    auth_service: AuthService, password: str
) -> None:
    with pytest.raises(InvalidPasswordError):
        await auth_service.create_user("short@example.com", password)
