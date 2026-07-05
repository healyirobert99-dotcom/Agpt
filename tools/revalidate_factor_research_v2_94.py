from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _window_results(trades: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    open_entries: dict[str, dict[str, Any]] = {}
    trades = trades.sort_values(["actual_trade_date", "ts_code", "side"], kind="mergesort")
    for _, trade in trades.iterrows():
        side = str(trade["side"])
        code = str(trade["ts_code"])
        executed = float(trade.get("executed_quantity") or 0.0)
        requested = float(trade.get("requested_quantity") or 0.0)
        if side == "buy":
            if executed <= 0:
                rows.append({
                    "ts_code": code,
                    "entry_date": str(trade["actual_trade_date"]),
                    "exit_date": None,
                    "window_status": "entry_unfilled",
                    "net_return_after_cost": None,
                })
                continue
            open_entries[code] = trade.to_dict()
        elif side == "sell" and code in open_entries:
            entry = open_entries.pop(code)
            entry_cost = float(entry.get("transaction_cost") or 0.0)
            exit_cost = float(trade.get("transaction_cost") or 0.0)
            entry_value = float(entry["execution_price"]) * float(entry["executed_quantity"]) + entry_cost
            exit_value = float(trade["execution_price"]) * executed - exit_cost
            rows.append({
                "ts_code": code,
                "entry_date": str(entry["actual_trade_date"]),
                "exit_date": str(trade["actual_trade_date"]),
                "window_status": "completed" if executed > 0 else "exit_unfilled",
                "net_return_after_cost": (exit_value / entry_value - 1.0) if entry_value else None,
            })
    for code, entry in sorted(open_entries.items()):
        rows.append({
            "ts_code": code,
            "entry_date": str(entry["actual_trade_date"]),
            "exit_date": None,
            "window_status": "open_or_incomplete",
            "net_return_after_cost": None,
        })
    return rows


def _final_grade(
    selection: dict[str, Any],
    stability: dict[str, Any],
    selection_fast: dict[str, Any],
    stability_fast: dict[str, Any],
    robust: dict[str, Any],
    rules: dict[str, Any],
    fast_status: str,
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    missing: list[str] = []
    required = ("trade_win_rate", "profit_loss_ratio")
    for source_name, source in (("selection", selection), ("stability", stability)):
        for key in required:
            if source.get(key) is None:
                missing.append(key)
                reasons.append(f"{source_name}_{key}_missing")
    if fast_status != "passed":
        reasons.append("fast_screen_not_passed")
        return "C" if not missing and str(robust.get("robustness_status")) == "passed" else "Rejected", reasons, missing
    if missing:
        return "Rejected", reasons, missing
    if str(robust.get("robustness_status")) != "passed":
        reasons.append("robustness_not_passed")
        return "Rejected", reasons, missing
    if float(stability.get("total_return") or 0.0) <= 0.0:
        reasons.append("stability_total_return_non_positive")
        return "C", reasons, missing
    min_abs_ic = float(rules.get("grade_b_min_abs_ic", 0.0))
    if abs(float(selection_fast.get("rank_ic_mean") or 0.0)) >= min_abs_ic and abs(float(stability_fast.get("rank_ic_mean") or 0.0)) >= min_abs_ic:
        return "B", reasons, missing
    return "C", reasons, missing


def extract_deduplicated_inputs(source_run_dir: str | Path) -> list[dict[str, Any]]:
    source = Path(source_run_dir)
    rows = pd.read_csv(source / "fast_screen_results.csv").to_dict("records")
    clusters = json.loads((source / "dedup_clusters.json").read_text(encoding="utf-8"))
    duplicate_members = {str(item["member"]) for item in clusters.get("clusters", [])}
    fixed = []
    for row in rows:
        if row.get("fast_screen_status") != "passed":
            continue
        if str(row.get("formula_hash")) in duplicate_members:
            continue
        fixed.append({**row, "source_run_id": source.name})
    return fixed
