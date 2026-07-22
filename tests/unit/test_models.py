from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    AssetWeight,
    PortfolioAnalytics,
    PriceBar,
    PriceBasis,
    ReturnType,
    Transaction,
    TransactionType,
)


def test_methodology_records_financial_assumptions(
    analytics_methodology: AnalyticsMethodology,
) -> None:
    assert analytics_methodology.price_basis is PriceBasis.ADJUSTED_CLOSE
    assert analytics_methodology.return_type is ReturnType.SIMPLE
    assert analytics_methodology.annualization_periods == 252
    assert analytics_methodology.annual_risk_free_rate == Decimal("0.04")
    assert analytics_methodology.risk_free_rate_as_of.isoformat() == "2026-01-01"
    assert (
        analytics_methodology.risk_free_rate_assumption
        == "Illustrative annual rate held constant over the analysis period."
    )


def test_price_bar_preserves_adjusted_close_as_decimal() -> None:
    price_bar = PriceBar(
        symbol="AAPL",
        date=date(2026, 1, 2),
        adjusted_close=Decimal("193.2500"),
    )

    assert price_bar.symbol == "AAPL"
    assert price_bar.date == date(2026, 1, 2)
    assert price_bar.adjusted_close == Decimal("193.2500")
    assert isinstance(price_bar.adjusted_close, Decimal)


def test_transaction_type_values_are_stable() -> None:
    assert [transaction_type.value for transaction_type in TransactionType] == [
        "BUY",
        "SELL",
        "DEPOSIT",
        "WITHDRAWAL",
    ]


def test_buy_transaction_preserves_decimal_values() -> None:
    transaction = Transaction(
        portfolio_id=UUID("00000000-0000-0000-0000-000000000001"),
        external_id="broker-buy-001",
        transaction_type=TransactionType.BUY,
        occurred_at=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        symbol="AAPL",
        quantity=Decimal("1.5000"),
        unit_price=Decimal("193.2500"),
        fees=Decimal("0.25"),
    )

    assert transaction.symbol == "AAPL"
    assert transaction.quantity == Decimal("1.5000")
    assert transaction.unit_price == Decimal("193.2500")
    assert transaction.fees == Decimal("0.25")
    assert transaction.cash_amount is None


def test_deposit_transaction_uses_cash_amount() -> None:
    transaction = Transaction(
        portfolio_id=UUID("00000000-0000-0000-0000-000000000001"),
        external_id="bank-deposit-001",
        transaction_type=TransactionType.DEPOSIT,
        occurred_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
        cash_amount=Decimal("1000.00"),
    )

    assert transaction.symbol is None
    assert transaction.quantity is None
    assert transaction.unit_price is None
    assert transaction.cash_amount == Decimal("1000.00")
    assert transaction.fees == Decimal("0")


def test_portfolio_analytics_includes_as_of_and_methodology(
    analytics_methodology: AnalyticsMethodology,
) -> None:
    analytics = PortfolioAnalytics(
        as_of=date(2026, 1, 31),
        simple_return=0.05,
        annualized_volatility=0.12,
        max_drawdown=-0.08,
        sharpe_ratio=0.75,
        portfolio_value=Decimal("1050"),
        cash_balance=Decimal("50"),
        asset_weights=(
            AssetWeight(
                symbol="AAPL",
                market_value=Decimal("1000"),
                weight=Decimal("0.9523809523809523809523809524"),
            ),
        ),
        methodology=analytics_methodology,
    )

    assert analytics.as_of == date(2026, 1, 31)
    assert analytics.simple_return == 0.05
    assert analytics.annualized_volatility == 0.12
    assert analytics.max_drawdown == -0.08
    assert analytics.sharpe_ratio == 0.75
    assert analytics.portfolio_value == Decimal("1050")
    assert analytics.cash_balance == Decimal("50")
    assert analytics.asset_weights[0].symbol == "AAPL"
    assert analytics.methodology is analytics_methodology
    assert analytics.stale is False
