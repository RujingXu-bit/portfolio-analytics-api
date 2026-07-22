from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from portfolio_analytics_api.domain import (
    InvalidPortfolioValuationError,
    PriceBar,
    Transaction,
    TransactionType,
    build_portfolio_valuation,
    required_price_symbols,
)

PORTFOLIO_ID = UUID("00000000-0000-0000-0000-000000000001")


def transaction(
    transaction_id: int,
    transaction_type: TransactionType,
    day: int,
    *,
    symbol: str | None = None,
    quantity: str | None = None,
    unit_price: str | None = None,
    cash_amount: str | None = None,
    fees: str = "0",
) -> Transaction:
    return Transaction(
        id=UUID(int=transaction_id),
        portfolio_id=PORTFOLIO_ID,
        external_id=f"tx-{transaction_id}",
        transaction_type=transaction_type,
        occurred_at=datetime(2026, 1, day, 9, tzinfo=UTC),
        created_at=datetime(2026, 2, day, 9, tzinfo=UTC),
        symbol=symbol,
        quantity=Decimal(quantity) if quantity is not None else None,
        unit_price=Decimal(unit_price) if unit_price is not None else None,
        cash_amount=Decimal(cash_amount) if cash_amount is not None else None,
        fees=Decimal(fees),
    )


def prices(symbol: str, observations: dict[int, str]) -> tuple[PriceBar, ...]:
    return tuple(
        PriceBar(symbol, date(2026, 1, day), Decimal(value))
        for day, value in observations.items()
    )


def test_multi_asset_value_returns_and_weights_are_hand_checkable() -> None:
    ledger = (
        transaction(1, TransactionType.DEPOSIT, 2, cash_amount="1000"),
        transaction(
            2,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="4",
            unit_price="100",
        ),
        transaction(
            3,
            TransactionType.BUY,
            2,
            symbol="MSFT",
            quantity="2",
            unit_price="100",
        ),
    )

    valuation = build_portfolio_valuation(
        ledger,
        {
            "AAPL": prices("AAPL", {2: "100", 3: "110", 4: "99"}),
            "MSFT": prices("MSFT", {2: "100", 3: "90", 4: "99"}),
        },
        date(2026, 1, 2),
        date(2026, 1, 4),
    )

    assert [point.total_value for point in valuation.points] == [
        Decimal("1000"),
        Decimal("1020"),
        Decimal("994"),
    ]
    assert valuation.period_returns == pytest.approx((0.02, -26 / 1020))
    assert valuation.portfolio_value == Decimal("994")
    assert valuation.cash_balance == Decimal("400")
    weight_values = [
        (weight.symbol, weight.market_value) for weight in valuation.asset_weights
    ]
    assert weight_values == [
        ("AAPL", Decimal("396")),
        ("MSFT", Decimal("198")),
    ]
    assert valuation.asset_weights[0].weight == Decimal("396") / Decimal("994")
    assert valuation.asset_weights[1].weight == Decimal("198") / Decimal("994")


def test_external_cash_flows_and_fees_do_not_invent_performance() -> None:
    ledger = (
        transaction(1, TransactionType.DEPOSIT, 2, cash_amount="1000"),
        transaction(
            2,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="10",
            unit_price="100",
        ),
        transaction(
            3,
            TransactionType.DEPOSIT,
            3,
            cash_amount="100",
            fees="1",
        ),
        transaction(
            4,
            TransactionType.WITHDRAWAL,
            4,
            cash_amount="50",
            fees="1",
        ),
    )

    valuation = build_portfolio_valuation(
        ledger,
        {"AAPL": prices("AAPL", {2: "100", 3: "100", 4: "100"})},
        date(2026, 1, 2),
        date(2026, 1, 4),
    )

    assert [point.total_value for point in valuation.points] == [
        Decimal("1000"),
        Decimal("1099"),
        Decimal("1048"),
    ]
    assert valuation.period_returns == pytest.approx((-0.001, -1 / 1099))


def test_unfunded_buy_uses_implicit_contribution_for_legacy_compatibility() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="2",
            unit_price="100",
        ),
    )

    valuation = build_portfolio_valuation(
        ledger,
        {"AAPL": prices("AAPL", {2: "100", 3: "110", 4: "99"})},
        date(2026, 1, 2),
        date(2026, 1, 4),
    )

    assert [point.total_value for point in valuation.points] == [
        Decimal("200"),
        Decimal("220"),
        Decimal("198"),
    ]
    assert valuation.period_returns == pytest.approx((0.1, -0.1))
    assert valuation.cash_balance == 0
    assert valuation.asset_weights[0].weight == 1


def test_opening_position_and_later_sale_are_replayed_in_order() -> None:
    ledger = (
        transaction(1, TransactionType.DEPOSIT, 1, cash_amount="100"),
        transaction(
            2,
            TransactionType.BUY,
            1,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
        transaction(
            3,
            TransactionType.SELL,
            3,
            symbol="AAPL",
            quantity="1",
            unit_price="110",
            fees="1",
        ),
    )

    assert required_price_symbols(ledger, date(2026, 1, 2), date(2026, 1, 3)) == (
        "AAPL",
    )
    valuation = build_portfolio_valuation(
        ledger,
        {"AAPL": prices("AAPL", {2: "100", 3: "110"})},
        date(2026, 1, 2),
        date(2026, 1, 3),
    )

    assert [point.total_value for point in valuation.points] == [
        Decimal("100"),
        Decimal("109"),
    ]
    assert valuation.period_returns == pytest.approx((0.09,))
    assert valuation.asset_weights == ()
    assert valuation.cash_balance == Decimal("109")


def test_zero_value_dates_before_the_first_trade_are_not_reported() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            3,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
    )

    valuation = build_portfolio_valuation(
        ledger,
        {"AAPL": prices("AAPL", {2: "90", 3: "100"})},
        date(2026, 1, 2),
        date(2026, 1, 3),
    )

    assert [point.date for point in valuation.points] == [date(2026, 1, 3)]
    assert valuation.period_returns == ()


