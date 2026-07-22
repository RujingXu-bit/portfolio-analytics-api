from fastapi import APIRouter, status

from portfolio_analytics_api.api.schemas import (
    AccessTokenResponse,
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from portfolio_analytics_api.application import AuthenticationService


def build_auth_router(authentication_service: AuthenticationService) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])

    @router.post(
        "/register",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def register(request: RegisterRequest) -> UserResponse:
        user = await authentication_service.register(
            email=request.email,
            password=request.password.get_secret_value(),
        )
        return UserResponse.model_validate(user)

    @router.post(
        "/login",
        response_model=AccessTokenResponse,
        responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def login(request: LoginRequest) -> AccessTokenResponse:
        token = await authentication_service.login(
            email=request.email,
            password=request.password.get_secret_value(),
        )
        return AccessTokenResponse(
            access_token=token.value,
            expires_in=token.expires_in_seconds,
        )

    return router
