from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from portfolio_analytics_api.api.schemas import (
    CreatePortfolioRequest,
    ErrorResponse,
    PortfolioAnalyticsResponse,
    PortfolioResponse,
    TransactionInput,
    TransactionResponse,
)
from portfolio_analytics_api.application import (
    NewTransaction,
    PortfolioAnalyticsService,
    PortfolioService,
    TransactionService,
)


def build_portfolio_router(
    portfolio_service: PortfolioService,
    transaction_service: TransactionService,
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
            base_currency=request.base_currency,
        )
        return PortfolioResponse.model_validate(portfolio)

    @router.get(
        "/{portfolio_id}",
        response_model=PortfolioResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_portfolio(portfolio_id: UUID) -> PortfolioResponse:
        portfolio = await portfolio_service.get(portfolio_id)
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
    ) -> TransactionResponse:
        result = await transaction_service.create(
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
    async def list_transactions(portfolio_id: UUID) -> list[TransactionResponse]:
        transactions = await transaction_service.list(portfolio_id)
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
    ) -> PortfolioAnalyticsResponse:
        analytics = await analytics_service.analyze(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        return PortfolioAnalyticsResponse.model_validate(analytics)

    return router