def test_prices_are_carried_forward_but_never_backward_from_the_future() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            1,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
        transaction(
            2,
            TransactionType.BUY,
            1,
            symbol="MSFT",
            quantity="1",
            unit_price="50",
        ),
    )

    valuation = build_portfolio_valuation(
        ledger,
        {
            "AAPL": prices("AAPL", {1: "100", 2: "110"}),
            "MSFT": prices("MSFT", {2: "50"}),
        },
        date(2026, 1, 1),
        date(2026, 1, 2),
    )

    assert [point.date for point in valuation.points] == [date(2026, 1, 2)]
    assert valuation.portfolio_value == Decimal("160")


def test_future_transaction_does_not_change_earlier_valuation() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
        transaction(
            2,
            TransactionType.BUY,
            5,
            symbol="MSFT",
            quantity="10",
            unit_price="50",
        ),
    )

    assert required_price_symbols(ledger, date(2026, 1, 2), date(2026, 1, 3)) == (
        "AAPL",
    )
    valuation = build_portfolio_valuation(
        ledger,
        {"AAPL": prices("AAPL", {2: "100", 3: "101"})},
        date(2026, 1, 2),
        date(2026, 1, 3),
    )

    assert valuation.portfolio_value == Decimal("101")
    assert [weight.symbol for weight in valuation.asset_weights] == ["AAPL"]


def test_price_validation_rejects_mismatched_and_duplicate_data() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
    )
    with pytest.raises(ValueError, match="does not match"):
        build_portfolio_valuation(
            ledger,
            {"AAPL": prices("MSFT", {2: "100"})},
            date(2026, 1, 2),
            date(2026, 1, 3),
        )
    with pytest.raises(ValueError, match="duplicate price date"):
        build_portfolio_valuation(
            ledger,
            {
                "AAPL": (
                    PriceBar("AAPL", date(2026, 1, 2), Decimal("100")),
                    PriceBar("AAPL", date(2026, 1, 2), Decimal("101")),
                )
            },
            date(2026, 1, 2),
            date(2026, 1, 3),
        )


def test_fee_loss_cannot_make_cash_flow_adjusted_value_non_positive() -> None:
    ledger = (
        transaction(1, TransactionType.DEPOSIT, 1, cash_amount="100"),
        transaction(
            2,
            TransactionType.BUY,
            1,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
        transaction(
            3,
            TransactionType.DEPOSIT,
            3,
            cash_amount="1000",
            fees="200",
        ),
    )

    with pytest.raises(
        InvalidPortfolioValuationError,
        match="cash-flow-adjusted portfolio value must remain positive",
    ):
        build_portfolio_valuation(
            ledger,
            {"AAPL": prices("AAPL", {2: "100", 3: "100"})},
            date(2026, 1, 2),
            date(2026, 1, 3),
        )


def test_sell_fees_cannot_create_a_negative_cash_balance() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="1",
            unit_price="1",
        ),
        transaction(
            2,
            TransactionType.SELL,
            3,
            symbol="AAPL",
            quantity="1",
            unit_price="1",
            fees="2",
        ),
    )

    with pytest.raises(
        InvalidPortfolioValuationError,
        match="fees exceed the available cash",
    ):
        build_portfolio_valuation(
            ledger,
            {"AAPL": prices("AAPL", {2: "1", 3: "1"})},
            date(2026, 1, 2),
            date(2026, 1, 3),
        )


def test_prices_outside_the_requested_range_are_ignored() -> None:
    ledger = (
        transaction(
            1,
            TransactionType.BUY,
            2,
            symbol="AAPL",
            quantity="1",
            unit_price="100",
        ),
    )
    valuation = build_portfolio_valuation(
        ledger,
        {"AAPL": prices("AAPL", {1: "99", 2: "100"})},
        date(2026, 1, 2),
        date(2026, 1, 2),
    )

    assert valuation.portfolio_value == Decimal("100")


@pytest.mark.parametrize(
    ("ledger", "price_map", "message"),
    [
        (
            (transaction(1, TransactionType.DEPOSIT, 2, cash_amount="100"),),
            {},
            "no security holdings",
        ),
        (
            (
                transaction(
                    1,
                    TransactionType.BUY,
                    2,
                    symbol="AAPL",
                    quantity="1",
                    unit_price="100",
                ),
            ),
            {},
            "no price bars",
        ),
        (
            (
                transaction(1, TransactionType.DEPOSIT, 1, cash_amount="10"),
                transaction(2, TransactionType.WITHDRAWAL, 2, cash_amount="11"),
                transaction(
                    3,
                    TransactionType.BUY,
                    2,
                    symbol="AAPL",
                    quantity="1",
                    unit_price="1",
                ),
            ),
            {"AAPL": prices("AAPL", {2: "1"})},
            "WITHDRAWAL exceeds",
        ),
    ],
)
def test_invalid_valuation_scenarios_have_stable_errors(
    ledger: tuple[Transaction, ...],
    price_map: dict[str, tuple[PriceBar, ...]],
    message: str,
) -> None:
    with pytest.raises(InvalidPortfolioValuationError, match=message):
        build_portfolio_valuation(
            ledger,
            price_map,
            date(2026, 1, 1),
            date(2026, 1, 4),
        )


def test_invalid_date_range_is_rejected_before_valuation() -> None:
    with pytest.raises(InvalidPortfolioValuationError, match="start_date"):
        required_price_symbols((), date(2026, 1, 3), date(2026, 1, 2))
