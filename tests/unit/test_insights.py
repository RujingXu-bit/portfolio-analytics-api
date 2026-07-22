from datetime import date
from decimal import Decimal

from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    AssetWeight,
    PortfolioAnalytics,
    RiskLevel,
    generate_deterministic_insight,
)


def analytics_fixture(
    methodology: AnalyticsMethodology,
    *,
    volatility: float | None,
    drawdown: float | None,
    sharpe: float | None,
    largest_weight: str,
    stale: bool = False,
) -> PortfolioAnalytics:
    weight = Decimal(largest_weight)
    return PortfolioAnalytics(
        as_of=date(2026, 1, 30),
        simple_return=-0.1,
        annualized_volatility=volatility,
        max_drawdown=drawdown,
        sharpe_ratio=sharpe,
        portfolio_value=Decimal("1000"),
        cash_balance=Decimal("0"),
        asset_weights=(AssetWeight("DEMO", Decimal("1000") * weight, weight),),
        methodology=methodology,
        stale=stale,
    )


def test_high_risk_summary_is_stable_and_covers_all_inputs(
    analytics_methodology: AnalyticsMethodology,
) -> None:
    analytics = analytics_fixture(
        analytics_methodology,
        volatility=0.35,
        drawdown=-0.40,
        sharpe=-0.2,
        largest_weight="0.80",
        stale=True,
    )

    first = generate_deterministic_insight(analytics)
    second = generate_deterministic_insight(analytics)

    assert first == second
    assert first.risk_level is RiskLevel.HIGH
    assert [
        "35.0%" in first.key_factors[0],
        "-40.0%" in first.key_factors[1],
        "-0.20" in first.key_factors[2],
        "80.0%" in first.key_factors[3],
    ] == [True, True, True, True]
    assert "stale" in first.limitations[-1]


def test_lower_signals_produce_low_historical_risk_level(
    analytics_methodology: AnalyticsMethodology,
) -> None:
    insight = generate_deterministic_insight(
        analytics_fixture(
            analytics_methodology,
            volatility=0.08,
            drawdown=-0.05,
            sharpe=1.2,
            largest_weight="0.20",
        )
    )

    assert insight.risk_level is RiskLevel.LOW


def test_missing_statistics_are_explicitly_limited(
    analytics_methodology: AnalyticsMethodology,
) -> None:
    insight = generate_deterministic_insight(
        analytics_fixture(
            analytics_methodology,
            volatility=None,
            drawdown=None,
            sharpe=None,
            largest_weight="1",
        )
    )

    assert insight.risk_level is RiskLevel.INSUFFICIENT_DATA
    assert sum("unavailable" in factor for factor in insight.key_factors) == 3
    assert any("conclusions" in limitation for limitation in insight.limitations)


def test_rule_summary_contains_no_transaction_recommendation(
    analytics_methodology: AnalyticsMethodology,
) -> None:
    insight = generate_deterministic_insight(
        analytics_fixture(
            analytics_methodology,
            volatility=0.35,
            drawdown=-0.40,
            sharpe=-0.2,
            largest_weight="0.80",
        )
    )
    output = " ".join(
        (
            insight.summary,
            *insight.key_factors,
            *insight.limitations,
            insight.disclaimer,
        )
    ).lower()

    assert "buy" not in output
    assert "sell" not in output
    assert "guaranteed return" not in output
    assert insight.disclaimer == (
        "For informational purposes only; not investment advice."
    )
