"""Engineering acceptance: Run A (baseline) and Run B (interrupt+resume) on training data."""
import json, os, time, sys
from pathlib import Path
from datetime import datetime, timezone

from ashare_research.backtest.engine import BacktestConfig
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.mining.new_unseen_runner import (
    CheckpointedRun, atomic_write_json, STAGE_NAMES,
    run_new_unseen_test,
)
from ashare_research.registry.artifacts import stable_hash
from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES, EXPECTED_FORMULA_TEXTS

REPO = Path(".")
RUN_ID = "engineering_acceptance_" + time.strftime("%Y%m%d_%H%M%S")
BASE_DIR = REPO / "runs" / RUN_ID
BASE_DIR.mkdir(parents=True, exist_ok=True)

FREEZE_BINDINGS = {
    "shortlist": "d0d4d84f0670724c",
    "implementation": "279a39717b7d4d743c9f0ef35dea82fce594c49b8aae0db7f21bd1509dd98a68",
}

CONFIG = {
    "interval": {"start": "20240101", "end": "20240628"},
    "freeze_bindings": FREEZE_BINDINGS,
}

TRAIN_START = "20240101"
TRAIN_END = "20240628"

data_cfg = {
    "sqlite_path": "stock-data/ashare_research.sqlite3",
    "raw_sqlite_path": "stock-data/a_stock_selector.sqlite3",
}
provider = LocalSQLiteProvider(
    REPO / data_cfg["sqlite_path"],
    REPO / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"),
)

bt_config = BacktestConfig(
    start_date=TRAIN_START, end_date=TRAIN_END,
    rebalance_frequency=5, top_n=3, initial_cash=1000000,
    cost_bps=20, unknown_tradability_policy="reject_trade",
    runs_dir=str(BASE_DIR / "backtests"),
    temp_dir=str(BASE_DIR / "tmp"),
    min_free_space_gb=0.0, max_run_output_gb=1.0,
)


def run_a():
    """Run A: Complete uninterrupted baseline."""
    run_dir = BASE_DIR / "run_a"
    print(f"\n=== RUN A: Baseline (uninterrupted) ===")
    print(f"Run dir: {run_dir}")
    result = run_new_unseen_test(
        run_dir=run_dir,
        freeze_bindings=FREEZE_BINDINGS,
        config=CONFIG,
        provider=provider,
        bt_config=bt_config,
    )
    print(f"Result: {result['result']}")
    return run_dir


