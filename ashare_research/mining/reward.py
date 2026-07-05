from __future__ import annotations

from dataclasses import dataclass


INVALID_REWARD = -1.0


@dataclass(frozen=True)
class RewardResult:
    reward: float
    validity_status: str
    failure_reason: str | None


def reward_from_metrics(metrics: dict, *, min_trade_count: int) -> RewardResult:
    if not metrics or metrics.get("status") == "insufficient_data":
        return RewardResult(INVALID_REWARD, "failed", "insufficient_data")
    trade_count = int(metrics.get("trade_count") or 0)
    if trade_count < int(min_trade_count):
        return RewardResult(INVALID_REWARD, "failed", "insufficient_trade_count")
    sortino = metrics.get("sortino")
    if sortino is None:
        return RewardResult(INVALID_REWARD, "failed", "sortino_unavailable")
    return RewardResult(float(sortino), "valid", None)


def invalid_reward(reason: str) -> RewardResult:
    return RewardResult(INVALID_REWARD, "invalid", reason)
