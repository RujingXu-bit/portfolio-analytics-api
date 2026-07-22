from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from portfolio_analytics_api.api.schemas import (
    CreatePortfolioRequest,
    ErrorResponse,
    PortfolioAnalyticsResponse,
    PortfolioResponse,
)
from portfolio_analytics_api.application import (
    NewTransaction,
    PortfolioAnalyticsService,
    PortfolioService,
)


def build_portfolio_router(
    portfolio_service: PortfolioService,
    analytics_service: PortfolioAnalyticsService,
) -> APIRouter:
    router = APIRouter(prefix="/portfolios", tags=["portfolios"])

    @router.post(
        "",
        response_model=PortfolioResponse,
        status_code=status.HTTP_201_CREATED,
        responses={422: {"model": ErrorResponse}},
    )
    async def create_portfolio(request: CreatePortfolioRequest) -> PortfolioResponse:
        portfolio = await portfolio_service.create(
            name=request.name,
            transactions=tuple(
                NewTransaction(
                    external_id=transaction.external_id,
                    transaction_type=transaction.transaction_type,
                    occurred_at=transaction.occurred_at,
                    symbol=transaction.symbol,
                    quantity=transaction.quantity,
                    unit_price=transaction.unit_price,
                    cash_amount=transaction.cash_amount,
                    fees=transaction.fees,
                )
                for transaction in request.transactions
            ),
        )
        return PortfolioResponse.model_validate(portfolio)

    @router.get(
        "/{portfolio_id}/analytics",
        response_model=PortfolioAnalyticsResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_portfolio_analytics(
        portfolio_id: UUID,
        start_date: Annotated[date, Query(description="Inclusive first date")],
        end_date: Annotated[date, Query(description="Inclusive last date")],
    ) -> PortfolioAnalyticsResponse:
        analytics = await analytics_service.analyze(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        return PortfolioAnalyticsResponse.model_validate(analytics)

    return router
