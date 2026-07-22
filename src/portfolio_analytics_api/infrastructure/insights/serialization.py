import json

from portfolio_analytics_api.domain import InsightInput


def insight_input_payload(insight_input: InsightInput) -> dict[str, object]:
    methodology = insight_input.methodology
    return {
        "metrics": {
            "as_of": insight_input.as_of.isoformat(),
            "simple_return": insight_input.simple_return,
            "annualized_volatility": insight_input.annualized_volatility,
            "max_drawdown": insight_input.max_drawdown,
            "sharpe_ratio": insight_input.sharpe_ratio,
            "asset_weights": [
                {"symbol": weight.symbol, "weight": str(weight.weight)}
                for weight in insight_input.asset_weights
            ],
            "stale": insight_input.stale,
        },
        "methodology": {
            "annual_risk_free_rate": str(methodology.annual_risk_free_rate),
            "risk_free_rate_as_of": methodology.risk_free_rate_as_of.isoformat(),
            "risk_free_rate_assumption": methodology.risk_free_rate_assumption,
            "price_basis": methodology.price_basis.value,
            "return_type": methodology.return_type.value,
            "annualization_periods": methodology.annualization_periods,
            "valuation_method": methodology.valuation_method,
            "cash_flow_policy": methodology.cash_flow_policy,
            "fee_policy": methodology.fee_policy,
            "date_alignment_policy": methodology.date_alignment_policy,
            "transaction_date_timezone": methodology.transaction_date_timezone,
        },
    }


def serialize_insight_input(insight_input: InsightInput) -> str:
    return json.dumps(
        insight_input_payload(insight_input),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
