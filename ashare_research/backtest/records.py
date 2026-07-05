from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class PlannedOrder:
    signal_date: str
    planned_trade_date: str
    ts_code: str
    side: str
    target_weight: float
    target_quantity: int
    current_quantity: int
    planned_quantity: int
    formula_hash: str
    factor_value: float
    rank: int
    snapshot_date: str | None = None
    effective_trade_date: str | None = None
    membership_source: str | None = None
    historical_is_st: bool | None = None
    st_source: str | None = None
    window_id: str | None = None
    planned_exit_date: str | None = None
    order_purpose: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionRecord:
    actual_trade_date: str
    ts_code: str
    side: str
    requested_quantity: int
    executed_quantity: int
    execution_price: float | None
    executed_notional: float
    transaction_cost: float
    status: str
    unfilled_reason: str | None
    tradability_source: str | None
    limit_rule_version: str | None
    signal_date: str | None = None
    planned_trade_date: str | None = None
    historical_is_st: bool | None = None
    st_source: str | None = None
    window_id: str | None = None
    planned_exit_date: str | None = None
    order_purpose: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExternalTarget:
    window_id: str
    signal_date: str
    entry_date: str
    planned_exit_date: str
    ts_code: str
    target_weight: float
    factor_value: float
    rank: int
