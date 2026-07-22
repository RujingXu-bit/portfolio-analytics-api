from fastapi import APIRouter, Request, status

from portfolio_analytics_api.api.rate_limit import (
    RateLimitPolicies,
    client_ip_identifier,
)
from portfolio_analytics_api.api.schemas import (
    AccessTokenResponse,
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from portfolio_analytics_api.application import AuthenticationService, RateLimiter


def build_auth_router(
    authentication_service: AuthenticationService,
    rate_limiter: RateLimiter | None = None,
    rate_limit_policies: RateLimitPolicies | None = None,
    trust_proxy_headers: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])
    policies = rate_limit_policies or RateLimitPolicies()

    @router.post(
        "/register",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    async def register(request: Request, payload: RegisterRequest) -> UserResponse:
        if rate_limiter is not None:
            await rate_limiter.enforce(
                policies.registration_ip,
                f"ip:{client_ip_identifier(request, trust_proxy_headers)}",
            )
        user = await authentication_service.register(
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
        return UserResponse.model_validate(user)

    @router.post(
        "/login",
        response_model=AccessTokenResponse,
        responses={
            401: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    async def login(request: Request, payload: LoginRequest) -> AccessTokenResponse:
        if rate_limiter is not None:
            await rate_limiter.enforce(
                policies.login_ip,
                f"ip:{client_ip_identifier(request, trust_proxy_headers)}",
            )
            await rate_limiter.enforce(
                policies.login_email,
                f"email:{payload.email}",
            )
        token = await authentication_service.login(
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
        return AccessTokenResponse(
            access_token=token.value,
            expires_in=token.expires_in_seconds,
        )

    return router
