from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.expression import parse_formula_text
from ashare_research.mining.stage3_6 import CachedProvider, FullBacktestBatchEvaluator, disk_mb, peak_memory_mb, run_search_benchmark


PREFLIGHT_FORMULAS = [
    "RET1",
    "RET5",
    "VOL_RATIO20",
    "TREND60",
    "ADD(RET1,VOL_RATIO20)",
    "SUB(RET5,TREND60)",
]


def sortino_diagnostic(metrics: dict, run_dir: str | None) -> dict:
    daily_count = 0
    negative_count = 0
    reason = None
    if run_dir:
        account_path = Path(run_dir) / "daily_account.csv"
        if account_path.exists():
            accounts = pd.read_csv(account_path)
            returns = accounts["net_return"].astype(float).dropna()
            daily_count = int(len(returns))
            negative_count = int((returns < 0).sum())
    if metrics.get("sortino") is not None:
        status = "available"
    elif daily_count == 0:
        status = "unavailable"
        reason = "returns_sequence_empty"
    elif negative_count == 0:
        status = "unavailable"
        reason = "no_negative_return_observation"
    elif (metrics.get("trade_count") or 0) == 0:
        status = "unavailable"
        reason = "trade_count_zero"
    else:
        status = "unavailable"
        reason = metrics.get("status") or "downside_deviation_zero_or_unavailable"
    return {
        "daily_return_observation_count": daily_count,
        "negative_return_observation_count": negative_count,
        "sortino_status": status,
        "failure_reason": reason,
    }


def preflight_reward_check(config_path: str | Path, repo_root: Path, run_dir: Path) -> list[dict]:
    cfg = load_simple_yaml(config_path)
    split = cfg["research_split"]["train"]
    data_cfg = cfg["data"]
    provider = CachedProvider(
        LocalSQLiteProvider(repo_root / data_cfg["sqlite_path"], repo_root / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3")),
        split[0],
        split[1],
    )
    from ashare_research.backtest.engine import BacktestConfig

    bt = BacktestConfig(
        start_date=split[0],
        end_date=split[1],
        rebalance_frequency=int(cfg["backtest"]["rebalance_frequency"]),
        top_n=int(cfg["backtest"]["top_n"]),
        initial_cash=float(cfg["backtest"]["initial_cash"]),
        cost_bps=float(cfg["backtest"]["one_way_cost_bps"]),
        unknown_tradability_policy=str(cfg["backtest"]["unknown_tradability_policy"]),
        runs_dir=str(run_dir / "preflight_backtests"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=1.0,
    )
    evaluator = FullBacktestBatchEvaluator(provider, bt, min_trade_count=int(cfg["mining"]["min_trade_count"]), keep_details=True)
    rows = []
    for text in PREFLIGHT_FORMULAS:
        expr = parse_formula_text(text)
        record = evaluator.evaluate(expr)
        run_dirs = sorted((run_dir / "preflight_backtests").glob("bt_*"), key=lambda p: p.stat().st_mtime)
        latest = str(run_dirs[-1]) if run_dirs else None
        diag = sortino_diagnostic(record.metrics, latest)
        rows.append(
            {
                "formula": text,
                "trade_count": record.metrics.get("trade_count"),
                "sortino": record.metrics.get("sortino"),
                **diag,
            }
        )
        if latest:
            shutil.rmtree(latest, ignore_errors=True)
    return rows


def reward_distribution_summary(records: list[dict]) -> dict:
    rewards = [r.get("reward") for r in records if r.get("reward") is not None and np.isfinite(float(r.get("reward")))]
    if not rewards:
        return {"count": len(records), "finite_count": 0}
    arr = np.array(rewards, dtype=float)
    return {
        "count": len(records),
        "finite_count": int(len(arr)),
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=0)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "percentiles": {"p10": float(np.quantile(arr, 0.1)), "p50": float(np.quantile(arr, 0.5)), "p90": float(np.quantile(arr, 0.9))},
        "positive_reward_count": int((arr > 0).sum()),
        "negative_reward_count": int((arr < 0).sum()),
        "zero_reward_count": int((arr == 0).sum()),
    }


def run_stage3_6a(config_path: str | Path, repo_root: Path, run_medium: bool = False) -> dict:
    cfg = load_simple_yaml(config_path)
    run_id = "search_reward_check_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    preflight = preflight_reward_check(config_path, repo_root, run_dir)
    sortino_available = sum(1 for row in preflight if row["sortino_status"] == "available")
    benchmark = None
    skip_reason = None
    if sortino_available == 0:
        skip_reason = "preflight_sortino_unavailable"
    elif run_medium:
        benchmark = run_search_benchmark(config_path, repo_root)
    else:
        skip_reason = "medium_budget_not_started_without_explicit_run_medium_flag"
    result = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "train": cfg["research_split"]["train"],
        "validation": cfg["research_split"]["validation"],
        "date_selection_basis": "data coverage and CSI800 snapshot coverage; not selected from formula performance",
        "preflight": preflight,
        "preflight_sortino_available_count": sortino_available,
        "preflight_sortino_available_ratio": sortino_available / len(preflight),
        "benchmark": benchmark,
        "benchmark_skip_reason": skip_reason,
        "ready_for_600_full_backtests": False,
        "ready_blockers": [],
        "wall_clock_seconds": time.perf_counter() - started,
        "peak_memory_mb": peak_memory_mb(),
        "disk_output_mb": disk_mb(run_dir),
        "tmp_residual_count": len(list((run_dir / "tmp").glob("*"))) if (run_dir / "tmp").exists() else 0,
        "full_detail_dir_residual_count": len(list((run_dir / "preflight_backtests").glob("bt_*"))) if (run_dir / "preflight_backtests").exists() else 0,
        "pytorch_route_decision": "route_1_continue_simple_searchers",
    }
    if sortino_available == 0:
        result["ready_blockers"].append("preflight produced no calculable Sortino")
    if benchmark is None:
        result["ready_blockers"].append(skip_reason)
    (run_dir / "stage3_6a_reward_observability.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return result
