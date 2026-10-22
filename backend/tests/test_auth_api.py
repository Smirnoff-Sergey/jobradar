from httpx import AsyncClient, Response

from app.core.config import Settings
from app.core.security import create_token
from app.db.models import User
from tests.constants import USER_EMAIL, USER_PASSWORD


async def post_login(
    client: AsyncClient, email: str = USER_EMAIL, password: str = USER_PASSWORD
) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def login(client: AsyncClient, email: str = USER_EMAIL) -> dict[str, str]:
    response = await post_login(client, email=email)
    assert response.status_code == 200, response.text
    tokens: dict[str, str] = response.json()
    return tokens


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_login_returns_token_pair(client: AsyncClient, user: User) -> None:
    tokens = await login(client)

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]


async def test_login_normalizes_email(client: AsyncClient, user: User) -> None:
    await login(client, email="  Owner@Example.COM ")


async def test_login_with_wrong_password(client: AsyncClient, user: User) -> None:
    response = await post_login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_with_unknown_email_looks_the_same(client: AsyncClient, user: User) -> None:
    response = await post_login(client, email="nobody@example.com")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_for_inactive_user(client: AsyncClient, user: User) -> None:
    user.is_active = False

    response = await post_login(client)

    assert response.status_code == 401


async def test_login_validation_error_format(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": "not-an-email"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert {tuple(item["loc"]) for item in error["details"]} == {
        ("body", "email"),
        ("body", "password"),
    }


async def test_validation_error_does_not_echo_input(client: AsyncClient) -> None:
    secret = "x" * 1000

    response = await post_login(client, password=secret)

    assert response.status_code == 422
    assert secret not in response.text
    assert all("input" not in item for item in response.json()["error"]["details"])


async def test_me_returns_current_user(client: AsyncClient, user: User) -> None:
    tokens = await login(client)

    response = await client.get("/api/v1/auth/me", headers=bearer(tokens["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["email"] == USER_EMAIL
    assert "password_hash" not in body


async def test_me_without_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_me_rejects_refresh_token(client: AsyncClient, user: User) -> None:
    tokens = await login(client)

    response = await client.get("/api/v1/auth/me", headers=bearer(tokens["refresh_token"]))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_me_for_deleted_user(client: AsyncClient, settings: Settings) -> None:
    token = create_token(999_999, "access", settings.auth)

    response = await client.get("/api/v1/auth/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_refresh_issues_new_pair(client: AsyncClient, user: User) -> None:
    tokens = await login(client)

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    me = await client.get("/api/v1/auth/me", headers=bearer(new_tokens["access_token"]))
    assert me.status_code == 200


async def test_refresh_rejects_access_token(client: AsyncClient, user: User) -> None:
    tokens = await login(client)

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )

    assert response.status_code == 401
