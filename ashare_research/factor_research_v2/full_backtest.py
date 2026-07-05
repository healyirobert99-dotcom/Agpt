from __future__ import annotations

from typing import Any

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.factors.expression import parse_formula_text


def run_full_backtests(candidates: list[dict[str, Any]], evaluator: BatchBacktestEvaluator, limit: int) -> list[dict[str, Any]]:
    rows = []
    for row in candidates[: int(limit)]:
        expr = parse_formula_text(str(row["canonical_formula"]))
        result = evaluator.evaluate(expr)
        trades = result.trades
        completed = trades[trades["status"] == "filled"] if not trades.empty and "status" in trades.columns else trades
        rows.append({
            "formula_hash": row["formula_hash"],
            "canonical_formula": row["canonical_formula"],
            "failure_reason": result.failure_reason,
            "full_backtest_status": "failed" if result.failure_reason else "passed",
            "metrics": result.metrics,
            "trade_count": int(result.metrics.get("trade_count", 0)) if result.metrics else 0,
            "completed_trade_count": int(len(completed)) if completed is not None else 0,
            "average_cash_ratio": _average_cash_ratio(result.accounts),
            "unfilled_count": _unfilled_count(result.trades),
        })
    return rows


def _average_cash_ratio(accounts) -> float | None:
    if accounts is None or accounts.empty or "cash" not in accounts.columns or "total_equity" not in accounts.columns:
        return None
    ratios = accounts["cash"].astype(float) / accounts["total_equity"].astype(float)
    return float(ratios.mean())


def _unfilled_count(trades) -> int:
    if trades is None or trades.empty or "status" not in trades.columns:
        return 0
    return int((trades["status"] != "filled").sum())
