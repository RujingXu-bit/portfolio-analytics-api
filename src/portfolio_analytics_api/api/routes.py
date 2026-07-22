from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from portfolio_analytics_api.api.rate_limit import RateLimitPolicies
from portfolio_analytics_api.api.schemas import (
    AnalysisSnapshotPageResponse,
    AnalysisSnapshotResponse,
    CreatePortfolioRequest,
    ErrorResponse,
    PortfolioAnalyticsResponse,
    PortfolioInsightResponse,
    PortfolioPageResponse,
    PortfolioResponse,
    TransactionImportCommitResponse,
    TransactionImportCommitRowResponse,
    TransactionImportCommitSummaryResponse,
    TransactionImportIssueResponse,
    TransactionImportPreviewResponse,
    TransactionImportPreviewRowResponse,
    TransactionImportPreviewSummaryResponse,
    TransactionImportValueResponse,
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
    RateLimiter,
    TransactionImportService,
    TransactionService,
)
from portfolio_analytics_api.domain import User


def build_portfolio_router(
    authentication_service: AuthenticationService,
    portfolio_service: PortfolioService,
    transaction_service: TransactionService,
    transaction_import_service: TransactionImportService,
    analytics_service: PortfolioAnalyticsService,
    insight_service: PortfolioInsightService,
    rate_limiter: RateLimiter | None = None,
    rate_limit_policies: RateLimitPolicies | None = None,
) -> APIRouter:
    policies = rate_limit_policies or RateLimitPolicies()
    router = APIRouter(
        prefix="/portfolios",
        tags=["portfolios"],
        responses={429: {"model": ErrorResponse}},
    )
    bearer = HTTPBearer(auto_error=False)

    async def current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> User:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise InvalidAccessTokenError()
        return await authentication_service.authenticate(credentials.credentials)

    async def standard_user(
        user: Annotated[User, Depends(current_user)],
    ) -> User:
        if rate_limiter is not None:
            await rate_limiter.enforce(
                policies.authenticated_user,
                f"user:{user.id}",
            )
        return user

    async def analytics_user(
        user: Annotated[User, Depends(current_user)],
    ) -> User:
        if rate_limiter is not None:
            await rate_limiter.enforce(
                policies.analytics_user,
                f"user:{user.id}",
            )
        return user

    async def insights_user(
        user: Annotated[User, Depends(current_user)],
    ) -> User:
        if rate_limiter is not None:
            await rate_limiter.enforce(
                policies.insights_user,
                f"user:{user.id}",
            )
        return user

    @router.post(
        "",
        response_model=PortfolioResponse,
        status_code=status.HTTP_201_CREATED,
        responses={422: {"model": ErrorResponse}},
    )
    async def create_portfolio(
        request: CreatePortfolioRequest,
        user: Annotated[User, Depends(standard_user)],
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
        user: Annotated[User, Depends(standard_user)],
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
        user: Annotated[User, Depends(standard_user)],
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
        user: Annotated[User, Depends(standard_user)],
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
        user: Annotated[User, Depends(standard_user)],
    ) -> list[TransactionResponse]:
        transactions = await transaction_service.list(user.id, portfolio_id)
        return [
            TransactionResponse.model_validate(transaction)
            for transaction in transactions
        ]

    @router.post(
        "/{portfolio_id}/transactions/import/preview",
        response_model=TransactionImportPreviewResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def preview_transaction_import(
        portfolio_id: UUID,
        csv_data: Annotated[
            bytes,
            Body(
                media_type="text/csv",
                max_length=1_000_000,
                description="UTF-8 CSV with at most 500 non-blank transaction rows",
            ),
        ],
        user: Annotated[User, Depends(standard_user)],
    ) -> TransactionImportPreviewResponse:
        preview = await transaction_import_service.preview(
            owner_id=user.id,
            portfolio_id=portfolio_id,
            csv_data=csv_data,
        )
        return TransactionImportPreviewResponse(
            rows=[
                TransactionImportPreviewRowResponse(
                    row_number=row.row_number,
                    external_id=row.external_id,
                    status=row.status,
                    normalized=(
                        _transaction_import_value(row.transaction)
                        if row.transaction is not None
                        else None
                    ),
                    errors=[
                        TransactionImportIssueResponse.model_validate(issue)
                        for issue in row.issues
                    ],
                )
                for row in preview.rows
            ],
            summary=TransactionImportPreviewSummaryResponse(
                total_rows=preview.total_rows,
                ready_rows=preview.ready_rows,
                replay_rows=preview.replay_rows,
                invalid_rows=preview.invalid_rows,
            ),
        )

    @router.post(
        "/{portfolio_id}/transactions/import",
        response_model=TransactionImportCommitResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def commit_transaction_import(
        portfolio_id: UUID,
        csv_data: Annotated[
            bytes,
            Body(
                media_type="text/csv",
                max_length=1_000_000,
                description="The same UTF-8 CSV previously checked by preview",
            ),
        ],
        user: Annotated[User, Depends(standard_user)],
    ) -> TransactionImportCommitResponse:
        result = await transaction_import_service.commit(
            owner_id=user.id,
            portfolio_id=portfolio_id,
            csv_data=csv_data,
        )
        return TransactionImportCommitResponse(
            rows=[
                TransactionImportCommitRowResponse(
                    row_number=row.row_number,
                    external_id=row.external_id,
                    status=row.status,
                    transaction=(
                        TransactionResponse.model_validate(row.transaction)
                        if row.transaction is not None
                        else None
                    ),
                    errors=[
                        TransactionImportIssueResponse.model_validate(issue)
                        for issue in row.issues
                    ],
                )
                for row in result.rows
            ],
            summary=TransactionImportCommitSummaryResponse(
                total_rows=result.total_rows,
                created_rows=result.created_rows,
                replayed_rows=result.replayed_rows,
                failed_rows=result.failed_rows,
            ),
        )

    @router.get(
        "/{portfolio_id}/analytics",
        response_model=PortfolioAnalyticsResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_portfolio_analytics(
        portfolio_id: UUID,
        start_date: Annotated[date, Query(description="Inclusive first date")],
        end_date: Annotated[date, Query(description="Inclusive last date")],
        user: Annotated[User, Depends(analytics_user)],
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
        user: Annotated[User, Depends(insights_user)],
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
        user: Annotated[User, Depends(insights_user)],
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


def _transaction_import_value(transaction: object) -> TransactionImportValueResponse:
    return TransactionImportValueResponse.model_validate(
        transaction,
        from_attributes=True,
    )
