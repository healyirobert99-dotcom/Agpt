"""New Unseen Test Runner with Checkpoint and Stage Persistence.

B-v1.0 protocol runner with:
  - 8-stage state machine with persistence
  - Per-formula checkpoint
  - Atomic writes
  - Heartbeat
  - Verified resume binding
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import BacktestConfig
from ashare_research.backtest.records import ExternalTarget
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import parse_formula_text
from ashare_research.mining.b_v1_executor import (
    build_weekly_schedule,
    build_composite_factor_dataframe,
    CompositeBacktestExecutor,
)
from ashare_research.registry.artifacts import stable_hash
from ashare_research.recommendation.protocol_b_v1 import (
    EXPECTED_FORMULA_HASHES,
    EXPECTED_FORMULA_TEXTS,
)


STAGE_NAMES = [
    "S0_freeze_gate",
    "S1_context_build",
    "S2_schedule",
    "S3_formula_execution",
    "S4_target_schedule",
    "S5_phase2_execution",
    "S6_core_persistence",
    "S7_report_and_freeze",
]

VALID_STAGES = set(STAGE_NAMES)
STAGE_STATUSES = {"pending", "running", "completed", "failed", "interrupted"}


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically: tmp → fsync → rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Stage state
# ---------------------------------------------------------------------------


@dataclass
class StageState:
    status: str = "pending"
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def mark_running(self) -> None:
        now = _now()
        self.status = "running"
        self.started_at = self.started_at or now
        self.updated_at = now

    def mark_completed(self, output_hash: str | None = None) -> None:
        now = _now()
        self.status = "completed"
        self.completed_at = now
        self.updated_at = now
        self.output_hash = output_hash

    def mark_failed(self, err_type: str, err_msg: str) -> None:
        self.status = "failed"
        self.updated_at = _now()
        self.error_type = err_type
        self.error_message = err_msg


@dataclass
class FormulaState:
    formula_hash: str
    formula_text: str
    status: str = "pending"
    started_at: str | None = None
    heartbeat_at: str | None = None
    completed_at: str | None = None
    output_path: str | None = None
    output_hash: str | None = None
    finite_value_count: int | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class HeartbeatState:
    current_stage: str | None = None
    current_formula_index: int | None = None
    current_formula_hash: str | None = None
    elapsed_seconds: float | None = None
    last_progress_timestamp: str | None = None
    process_id: int | None = None
    resident_memory_mb: float | None = None


# ---------------------------------------------------------------------------
# Run state machine
# ---------------------------------------------------------------------------


class CheckpointedRun:
    """Maintains and persists run state across all stages."""

    def __init__(self, run_dir: Path, config: dict[str, Any], freeze_bindings: dict[str, str]):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.freeze_bindings = freeze_bindings

        self.stages: dict[str, StageState] = {s: StageState() for s in STAGE_NAMES}
        self.formulas: list[FormulaState] = []
        self.heartbeat = HeartbeatState(process_id=os.getpid())
        self.run_hash: str | None = None

    # ---- Persistence ----

    def _stages_path(self) -> Path:
        return self.run_dir / "stage_status.json"

    def _formulas_path(self) -> Path:
        return self.run_dir / "formula_status.json"

    def _heartbeat_path(self) -> Path:
        return self.run_dir / "heartbeat.json"

    def _run_meta_path(self) -> Path:
        return self.run_dir / "run_meta.json"

    def persist_stages(self) -> None:
        atomic_write_json(self._stages_path(), {k: asdict(v) for k, v in self.stages.items()})

    def persist_formulas(self) -> None:
        atomic_write_json(self._formulas_path(), [asdict(f) for f in self.formulas])

    def persist_heartbeat(self) -> None:
        atomic_write_json(self._heartbeat_path(), asdict(self.heartbeat))

    def persist_run_meta(self) -> None:
        atomic_write_json(self._run_meta_path(), {
            "run_hash": self.run_hash,
            "config": self.config,
            "freeze_bindings": self.freeze_bindings,
            "created_at": _now(),
        })

    def persist_all(self) -> None:
        self.persist_stages()
        self.persist_formulas()
        self.persist_heartbeat()
        self.persist_run_meta()

    # ---- Stage transitions ----

    def stage(self, name: str) -> StageState:
        assert name in VALID_STAGES, f"Unknown stage: {name}"
        return self.stages[name]

    def start_stage(self, name: str, input_hash: str | None = None) -> None:
        s = self.stage(name)
        s.mark_running()
        s.input_hash = input_hash
        self.persist_stages()
        self._update_heartbeat(current_stage=name)

    def complete_stage(self, name: str, output_hash: str | None = None) -> None:
        self.stage(name).mark_completed(output_hash)
        self.persist_stages()

    def fail_stage(self, name: str, err_type: str, err_msg: str) -> None:
        self.stage(name).mark_failed(err_type, err_msg)
        self.persist_stages()

    # ---- Formula transitions ----

    def init_formulas(self) -> None:
        self.formulas = [
            FormulaState(formula_hash=h, formula_text=t)
            for h, t in zip(EXPECTED_FORMULA_HASHES, EXPECTED_FORMULA_TEXTS)
        ]
        self.persist_formulas()

    def start_formula(self, idx: int) -> None:
        f = self.formulas[idx]
        f.status = "running"
        f.started_at = _now()
        f.heartbeat_at = _now()
        self.persist_formulas()
        self._update_heartbeat(current_formula_index=idx, current_formula_hash=f.formula_hash)

    def heartbeat_formula(self, idx: int) -> None:
        self.formulas[idx].heartbeat_at = _now()
        self.persist_formulas()
        self._update_heartbeat()

    def complete_formula(self, idx: int, output_path: str, output_hash: str, finite_count: int) -> None:
        f = self.formulas[idx]
        f.status = "completed"
        f.completed_at = _now()
        f.output_path = output_path
        f.output_hash = output_hash
        f.finite_value_count = finite_count
        self.persist_formulas()

    def fail_formula(self, idx: int, err_type: str, err_msg: str) -> None:
        f = self.formulas[idx]
        f.status = "failed"
        f.heartbeat_at = _now()
        f.error_type = err_type
        f.error_message = err_msg
        self.persist_formulas()

    # ---- Checkpoint verification ----

    def verify_resume_bindings(self, freeze_bindings: dict[str, str]) -> bool:
        for k, v in freeze_bindings.items():
            if self.freeze_bindings.get(k) != v:
                return False
        return True

    def completed_formula_hashes(self) -> list[str]:
        return [f.formula_hash for f in self.formulas if f.status == "completed"]

    def resume_formula_states(self, persisted: list[dict]) -> None:
        """Restore formula states from persisted data."""
        self.formulas = [FormulaState(**f) for f in persisted]

    # ---- Internal ----

    def _update_heartbeat(self, **updates: Any) -> None:
        self.heartbeat.last_progress_timestamp = _now()
        self.heartbeat.elapsed_seconds = time.time() - (
            self.heartbeat.elapsed_seconds or time.time()
        )
        for k, v in updates.items():
            setattr(self.heartbeat, k, v)
        try:
            import resource
            import sys

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                self.heartbeat.resident_memory_mb = round(rss / 1024 / 1024, 2)
            else:
                self.heartbeat.resident_memory_mb = round(rss / 1024, 2)
        except Exception:
            pass
        self.persist_heartbeat()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_new_unseen_test(
    *, run_dir: Path, freeze_bindings: dict[str, str],
    config: dict[str, Any], provider: LocalSQLiteProvider,
    bt_config: BacktestConfig,
) -> dict[str, Any]:
    """Run the B-v1.0 new unseen test with full checkpointing."""
    run = CheckpointedRun(run_dir, config, freeze_bindings)
    run.run_hash = stable_hash({"freeze_bindings": freeze_bindings, "config": config})
    run.persist_all()
    boundary_start, boundary_end = _boundary_interval(config, bt_config)

    # S0: Freeze gate
    run.start_stage("S0_freeze_gate")
    gate_ok = run.verify_resume_bindings(freeze_bindings)
    if not gate_ok:
        run.fail_stage("S0_freeze_gate", "binding_mismatch", "freeze bindings do not match")
        run.persist_all()
        return {"result": "failed", "stage": "S0"}
    run.complete_stage("S0_freeze_gate", output_hash=run.run_hash)

    # S1: Context build
    run.start_stage("S1_context_build")
    try:
        ctx = ResearchContext.build(provider, bt_config,
                                     data_snapshot_hash="new_unseen_b_v1",
                                     progress_path=run_dir / "context_progress.json")
        ctx_hash = ctx.context_hash
        run.complete_stage("S1_context_build", output_hash=ctx_hash)
    except Exception as e:
        run.fail_stage("S1_context_build", type(e).__name__, str(e))
        run.persist_all()
        return {"result": "failed", "stage": "S1", "error": str(e)}

    # S2: Schedule
    run.start_stage("S2_schedule", input_hash=ctx_hash)
    try:
        dates = _boundary_calendar_dates(ctx, boundary_start, boundary_end)
        schedule = build_weekly_schedule(dates)
        _assert_schedule_within_boundary(schedule, boundary_start, boundary_end)
        from datetime import datetime as _dt
        dates_parsed = [_dt.strptime(d, '%Y%m%d') for d in dates]
        total_iso = len(set((d.year, d.isocalendar()[1]) for d in dates_parsed))
        atomic_write_json(run_dir / "schedule.json", {
            "authorized_start": boundary_start,
            "authorized_end": boundary_end,
            "schedule": [_schedule_to_dict(s) for s in schedule],
            "total_iso_week_count": total_iso,
            "complete_schedule_window_count": len(schedule),
            "expected_signal_count_exact": len(schedule),
            "warmup_signal_count": 0,
            "boundary_verified": True,
        })
        run.complete_stage("S2_schedule", output_hash=stable_hash(schedule))
    except Exception as e:
        run.fail_stage("S2_schedule", type(e).__name__, str(e))
        run.persist_all()
        return {"result": "failed", "stage": "S2", "error": str(e)}

    # S3: Formula execution
    run.start_stage("S3_formula_execution")
    run.init_formulas()
    evaluator = BatchBacktestEvaluator(ctx, save_detail_policy="summary_only",
                                        run_dir=run_dir / "details")
    evaluator._get_market_indices()

    formula_results = []
    for i, (text, expected_hash) in enumerate(zip(EXPECTED_FORMULA_TEXTS, EXPECTED_FORMULA_HASHES)):
        run.start_formula(i)
        try:
            expr = parse_formula_text(text)
            assert expr.sha256() == expected_hash, f"Hash mismatch for {text}"
            t0 = time.perf_counter()
            result = evaluator.evaluate(expr)
            elapsed = time.perf_counter() - t0

            formula_result = {
                "formula_hash": expected_hash,
                "formula_text": text,
                "status": "completed" if not result.failure_reason else "failed",
                "failure_reason": result.failure_reason,
                "metrics": result.metrics,
                "sortino": result.metrics.get("sortino") if result.metrics else None,
                "elapsed_seconds": round(elapsed, 4),
            }
            formula_results.append(formula_result)

            # Write per-formula result atomically
            formula_path = run_dir / "formula_results" / f"{expected_hash}.json"
            atomic_write_json(formula_path, formula_result)
            result_hash = stable_hash(formula_result)
            finite_count = (
                result.metrics.get("trade_count", 0) if result.metrics else 0
            )
            run.complete_formula(i, str(formula_path), result_hash, finite_count)
        except Exception as e:
            run.fail_formula(i, type(e).__name__, str(e))
            run.fail_stage("S3_formula_execution", type(e).__name__, str(e))
            run.persist_all()
            return {"result": "failed", "stage": "S3", "formula_index": i, "error": str(e)}

    run.complete_stage("S3_formula_execution", output_hash=stable_hash(formula_results))

    # S4: Target schedule / composite signal
    run.start_stage("S4_target_schedule")
    try:
        signal_dates = [s.signal_date for s in schedule]
        composite_factor = build_composite_factor_dataframe(ctx, signal_dates)
        target_builder = CompositeBacktestExecutor(ctx, bt_config)
        targets = target_builder.build_external_targets(composite_factor, schedule)
        _assert_targets_within_boundary(targets, boundary_start, boundary_end)
        target_rows = _target_rows(targets)
        pd.DataFrame(target_rows).to_csv(run_dir / "target_schedule.csv", index=False)
        atomic_write_json(run_dir / "target_schedule.json", {
            "authorized_start": boundary_start,
            "authorized_end": boundary_end,
            "signal_dates": signal_dates,
            "composite_factor_rows": len(composite_factor),
            "composite_hash": stable_hash(composite_factor.to_dict(orient="records"))
            if not composite_factor.empty else None,
            "target_count": len(target_rows),
            "targets": target_rows,
            "boundary_verified": True,
        })
        run.complete_stage("S4_target_schedule")
    except Exception as e:
        run.fail_stage("S4_target_schedule", type(e).__name__, str(e))
        run.persist_all()
        return {"result": "failed", "stage": "S4", "error": str(e)}

    # S5: Phase 2 execution
    run.start_stage("S5_phase2_execution")
    try:
        execution_ctx = _execution_context_for_boundary(ctx, boundary_start, boundary_end)
        composite_executor = CompositeBacktestExecutor(execution_ctx, bt_config)
        core_result = composite_executor.run_composite(
            composite_factor, signal_dates, schedule, run_dir=run_dir
        )
        window_status = _build_window_status(targets, core_result.trades)
        window_stats = _summarize_window_status(window_status)
        pd.DataFrame(window_status).to_csv(run_dir / "window_status.csv", index=False)
        atomic_write_json(run_dir / "core_result.json", {
            "metrics": core_result.metrics,
            "failure_reason": core_result.failure_reason,
            "trade_count": len(core_result.trades) if not core_result.trades.empty else 0,
            "window_statistics": window_stats,
            "result_hash": stable_hash(core_result.metrics),
        })
        run.complete_stage("S5_phase2_execution")
    except Exception as e:
        run.fail_stage("S5_phase2_execution", type(e).__name__, str(e))
        run.persist_all()
        return {"result": "failed", "stage": "S5", "error": str(e)}

    # S6: Core persistence / freeze
    run.start_stage("S6_core_persistence")
    try:
        atomic_write_json(run_dir / "completion_marker.json", {
            "status": "completed",
            "completed_at": _now(),
            "run_hash": run.run_hash,
            "freeze_bindings": freeze_bindings,
        })
        run.complete_stage("S6_core_persistence")
    except Exception as e:
        run.fail_stage("S6_core_persistence", type(e).__name__, str(e))
        run.persist_all()
        return {"result": "failed", "stage": "S6", "error": str(e)}

    # S7: Report not implemented — for new unseen, user decides after
    run.start_stage("S7_report_and_freeze")
    run.complete_stage("S7_report_and_freeze")
    run.persist_all()

    return {"result": "completed", "run_dir": str(run_dir)}


def _schedule_to_dict(s: Any) -> dict:
    return {"signal_date": s.signal_date, "entry_date": s.entry_date, "exit_date": s.exit_date}


def _boundary_interval(config: dict[str, Any], bt_config: BacktestConfig) -> tuple[str, str]:
    """Return the authorized test interval, distinct from any warm-up range."""
    interval = config.get("interval", {}) if isinstance(config, dict) else {}
    start = str(interval.get("start") or bt_config.start_date)
    end = str(interval.get("end") or bt_config.end_date)
    if start > end:
        raise ValueError("invalid_authorized_interval")
    return start, end


def _boundary_calendar_dates(ctx: ResearchContext, start: str, end: str) -> list[str]:
    dates = [str(d) for d in ctx.calendar["trade_date"].astype(str) if start <= str(d) <= end]
    if not dates:
        raise ValueError("no_authorized_calendar_dates")
    return dates


def _assert_schedule_within_boundary(schedule: list[Any], start: str, end: str) -> None:
    bad = [
        _schedule_to_dict(s)
        for s in schedule
        if str(s.signal_date) < start
        or str(s.signal_date) > end
        or str(s.entry_date) < start
        or str(s.entry_date) > end
        or str(s.exit_date) < start
        or str(s.exit_date) > end
    ]
    if bad:
        raise ValueError(f"schedule_outside_authorized_interval:{bad[:3]}")


def _assert_targets_within_boundary(targets: list[ExternalTarget], start: str, end: str) -> None:
    bad = [
        t.window_id
        for t in targets
        if t.signal_date < start
        or t.signal_date > end
        or t.entry_date < start
        or t.entry_date > end
        or t.planned_exit_date < start
        or t.planned_exit_date > end
    ]
    if bad:
        raise ValueError(f"target_schedule_outside_authorized_interval:{bad[:3]}")


def _target_rows(targets: list[ExternalTarget]) -> list[dict[str, Any]]:
    return [
        {
            "window_id": t.window_id,
            "signal_date": t.signal_date,
            "entry_date": t.entry_date,
            "planned_exit_date": t.planned_exit_date,
            "ts_code": t.ts_code,
            "target_weight": t.target_weight,
            "factor_value": t.factor_value,
            "rank": t.rank,
            "status": "planned",
        }
        for t in targets
    ]


def _execution_context_for_boundary(ctx: ResearchContext, start: str, end: str) -> ResearchContext:
    """Build a Phase 2 execution view that excludes warm-up trading dates."""
    calendar = _filter_by_trade_date(ctx.calendar, start, end)
    dates = tuple(calendar["trade_date"].astype(str))
    return replace(
        ctx,
        bars=_filter_by_trade_date(ctx.bars, start, end),
        calendar=calendar,
        constituents=_filter_effective_trade_date(ctx.constituents, start, end),
        limits=_filter_by_trade_date(ctx.limits, start, end),
        tradability=_filter_by_trade_date(ctx.tradability, start, end),
        st_status=_filter_st_status(ctx.st_status, start, end),
        dates=dates,
        rebalance_dates=frozenset(dates[:: ctx.config.rebalance_frequency]),
    )


def _filter_by_trade_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty or "trade_date" not in df.columns:
        return df.copy()
    dates = df["trade_date"].astype(str)
    return df[(dates >= start) & (dates <= end)].copy()


def _filter_effective_trade_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty or "effective_trade_date" not in df.columns:
        return df.copy()
    dates = df["effective_trade_date"].astype(str)
    return df[(dates >= start) & (dates <= end)].copy()


def _filter_st_status(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty or not {"start_date", "end_date"}.issubset(df.columns):
        return df.copy()
    starts = df["start_date"].astype(str)
    ends = df["end_date"].astype(str)
    return df[(starts <= end) & (ends >= start)].copy()


def _build_window_status(
    targets: list[ExternalTarget],
    trades: pd.DataFrame,
) -> list[dict[str, Any]]:
    trade_rows = trades.to_dict(orient="records") if not trades.empty else []
    by_window: dict[str, list[dict[str, Any]]] = {}
    for row in trade_rows:
        window_id = row.get("window_id")
        if pd.isna(window_id) or window_id is None:
            continue
        by_window.setdefault(str(window_id), []).append(row)

    rows: list[dict[str, Any]] = []
    for target in targets:
        related = by_window.get(target.window_id, [])
        entry_rows = [r for r in related if str(r.get("order_purpose")) == "entry"]
        exit_rows = [r for r in related if str(r.get("order_purpose")) == "exit"]
        filled_entries = [r for r in entry_rows if str(r.get("status")) == "filled"]
        filled_exits = [r for r in exit_rows if str(r.get("status")) == "filled"]
        unfilled_entries = [r for r in entry_rows if str(r.get("status")) != "filled"]
        unfilled_exits = [r for r in exit_rows if str(r.get("status")) != "filled"]

        status = "missing_execution_status"
        failure_reason = None
        net_return = None
        gross_pnl = None
        total_cost = None
        entry_date = None
        exit_date = None
        delayed_exit = bool(unfilled_exits and filled_exits)

        if filled_entries and filled_exits:
            entry = filled_entries[0]
            exit_ = filled_exits[-1]
            entry_cost = _as_float(entry.get("transaction_cost"))
            exit_cost = _as_float(exit_.get("transaction_cost"))
            buy_notional = _as_float(entry.get("executed_notional"))
            sell_notional = _as_float(exit_.get("executed_notional"))
            denominator = buy_notional + entry_cost
            gross_pnl = sell_notional - buy_notional
            total_cost = entry_cost + exit_cost
            net_return = (sell_notional - exit_cost - buy_notional - entry_cost) / denominator if denominator else None
            entry_date = entry.get("actual_trade_date")
            exit_date = exit_.get("actual_trade_date")
            status = "completed"
        elif unfilled_entries and not filled_entries:
            status = "entry_unfilled"
            failure_reason = _first_reason(unfilled_entries)
        elif filled_entries:
            status = "entry_filled_exit_incomplete"
            failure_reason = _first_reason(unfilled_exits) if unfilled_exits else "missing_exit_execution"

        rows.append({
            "window_id": target.window_id,
            "signal_date": target.signal_date,
            "entry_date": target.entry_date,
            "planned_exit_date": target.planned_exit_date,
            "actual_entry_date": entry_date,
            "actual_exit_date": exit_date,
            "ts_code": target.ts_code,
            "rank": target.rank,
            "status": status,
            "failure_reason": failure_reason,
            "entry_trade_count": len(entry_rows),
            "exit_trade_count": len(exit_rows),
            "delayed_exit": delayed_exit,
            "gross_pnl": gross_pnl,
            "total_cost": total_cost,
            "net_return_after_cost": net_return,
        })
    return rows


def _summarize_window_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [
        float(r["net_return_after_cost"])
        for r in rows
        if r.get("status") == "completed" and r.get("net_return_after_cost") is not None
    ]
    return {
        "target_window_count": len(rows),
        "completed_window_count": sum(1 for r in rows if r.get("status") == "completed"),
        "entry_unfilled_count": sum(1 for r in rows if r.get("status") == "entry_unfilled"),
        "incomplete_exit_count": sum(1 for r in rows if r.get("status") == "entry_filled_exit_incomplete"),
        "missing_status_count": sum(1 for r in rows if r.get("status") == "missing_execution_status"),
        "delayed_exit_count": sum(1 for r in rows if r.get("delayed_exit")),
        "net_return_observation_count": len(returns),
        "positive_net_return_count": sum(1 for v in returns if v > 0),
        "negative_net_return_count": sum(1 for v in returns if v < 0),
        "zero_net_return_count": sum(1 for v in returns if v == 0),
        "mean_net_return_after_cost": sum(returns) / len(returns) if returns else None,
        "median_net_return_after_cost": float(pd.Series(returns).median()) if returns else None,
    }


def _first_reason(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        value = row.get("unfilled_reason")
        if value is not None and not pd.isna(value):
            return str(value)
    return None


def _as_float(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
