import re

from portfolio_analytics_api.domain.models import (
    GeneratedInsight,
    PortfolioAnalytics,
    PortfolioInsight,
    RiskLevel,
)

RULES_VERSION = "risk-rules-v1"
DISCLAIMER = "For informational purposes only; not investment advice."
_FORBIDDEN_RECOMMENDATION = re.compile(
    r"\b(buy|sell|purchase|liquidate|guarantee|guaranteed)\b",
    re.IGNORECASE,
)


def validate_generated_insight(generated: GeneratedInsight) -> None:
    if not 20 <= len(generated.summary.strip()) <= 1200:
        raise ValueError("generated insight summary length is invalid")
    if len(generated.additional_limitations) > 3 or any(
        not limitation.strip() for limitation in generated.additional_limitations
    ):
        raise ValueError("generated insight limitations are invalid")
    text = " ".join((generated.summary, *generated.additional_limitations))
    if _FORBIDDEN_RECOMMENDATION.search(text):
        raise ValueError("generated insight contains transaction language")


def generate_deterministic_insight(
    analytics: PortfolioAnalytics,
) -> PortfolioInsight:
    score = 0
    factors: list[str] = []

    volatility = analytics.annualized_volatility
    if volatility is None:
        factors.append(
            "Annualized volatility is unavailable because the return history "
            "is insufficient."
        )
    elif volatility >= 0.30:
        score += 2
        factors.append(f"Annualized volatility is high at {volatility:.1%}.")
    elif volatility >= 0.15:
        score += 1
        factors.append(f"Annualized volatility is elevated at {volatility:.1%}.")
    else:
        factors.append(f"Annualized volatility is lower at {volatility:.1%}.")

    drawdown = analytics.max_drawdown
    if drawdown is None:
        factors.append(
            "Maximum drawdown is unavailable because the return history is "
            "insufficient."
        )
    elif drawdown <= -0.25:
        score += 2
        factors.append(f"Maximum historical drawdown is severe at {drawdown:.1%}.")
    elif drawdown <= -0.10:
        score += 1
        factors.append(f"Maximum historical drawdown is material at {drawdown:.1%}.")
    else:
        factors.append(f"Maximum historical drawdown is limited at {drawdown:.1%}.")

    sharpe_ratio = analytics.sharpe_ratio
    if sharpe_ratio is None:
        factors.append(
            "Sharpe ratio is unavailable because returns are insufficient or "
            "volatility is zero."
        )
    elif sharpe_ratio < 0:
        score += 1
        factors.append(f"Historical Sharpe ratio is negative at {sharpe_ratio:.2f}.")
    elif sharpe_ratio < 1:
        factors.append(f"Historical Sharpe ratio is below 1 at {sharpe_ratio:.2f}.")
    else:
        factors.append(f"Historical Sharpe ratio is at least 1 at {sharpe_ratio:.2f}.")

    if analytics.asset_weights:
        largest = max(analytics.asset_weights, key=lambda weight: weight.weight)
        concentration = float(largest.weight)
        if concentration >= 0.50:
            score += 2
            label = "high"
        elif concentration >= 0.25:
            score += 1
            label = "elevated"
        else:
            label = "lower"
        factors.append(
            f"Latest single-security concentration is {label}: {largest.symbol} "
            f"represents {concentration:.1%} of total portfolio value."
        )
    else:
        factors.append(
            "Security concentration is unavailable because no latest asset "
            "weights were produced."
        )

    if all(
        metric is None
        for metric in (
            analytics.annualized_volatility,
            analytics.max_drawdown,
            analytics.sharpe_ratio,
        )
    ):
        risk_level = RiskLevel.INSUFFICIENT_DATA
    elif score >= 4:
        risk_level = RiskLevel.HIGH
    elif score >= 2:
        risk_level = RiskLevel.MODERATE
    else:
        risk_level = RiskLevel.LOW

    limitations = [
        "The metrics use historical adjusted-close data and do not forecast "
        "future prices or returns.",
        (
            "Volatility and Sharpe use "
            f"{analytics.methodology.annualization_periods} annual periods; "
            "Sharpe assumes an annual risk-free rate of "
            f"{analytics.methodology.annual_risk_free_rate} as of "
            f"{analytics.methodology.risk_free_rate_as_of.isoformat()}."
        ),
        (
            "Concentration uses latest security weights relative to total "
            "portfolio value including cash; it does not measure sectors, "
            "correlations, liquidity, or issuer relationships."
        ),
    ]
    if any(
        metric is None
        for metric in (
            analytics.annualized_volatility,
            analytics.max_drawdown,
            analytics.sharpe_ratio,
        )
    ):
        limitations.append(
            "At least one statistical metric is unavailable; conclusions from "
            "the available history are limited."
        )
    if analytics.stale:
        limitations.append(
            "The analysis used an explicitly stale retained market-data response."
        )

    return PortfolioInsight(
        as_of=analytics.as_of,
        risk_level=risk_level,
        summary=(
            f"Historical rule-based risk level: {risk_level.value}. "
            "This classification summarizes adverse signals in the supplied "
            "metrics and is not a forecast."
        ),
        key_factors=tuple(factors),
        limitations=tuple(limitations),
        disclaimer=DISCLAIMER,
        generator="deterministic_rules",
        model_name=None,
        prompt_version=RULES_VERSION,
        stale=analytics.stale,
    )
