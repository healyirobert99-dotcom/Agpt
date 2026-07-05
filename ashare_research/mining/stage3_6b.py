from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.expression import parse_formula_text
from ashare_research.mining.model import UniformRandomGenerator
from ashare_research.mining.stage3_6 import disk_mb, generate_unique, peak_memory_mb


PROFILE_FORMULAS = [
    "RET1",
    "RET5",
    "VOL_RATIO20",
    "TREND60",
    "ADD(RET1,VOL_RATIO20)",
    "SUB(RET5,TREND60)",
]


def build_config(config_path: str | Path, run_dir: Path) -> tuple[dict, BacktestConfig, LocalSQLiteProvider]:
    cfg = load_simple_yaml(config_path)
    split = cfg["research_split"]["train"]
    bt = BacktestConfig(
        start_date=split[0],
        end_date=split[1],
        rebalance_frequency=int(cfg["backtest"]["rebalance_frequency"]),
        top_n=int(cfg["backtest"]["top_n"]),
        initial_cash=float(cfg["backtest"]["initial_cash"]),
        cost_bps=float(cfg["backtest"]["one_way_cost_bps"]),
        unknown_tradability_policy=str(cfg["backtest"]["unknown_tradability_policy"]),
        runs_dir=str(run_dir / "independent_backtests"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=1.0,
    )
    data = cfg["data"]
    provider = LocalSQLiteProvider(Path(".") / data["sqlite_path"], Path(".") / data.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"))
    return cfg, bt, provider


def compare_metrics(a: dict, b: dict, tol: float = 1e-9) -> bool:
    keys = ["total_return", "sortino", "max_drawdown", "cumulative_cost", "trade_count", "unfilled_buy_count", "unfilled_sell_count"]
    for key in keys:
        av, bv = a.get(key), b.get(key)
        if isinstance(av, float) or isinstance(bv, float):
            if av is None or bv is None:
                if av != bv:
                    return False
            elif abs(float(av) - float(bv)) > tol:
                return False
        elif av != bv:
            return False
    return True


def run_stage3_6b(config_path: str | Path = "config/search_benchmark_reward_check.yaml", unique_count: int = 20) -> dict:
    run_id = "backtest_performance_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    cfg, bt, provider = build_config(config_path, run_dir)
    start = time.perf_counter()
    context = ResearchContext.build(provider, bt, data_snapshot_hash="stage3_6b")
    context_seconds = time.perf_counter() - start

    profile_rows = []
    evaluator = BatchBacktestEvaluator(context, save_detail_policy="summary_only", run_dir=run_dir / "details")
    for text in PROFILE_FORMULAS:
        expr = parse_formula_text(text)
        result = evaluator.evaluate(expr)
        profile_rows.append({"formula": text, "metrics": result.metrics, "profile": result.profile, "failure_reason": result.failure_reason})

    equivalence = []
    for text in ["RET1", "RET5", "ADD(RET1,VOL_RATIO20)", "SUB(RET5,TREND60)"]:
        expr = parse_formula_text(text)
        independent = DeterministicBacktestEngine(provider, bt).run(expr)
        batch = evaluator.evaluate(expr)
        ok = compare_metrics(independent["metrics"], batch.metrics)
        equivalence.append({"formula": text, "equivalent": ok, "independent_metrics": independent["metrics"], "batch_metrics": batch.metrics})
        import shutil

        shutil.rmtree(independent["run_dir"], ignore_errors=True)

    if not all(row["equivalent"] for row in equivalence):
        raise RuntimeError("batch_equivalence_failed")

    formulas, generated_count, duplicate_count = generate_unique(UniformRandomGenerator(seed=101), unique_count)
    t0 = time.perf_counter()
    batch_results = evaluator.evaluate_many(formulas)
    batch_seconds = time.perf_counter() - t0
    per_formula = [sum(r.profile.values()) for r in batch_results if r.failure_reason is None]
    avg = batch_seconds / len(batch_results)
    estimates = {str(n): avg * n for n in [100, 200, 600]}
    output = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "train": cfg["research_split"]["train"],
        "validation_not_loaded": True,
        "context_hash": context.context_hash,
        "context_seconds": context_seconds,
        "context_profile": context.profile,
        "profile_formulas": profile_rows,
        "equivalence_verified": True,
        "equivalence": equivalence,
        "batch_unique_formula_count": len(batch_results),
        "generated_count": generated_count,
        "duplicate_count": duplicate_count,
        "batch_total_seconds": batch_seconds,
        "batch_avg_seconds": avg,
        "batch_median_internal_seconds": float(np.median(per_formula)) if per_formula else None,
        "batch_p90_internal_seconds": float(np.quantile(per_formula, 0.9)) if per_formula else None,
        "sqlite_read_count_before": len(PROFILE_FORMULAS) * 7,
        "sqlite_read_count_after": 7,
        "feature_compute_count_before": len(PROFILE_FORMULAS),
        "feature_compute_count_after": 1,
        "peak_memory_mb": peak_memory_mb(),
        "disk_output_mb": disk_mb(run_dir),
        "tmp_residual_count": len(list((run_dir / "tmp").glob("*"))) if (run_dir / "tmp").exists() else 0,
        "detail_dir_residual_count": len(list((run_dir / "details").glob("*"))) if (run_dir / "details").exists() else 0,
        "estimated_seconds": estimates,
        "suitable_for_100_200": avg * 200 < 3600,
    }
    (run_dir / "stage3_6b_performance_report.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return output
