from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradabilityDecision:
    can_trade: bool
    reason: str | None
    source: str | None
    limit_rule_version: str | None


def check_trade(
    *,
    side: str,
    price: float | None,
    limit_up: float | None,
    limit_down: float | None,
    limit_status: str | None,
    limit_rule_version: str | None,
    tradability_proxy: str | None = None,
    unknown_policy: str = "reject_trade",
    tick_size: float = 0.01,
) -> TradabilityDecision:
    if tradability_proxy == "unavailable":
        return TradabilityDecision(False, "missing_bar_on_open_day", "derived_tradability", limit_rule_version)
    if price is None or price <= 0:
        return TradabilityDecision(False, "missing_or_invalid_raw_open", "daily_price.raw_open", limit_rule_version)
    if limit_status in {"special_case_unknown", "missing_input"}:
        if unknown_policy == "reject_trade":
            return TradabilityDecision(False, limit_status, "derived_limit_price", limit_rule_version)
        if unknown_policy != "exclude_date":
            raise ValueError(f"Unknown tradability policy: {unknown_policy}")
    if limit_status == "verified_rule":
        eps = tick_size / 2.0
        if side == "buy" and limit_up is not None and price >= limit_up - eps:
            return TradabilityDecision(False, "limit_up_open", "derived_limit_price", limit_rule_version)
        if side == "sell" and limit_down is not None and price <= limit_down + eps:
            return TradabilityDecision(False, "limit_down_open", "derived_limit_price", limit_rule_version)
    return TradabilityDecision(True, None, "derived_limit_price", limit_rule_version)