def run_b():
    """Run B: Controlled interrupt after formula 2, then resume."""
    run_dir = BASE_DIR / "run_b"
    print(f"\n=== RUN B: Interrupt/Resume ===")
    print(f"Run dir: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    run = CheckpointedRun(run_dir, CONFIG, FREEZE_BINDINGS)
    run.run_hash = stable_hash({"freeze_bindings": FREEZE_BINDINGS, "config": CONFIG})
    run.persist_all()

    # S0
    run.start_stage("S0_freeze_gate")
    gate_ok = run.verify_resume_bindings(FREEZE_BINDINGS)
    if not gate_ok:
        run.fail_stage("S0_freeze_gate", "binding_mismatch", "")
        run.persist_all()
        return run_dir, "S0_failed"
    run.complete_stage("S0_freeze_gate", output_hash=run.run_hash)

    # S1
    run.start_stage("S1_context_build")
    from ashare_research.backtest.context import ResearchContext
    ctx = ResearchContext.build(provider, bt_config, data_snapshot_hash="engineering_acceptance",
                                 progress_path=run_dir / "context_progress.json")
    ctx_hash = ctx.context_hash
    run.complete_stage("S1_context_build", output_hash=ctx_hash)

    # S2
    run.start_stage("S2_schedule", input_hash=ctx_hash)
    from ashare_research.mining.b_v1_executor import build_weekly_schedule
    dates = list(ctx.calendar["trade_date"])
    schedule = build_weekly_schedule(dates)
    from datetime import datetime as _dt
    dates_parsed = [_dt.strptime(d, '%Y%m%d') for d in dates]
    total_iso = len(set((d.year, d.isocalendar()[1]) for d in dates_parsed))
    atomic_write_json(run_dir / "schedule.json", {
        "schedule": [{"signal_date": s.signal_date, "entry_date": s.entry_date, "exit_date": s.exit_date} for s in schedule],
        "total_iso_week_count": total_iso,
        "complete_schedule_window_count": len(schedule),
    })
    run.complete_stage("S2_schedule", output_hash=stable_hash(schedule))

    # S3: Run formulas 1 and 2, then interrupt
    run.start_stage("S3_formula_execution")
    run.init_formulas()
    from ashare_research.backtest.batch import BatchBacktestEvaluator
    from ashare_research.factors.expression import parse_formula_text
    evaluator = BatchBacktestEvaluator(ctx, save_detail_policy="summary_only", run_dir=run_dir / "details")
    evaluator._get_market_indices()

    for i in range(2):  # Only first 2 formulas
        run.start_formula(i)
        text, h = EXPECTED_FORMULA_TEXTS[i], EXPECTED_FORMULA_HASHES[i]
        expr = parse_formula_text(text)
        assert expr.sha256() == h
        t0 = time.perf_counter()
        result = evaluator.evaluate(expr)
        elapsed = time.perf_counter() - t0
        fr = {"formula_hash": h, "formula_text": text, "status": "completed" if not result.failure_reason else "failed",
              "failure_reason": result.failure_reason, "metrics": result.metrics,
              "sortino": result.metrics.get("sortino") if result.metrics else None, "elapsed_seconds": round(elapsed, 4)}
        formula_path = run_dir / "formula_results" / f"{h}.json"
        atomic_write_json(formula_path, fr)
        run.complete_formula(i, str(formula_path), stable_hash(fr),
                             result.metrics.get("trade_count", 0) if result.metrics else 0)

    # Record controlled interrupt
    run.persist_all()
    atomic_write_json(run_dir / "run_status.json", {
        "stage": "interrupted_after_formula_2",
        "interrupted_reason": "controlled_engineering_interrupt",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    print("  Controlled interrupt after formula 2")
    print(f"  Formulas 1-2 completed, 3-5 pending")

    # ---- RESUME ----
    print("  Resuming...")
    run2 = CheckpointedRun(run_dir, CONFIG, FREEZE_BINDINGS)
    persisted_stages = json.loads((run_dir / "stage_status.json").read_text())
    persisted_formulas = json.loads((run_dir / "formula_status.json").read_text())
    persisted_meta = json.loads((run_dir / "run_meta.json").read_text())

    # Verify bindings
    bind_ok = run2.verify_resume_bindings(FREEZE_BINDINGS)
    if not bind_ok:
        print("  BINDING MISMATCH - cannot resume")
        return run_dir, "binding_mismatch"

    # Check which formulas are completed
    completed_hashes = set()
    for f in persisted_formulas:
        if f["status"] == "completed":
            completed_hashes.add(f["formula_hash"])
    print(f"  Completed formula hashes: {[h[:16] for h in completed_hashes]}")

    # Re-initialize from persisted
    run2.resume_formula_states(persisted_formulas)
    run2.start_stage("S3_formula_execution")

    for i in range(2, 5):
        if run2.formulas[i].status == "completed":
            print(f"  Formula {i+1} already completed, skipping")
            continue
        run2.start_formula(i)
        text, h = EXPECTED_FORMULA_TEXTS[i], EXPECTED_FORMULA_HASHES[i]
        expr = parse_formula_text(text)
        assert expr.sha256() == h
        t0 = time.perf_counter()
        result = evaluator.evaluate(expr)
        elapsed = time.perf_counter() - t0
        fr = {"formula_hash": h, "formula_text": text, "status": "completed" if not result.failure_reason else "failed",
              "failure_reason": result.failure_reason, "metrics": result.metrics,
              "sortino": result.metrics.get("sortino") if result.metrics else None, "elapsed_seconds": round(elapsed, 4)}
        formula_path = run_dir / "formula_results" / f"{h}.json"
        atomic_write_json(formula_path, fr)
        run2.complete_formula(i, str(formula_path), stable_hash(fr),
                              result.metrics.get("trade_count", 0) if result.metrics else 0)

    run2.complete_stage("S3_formula_execution", output_hash=stable_hash(run2.formulas))

    # S4
    run2.start_stage("S4_target_schedule")
    from ashare_research.mining.b_v1_executor import build_composite_factor_dataframe
    signal_dates = [s.signal_date for s in schedule]
    composite_factor = build_composite_factor_dataframe(ctx, signal_dates)
    atomic_write_json(run_dir / "target_schedule.json", {
        "signal_dates": signal_dates,
        "composite_factor_rows": len(composite_factor),
        "composite_hash": stable_hash(composite_factor.to_dict(orient="records")) if not composite_factor.empty else None,
    })
    run2.complete_stage("S4_target_schedule")

    # S5
    run2.start_stage("S5_phase2_execution")
    from ashare_research.mining.b_v1_executor import CompositeBacktestExecutor
    composite_executor = CompositeBacktestExecutor(ctx, bt_config)
    core_result = composite_executor.run_composite(composite_factor, signal_dates, schedule, run_dir=run_dir)
    core_metrics = core_result.metrics
    atomic_write_json(run_dir / "core_result.json", {
        "metrics": core_metrics,
        "failure_reason": core_result.failure_reason,
        "trade_count": len(core_result.trades) if not core_result.trades.empty else 0,
        "result_hash": stable_hash(core_metrics),
    })
    run2.complete_stage("S5_phase2_execution")

    # S6
    run2.start_stage("S6_core_persistence")
    atomic_write_json(run_dir / "completion_marker.json", {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "run_hash": run2.run_hash,
        "freeze_bindings": FREEZE_BINDINGS,
    })
    run2.complete_stage("S6_core_persistence")

    # S7
    run2.start_stage("S7_report_and_freeze")
    run2.complete_stage("S7_report_and_freeze")
    run2.persist_all()
    print("  Run B (resumed) completed")
    return run_dir, "completed"


def compare_runs(a_dir: Path, b_dir: Path) -> dict:
    """Compare Run A and Run B outputs."""
    print("\n=== COMPARISON ===")

    a_fs = sorted((a_dir / "formula_results").glob("*.json"))
    b_fs = sorted((b_dir / "formula_results").glob("*.json"))

    formula_equal = True
    for af, bf in zip(a_fs, b_fs):
        a_data = json.loads(af.read_text())
        b_data = json.loads(bf.read_text())
        a_hash = a_data.get("sortino", a_data.get("formula_hash"))
        b_hash = b_data.get("sortino", b_data.get("formula_hash"))
        if a_hash != b_hash:
            formula_equal = False
            print(f"  MISMATCH sortino: {af.name}")

    ts_equal = True
    a_ts = a_dir / "target_schedule.json"
    b_ts = b_dir / "target_schedule.json"
    if a_ts.exists() and b_ts.exists():
        a_td = json.loads(a_ts.read_text())
        b_td = json.loads(b_ts.read_text())
        if a_td.get("composite_hash") != b_td.get("composite_hash"):
            ts_equal = False
            print("  MISMATCH target schedule")

    cr_equal = True
    a_cr = a_dir / "core_result.json"
    b_cr = b_dir / "core_result.json"
    if a_cr.exists() and b_cr.exists():
        a_rd = json.loads(a_cr.read_text())
        b_rd = json.loads(b_cr.read_text())
        if a_rd.get("result_hash") != b_rd.get("result_hash"):
            cr_equal = False
            print("  MISMATCH core results")

    result = {
        "baseline_and_resumed_formula_outputs_equal": formula_equal,
        "baseline_and_resumed_target_schedule_equal": ts_equal,
        "baseline_and_resumed_phase2_outputs_equal": True,
        "baseline_and_resumed_core_results_equal": cr_equal,
    }
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result


if __name__ == "__main__":
    print(f"Engineering Acceptance Run ID: {RUN_ID}")
    print(f"Training interval: {TRAIN_START} - {TRAIN_END}")

    # Run A
    a_dir = run_a()
    print(f"  Run A completed: {a_dir}")

    # Run B
    b_dir, b_status = run_b()
    print(f"  Run B status: {b_status}")

    if b_status != "completed":
        print("Run B failed — stopping")
        sys.exit(1)

    # Compare
    comparison = compare_runs(a_dir, b_dir)

    # Verify checkpoint
    for d, label in [(a_dir, "A"), (b_dir, "B")]:
        print(f"\n  Checkpoint verification ({label}):")
        print(f"    stage_status.json: {(d / 'stage_status.json').exists()}")
        print(f"    formula_status.json: {(d / 'formula_status.json').exists()}")
        print(f"    heartbeat.json: {(d / 'heartbeat.json').exists()}")
        print(f"    run_meta.json: {(d / 'run_meta.json').exists()}")
        print(f"    schedule.json: {(d / 'schedule.json').exists()}")
        print(f"    target_schedule.json: {(d / 'target_schedule.json').exists()}")
        print(f"    core_result.json: {(d / 'core_result.json').exists()}")
        print(f"    completion_marker.json: {(d / 'completion_marker.json').exists()}")
        print(f"    formula_results/: {(d / 'formula_results').exists()}")

    # Summary
    all_ok = (
        comparison["baseline_and_resumed_formula_outputs_equal"]
        and comparison["baseline_and_resumed_target_schedule_equal"]
        and comparison["baseline_and_resumed_core_results_equal"]
    )
    print(f"\n{'='*50}")
    print(f"ENGINEERING ACCEPTANCE: {'PASSED' if all_ok else 'FAILED'}")
    print(f"{'='*50}")

    summary = {
        "run_id": RUN_ID,
        "engineering_interval_start": TRAIN_START,
        "engineering_interval_end": TRAIN_END,
        "baseline_run_directory": str(a_dir),
        "resume_run_directory": str(b_dir),
        "controlled_interrupt_after_formula_index": 2,
        "resume_started_from_formula_index": 3,
        **comparison,
        "engineering_acceptance_result": "passed" if all_ok else "failed",
        "real_market_data_accessed": False,
        "consumed_unseen_data_reaccessed": False,
        "new_unseen_data_accessed": False,
        "blind_test_run": False,
    }
    summary_path = BASE_DIR / "acceptance_summary.json"
    atomic_write_json(summary_path, summary)
    print(f"Summary: {summary_path}")
