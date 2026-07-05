from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import Expression

from .models import CandidateFormula


def compute_forward_returns(bars: pd.DataFrame, horizon: int) -> pd.DataFrame:
    frame = bars.sort_values(["ts_code", "trade_date"], kind="mergesort").copy()
    frame["future_close"] = frame.groupby("ts_code")["raw_close"].shift(-int(horizon))
    frame["forward_return"] = frame["future_close"] / frame["raw_close"] - 1.0
    return frame[["trade_date", "ts_code", "forward_return"]]


def screen_candidates(
    candidates: list[CandidateFormula],
    features: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    thresholds: dict[str, Any],
    forward_return_horizon: int,
    output_limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, pd.Series]]:
    labels = compute_forward_returns(bars, forward_return_horizon)
    labels_by_key = labels.set_index(["trade_date", "ts_code"])["forward_return"]
    results: list[dict[str, Any]] = []
    outputs: dict[str, pd.Series] = {}
    output_rows: dict[str, dict[str, Any]] = {}
    min_coverage = float(thresholds.get("min_coverage", 0.1))
    min_abs_ic = float(thresholds.get("min_abs_rank_ic_mean", 0.0))
    min_dispersion = float(thresholds.get("min_cross_sectional_dispersion", 0.0))
    executor = FormulaExecutor(min_valid_rows=int(thresholds.get("min_valid_rows", 20)))
    for cand in candidates:
        expr = Expression(cand.tokens)
        exec_result = executor.execute(expr, features)
        base = {
            "formula_hash": cand.formula_hash,
            "canonical_formula": cand.canonical_formula,
            "coverage": 0.0,
            "rank_ic_mean": None,
            "rank_ic_std": None,
            "rank_ic_ir": None,
            "positive_period_ratio": None,
            "negative_period_ratio": None,
            "monotonicity_score": None,
            "top_bottom_spread": None,
            "turnover_proxy": None,
            "signal_stability": None,
            "fast_screen_status": "rejected",
            "rejection_reason": exec_result.failure_reason,
        }
        if not exec_result.valid or exec_result.values is None:
            results.append(base)
            continue
        factor = exec_result.values.rename("factor_value").reset_index()
        factor.columns = ["ts_code", "trade_date", "factor_value"]
        lookup = pd.MultiIndex.from_frame(factor[["trade_date", "ts_code"]])
        factor["forward_return"] = labels_by_key.reindex(lookup).to_numpy()
        merged = factor.replace([np.inf, -np.inf], np.nan)
        merged = merged.dropna(subset=["factor_value", "forward_return"])
        coverage = len(merged) / max(1, len(factor))
        ics = []
        spreads = []
        dispersions = []
        top_sets = []
        for _, group in merged.groupby("trade_date", sort=True):
            if len(group) < 5 or group["factor_value"].nunique() <= 1:
                continue
            dispersions.append(float(group["factor_value"].std(ddof=0)))
            ic = group["factor_value"].rank().corr(group["forward_return"].rank())
            if pd.notna(ic):
                ics.append(float(ic))
            q = min(5, max(1, len(group) // 5))
            ranked = group.sort_values(["factor_value", "ts_code"], ascending=[False, True], kind="mergesort")
            spreads.append(float(ranked.head(q)["forward_return"].mean() - ranked.tail(q)["forward_return"].mean()))
            top_sets.append(set(ranked.head(q)["ts_code"]))
        ic_mean = float(np.mean(ics)) if ics else None
        ic_std = float(np.std(ics, ddof=0)) if ics else None
        turnover_proxy = _turnover_proxy(top_sets)
        signal_stability = 1.0 - turnover_proxy if turnover_proxy is not None else None
        monotonicity = _monotonicity_score(merged)
        status = "passed"
        reason = None
        if coverage < min_coverage:
            status, reason = "rejected", "low_coverage"
        elif not dispersions or float(np.mean(dispersions)) < min_dispersion:
            status, reason = "rejected", "low_dispersion"
        elif ic_mean is None or abs(ic_mean) < min_abs_ic:
            status, reason = "rejected", "weak_rank_ic"
        row = {
            **base,
            "coverage": coverage,
            "rank_ic_mean": ic_mean,
            "rank_ic_std": ic_std,
            "rank_ic_ir": (ic_mean / ic_std) if ic_mean is not None and ic_std and ic_std > 0 else None,
            "positive_period_ratio": sum(1 for v in ics if v > 0) / len(ics) if ics else None,
            "negative_period_ratio": sum(1 for v in ics if v < 0) / len(ics) if ics else None,
            "monotonicity_score": monotonicity,
            "top_bottom_spread": float(np.mean(spreads)) if spreads else None,
            "turnover_proxy": turnover_proxy,
            "signal_stability": signal_stability,
            "fast_screen_status": status,
            "rejection_reason": reason,
        }
        results.append(row)
        if status == "passed":
            outputs[cand.formula_hash] = exec_result.values
            output_rows[cand.formula_hash] = row
            if output_limit is not None and len(outputs) > int(output_limit):
                worst_hash = max(output_rows.values(), key=_correlation_order_key)["formula_hash"]
                outputs.pop(worst_hash, None)
                output_rows.pop(worst_hash, None)
    return results, outputs


def _correlation_order_key(row: dict[str, Any]) -> tuple[float, float, int, str]:
    return (
        -(abs(float(row.get("rank_ic_mean") or 0.0))),
        -float(row.get("coverage") or 0.0),
        len(str(row.get("canonical_formula", ""))),
        str(row.get("formula_hash", "")),
    )


def _turnover_proxy(top_sets: list[set[str]]) -> float | None:
    if len(top_sets) < 2:
        return None
    changes = []
    for prev, cur in zip(top_sets, top_sets[1:]):
        denom = max(1, len(prev | cur))
        changes.append(1.0 - len(prev & cur) / denom)
    return float(np.mean(changes)) if changes else None


def _monotonicity_score(merged: pd.DataFrame) -> float | None:
    scores = []
    for _, group in merged.groupby("trade_date", sort=True):
        if len(group) < 10 or group["factor_value"].nunique() <= 1:
            continue
        try:
            group = group.copy()
            group["bucket"] = pd.qcut(group["factor_value"], q=5, labels=False, duplicates="drop")
            means = group.groupby("bucket")["forward_return"].mean()
            if len(means) >= 3:
                scores.append(float(means.rank().corr(pd.Series(range(len(means)), index=means.index))))
        except ValueError:
            continue
    vals = [v for v in scores if math.isfinite(v)]
    return float(np.mean(vals)) if vals else None
