from fastapi import APIRouter

from app.api.deps import AuthServiceDep, CurrentUserDep
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPairRead
from app.schemas.common import ErrorResponse
from app.schemas.user import UserRead

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"model": ErrorResponse}},
)


@router.post("/login")
async def login(body: LoginRequest, auth: AuthServiceDep) -> TokenPairRead:
    return TokenPairRead.model_validate(await auth.authenticate(body.email, body.password))


@router.post("/refresh")
async def refresh(body: RefreshRequest, auth: AuthServiceDep) -> TokenPairRead:
    return TokenPairRead.model_validate(await auth.refresh(body.refresh_token))


@router.get("/me")
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)
