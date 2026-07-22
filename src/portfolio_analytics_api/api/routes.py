from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from portfolio_analytics_api.api.schemas import (
    AnalysisSnapshotPageResponse,
    AnalysisSnapshotResponse,
    CreatePortfolioRequest,
    ErrorResponse,
    PortfolioAnalyticsResponse,
    PortfolioInsightResponse,
    PortfolioPageResponse,
    PortfolioResponse,
    TransactionInput,
    TransactionResponse,
)
from portfolio_analytics_api.application import (
    AuthenticationService,
    InvalidAccessTokenError,
    NewTransaction,
    PortfolioAnalyticsService,
    PortfolioInsightService,
    PortfolioService,
    TransactionService,
)
from portfolio_analytics_api.domain import User


def build_portfolio_router(
    authentication_service: AuthenticationService,
    portfolio_service: PortfolioService,
    transaction_service: TransactionService,
    analytics_service: PortfolioAnalyticsService,
    insight_service: PortfolioInsightService,
) -> APIRouter:
    router = APIRouter(prefix="/portfolios", tags=["portfolios"])
    bearer = HTTPBearer(auto_error=False)

    async def current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> User:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise InvalidAccessTokenError()
        return await authentication_service.authenticate(credentials.credentials)

    @router.post(
        "",
        response_model=PortfolioResponse,
        status_code=status.HTTP_201_CREATED,
        responses={422: {"model": ErrorResponse}},
    )
    async def create_portfolio(
        request: CreatePortfolioRequest,
        user: Annotated[User, Depends(current_user)],
    ) -> PortfolioResponse:
        portfolio = await portfolio_service.create(
            owner_id=user.id,
            name=request.name,
            base_currency=request.base_currency,
        )
        return PortfolioResponse.model_validate(portfolio)

    @router.get(
        "",
        response_model=PortfolioPageResponse,
    )
    async def list_portfolios(
        user: Annotated[User, Depends(current_user)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> PortfolioPageResponse:
        page = await portfolio_service.list(user.id, limit, offset)
        return PortfolioPageResponse(
            items=[
                PortfolioResponse.model_validate(portfolio) for portfolio in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    @router.get(
        "/{portfolio_id}",
        response_model=PortfolioResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_portfolio(
        portfolio_id: UUID,
        user: Annotated[User, Depends(current_user)],
    ) -> PortfolioResponse:
        portfolio = await portfolio_service.get(user.id, portfolio_id)
        return PortfolioResponse.model_validate(portfolio)

    @router.post(
        "/{portfolio_id}/transactions",
        response_model=TransactionResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_transaction(
        portfolio_id: UUID,
        request: TransactionInput,
        response: Response,
        user: Annotated[User, Depends(current_user)],
    ) -> TransactionResponse:
        result = await transaction_service.create(
            user.id,
            portfolio_id,
            NewTransaction(
                external_id=request.external_id,
                transaction_type=request.transaction_type,
                occurred_at=request.occurred_at,
                symbol=request.symbol,
                quantity=request.quantity,
                unit_price=request.unit_price,
                cash_amount=request.cash_amount,
                fees=request.fees,
            ),
        )
        if not result.created:
            response.status_code = status.HTTP_200_OK
        return TransactionResponse.model_validate(result.transaction)

    @router.get(
        "/{portfolio_id}/transactions",
        response_model=list[TransactionResponse],
        responses={404: {"model": ErrorResponse}},
    )
    async def list_transactions(
        portfolio_id: UUID,
        user: Annotated[User, Depends(current_user)],
    ) -> list[TransactionResponse]:
        transactions = await transaction_service.list(user.id, portfolio_id)
        return [
            TransactionResponse.model_validate(transaction)
            for transaction in transactions
        ]

    @router.get(
        "/{portfolio_id}/analytics",
        response_model=PortfolioAnalyticsResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_portfolio_analytics(
        portfolio_id: UUID,
        start_date: Annotated[date, Query(description="Inclusive first date")],
        end_date: Annotated[date, Query(description="Inclusive last date")],
        user: Annotated[User, Depends(current_user)],
    ) -> PortfolioAnalyticsResponse:
        analytics = await analytics_service.analyze(
            owner_id=user.id,
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        return PortfolioAnalyticsResponse.model_validate(analytics)

    @router.post(
        "/{portfolio_id}/insights",
        response_model=PortfolioInsightResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_portfolio_insight(
        portfolio_id: UUID,
        start_date: Annotated[date, Query(description="Inclusive first date")],
        end_date: Annotated[date, Query(description="Inclusive last date")],
        user: Annotated[User, Depends(current_user)],
    ) -> PortfolioInsightResponse:
        insight = await insight_service.generate(
            owner_id=user.id,
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        return PortfolioInsightResponse.model_validate(insight)

    @router.get(
        "/{portfolio_id}/insights",
        response_model=AnalysisSnapshotPageResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def list_portfolio_insights(
        portfolio_id: UUID,
        user: Annotated[User, Depends(current_user)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AnalysisSnapshotPageResponse:
        page = await insight_service.list_snapshots(
            owner_id=user.id,
            portfolio_id=portfolio_id,
            limit=limit,
            offset=offset,
        )
        return AnalysisSnapshotPageResponse(
            items=[
                AnalysisSnapshotResponse.model_validate(snapshot)
                for snapshot in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    return router
