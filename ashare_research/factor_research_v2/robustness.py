from __future__ import annotations

from typing import Any


def evaluate_robustness(full_rows: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    min_positive = float(cfg.get("rating", {}).get("min_positive_period_ratio", 0.45))
    out = []
    for row in full_rows:
        metrics = row.get("metrics") or {}
        total_return = metrics.get("total_return")
        sortino = metrics.get("sortino")
        positive_period_ratio = 1.0 if total_return is not None and float(total_return) > 0 else 0.0
        robust = row.get("full_backtest_status") == "passed" and positive_period_ratio >= min_positive
        out.append({
            "formula_hash": row["formula_hash"],
            "stable_period_ratio": positive_period_ratio,
            "positive_period_ratio": positive_period_ratio,
            "worst_period_return": total_return,
            "worst_period_ic": None,
            "cost_sensitivity": "not_run_mvp",
            "holding_period_sensitivity": "not_run_mvp",
            "robustness_status": "passed" if robust else "rejected",
            "sortino": sortino,
        })
    return out


def grade_factor(fast: dict[str, Any], full: dict[str, Any], robust: dict[str, Any], rules: dict[str, Any]) -> str:
    if full.get("full_backtest_status") != "passed" or robust.get("robustness_status") != "passed":
        return "Rejected"
    ic = abs(float(fast.get("rank_ic_mean") or 0.0))
    ret = float((full.get("metrics") or {}).get("total_return") or 0.0)
    max_dd = abs(float((full.get("metrics") or {}).get("max_drawdown") or 0.0))
    if ic >= float(rules.get("grade_a_min_abs_ic", 0.03)) and ret > 0 and max_dd <= float(rules.get("grade_a_max_drawdown", 0.35)):
        return "A"
    if ic >= float(rules.get("grade_b_min_abs_ic", 0.015)) and ret > 0:
        return "B"
    if ret > 0:
        return "C"
    return "Rejected"
