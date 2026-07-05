from __future__ import annotations

from .portfolio import Account
from .records import ExecutionRecord, PlannedOrder
from .tradability import check_trade


def execute_order(
    account: Account,
    order: PlannedOrder,
    *,
    raw_open: float | None,
    limit_up: float | None,
    limit_down: float | None,
    limit_status: str | None,
    limit_rule_version: str | None,
    tradability_proxy: str | None,
    cost_bps: float,
    unknown_policy: str,
) -> ExecutionRecord:
    decision = check_trade(
        side=order.side,
        price=raw_open,
        limit_up=limit_up,
        limit_down=limit_down,
        limit_status=limit_status,
        limit_rule_version=limit_rule_version,
        tradability_proxy=tradability_proxy,
        unknown_policy=unknown_policy,
    )
    if not decision.can_trade:
        return ExecutionRecord(
            order.planned_trade_date,
            order.ts_code,
            order.side,
            abs(order.planned_quantity),
            0,
            raw_open,
            0.0,
            0.0,
            "unfilled",
            decision.reason,
            decision.source,
            decision.limit_rule_version,
            order.signal_date,
            order.planned_trade_date,
            order.historical_is_st,
            order.st_source,
        )
    qty = abs(order.planned_quantity)
    try:
        if order.side == "buy":
            cost = account.buy(order.ts_code, qty, float(raw_open), order.planned_trade_date, cost_bps)
        else:
            cost = account.sell(order.ts_code, qty, float(raw_open), cost_bps)
        return ExecutionRecord(
            order.planned_trade_date,
            order.ts_code,
            order.side,
            qty,
            qty,
            float(raw_open),
            qty * float(raw_open),
            cost,
            "filled",
            None,
            decision.source,
            decision.limit_rule_version,
            order.signal_date,
            order.planned_trade_date,
            order.historical_is_st,
            order.st_source,
        )
    except ValueError as exc:
        return ExecutionRecord(
            order.planned_trade_date,
            order.ts_code,
            order.side,
            qty,
            0,
            raw_open,
            0.0,
            0.0,
            "unfilled",
            str(exc),
            decision.source,
            decision.limit_rule_version,
            order.signal_date,
            order.planned_trade_date,
            order.historical_is_st,
            order.st_source,
        )
