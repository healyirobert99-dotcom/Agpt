from __future__ import annotations


def bps_to_rate(bps: float) -> float:
    return float(bps) / 10000.0


def transaction_cost(notional: float, one_way_bps: float) -> float:
    return abs(float(notional)) * bps_to_rate(one_way_bps)

