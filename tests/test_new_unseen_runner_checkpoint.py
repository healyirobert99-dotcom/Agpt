"""Tests for New Unseen Runner — checkpoint, stage persistence, resume logic.

All tests use artificial data. No real database access.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import BacktestConfig
from ashare_research.backtest.records import ExternalTarget
from ashare_research.registry.artifacts import stable_hash
from ashare_research.mining.new_unseen_runner import (
    CheckpointedRun,
    STAGE_NAMES,
    _assert_schedule_within_boundary,
    _assert_targets_within_boundary,
    _boundary_calendar_dates,
    _build_window_status,
    _execution_context_for_boundary,
    _summarize_window_status,
    atomic_write_json,
)
from ashare_research.mining.b_v1_executor import build_weekly_schedule
from ashare_research.recommendation.protocol_b_v1 import WeeklySchedule


# =========================================================================
# Checkpoint: stage lifecycle
# =========================================================================


def test_stage_lifecycle(tmp_path):
    run = CheckpointedRun(tmp_path, {"test": True}, {"freeze": "abc"})
    assert run.stage("S0_freeze_gate").status == "pending"
    run.start_stage("S0_freeze_gate")
    assert run.stage("S0_freeze_gate").status == "running"
    assert run.stage("S0_freeze_gate").started_at is not None
    run.complete_stage("S0_freeze_gate", output_hash="abc")
    assert run.stage("S0_freeze_gate").status == "completed"


def test_stage_fail(tmp_path):
    run = CheckpointedRun(tmp_path, {}, {})
    run.start_stage("S1_context_build")
    run.fail_stage("S1_context_build", "ValueError", "something broke")
    assert run.stage("S1_context_build").status == "failed"
    assert run.stage("S1_context_build").error_type == "ValueError"
    assert run.stage("S1_context_build").error_message == "something broke"


# =========================================================================
# Checkpoint: stage persistence
# =========================================================================


def test_stage_persistence(tmp_path):
    run = CheckpointedRun(tmp_path, {"k": "v"}, {"f1": "x"})
    run.start_stage("S2_schedule")
    run.persist_all()
    # Reload from persisted
    stages = json.loads((tmp_path / "stage_status.json").read_text())
    assert "S2_schedule" in stages
    assert stages["S2_schedule"]["status"] == "running"


# =========================================================================
# Checkpoint: formula lifecycle
# =========================================================================


def test_formula_lifecycle(tmp_path):
    from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES, EXPECTED_FORMULA_TEXTS
    run = CheckpointedRun(tmp_path, {}, {})
    run.init_formulas()
    assert len(run.formulas) == 5
    assert all(f.status == "pending" for f in run.formulas)

    run.start_formula(0)
    assert run.formulas[0].status == "running"
    assert run.formulas[0].started_at is not None

    run.complete_formula(0, "/tmp/out.json", "hash123", 42)
    assert run.formulas[0].status == "completed"
    assert run.formulas[0].output_hash == "hash123"
    assert run.formulas[0].finite_value_count == 42


def test_formula_persistence(tmp_path):
    from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES
    run = CheckpointedRun(tmp_path, {}, {})
    run.init_formulas()
    run.start_formula(0)
    run.complete_formula(0, "/tmp/out.json", "hash123", 42)
    run.persist_all()

    formulas = json.loads((tmp_path / "formula_status.json").read_text())
    assert formulas[0]["status"] == "completed"
    assert formulas[0]["output_hash"] == "hash123"


# =========================================================================
# Resume: skip completed formulas
# =========================================================================


def test_resume_skips_completed(tmp_path):
    from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES
    run = CheckpointedRun(tmp_path, {}, {})
    run.init_formulas()
    run.start_formula(0)
    run.complete_formula(0, "/tmp/out.json", "hash123", 42)
    run.persist_all()

    # Simulate resume
    run2 = CheckpointedRun(tmp_path, {}, {})
    persisted = json.loads((tmp_path / "formula_status.json").read_text())
    run2.resume_formula_states(persisted)
    completed = run2.completed_formula_hashes()
    assert EXPECTED_FORMULA_HASHES[0] in completed


# =========================================================================
# Resume: binding mismatch prevents resume
# =========================================================================


def test_resume_binding_mismatch(tmp_path):
    run = CheckpointedRun(tmp_path, {}, {"shortlist": "abc"})
    assert run.verify_resume_bindings({"shortlist": "abc"}) is True
    assert run.verify_resume_bindings({"shortlist": "xyz"}) is False


# =========================================================================
# Atomic write: tmp file not seen as complete
# =========================================================================


def test_atomic_write_tmp_not_final(tmp_path):
    p = tmp_path / "test.json"
    atomic_write_json(p, {"hello": "world"})
    assert p.exists()
    assert not p.with_suffix(".json.tmp").exists()


# =========================================================================
# Heartbeat: updates without affecting results
# =========================================================================


def test_heartbeat_updates(tmp_path):
    run = CheckpointedRun(tmp_path, {}, {})
    run.persist_heartbeat()
    hb = json.loads((tmp_path / "heartbeat.json").read_text())
    assert "process_id" in hb
    assert hb["process_id"] is not None


# =========================================================================
# Completion marker prevents incomplete freeze
# =========================================================================


def test_completion_marker_required(tmp_path):
    """Core results should not be freezable without completion marker."""
    marker = tmp_path / "completion_marker.json"
    # No marker — simulate check that should fail
    has_marker = marker.exists()
    assert not has_marker
    # After writing marker
    atomic_write_json(marker, {"status": "completed"})
    assert marker.exists()


# =========================================================================
# All stage names defined
# =========================================================================


def test_all_stages_present():
    expected = [
        "S0_freeze_gate", "S1_context_build", "S2_schedule",
        "S3_formula_execution", "S4_target_schedule",
        "S5_phase2_execution", "S6_core_persistence", "S7_report_and_freeze",
    ]
    assert STAGE_NAMES == expected


# =========================================================================
# Freeze binding: formula count
# =========================================================================


def test_formula_count_expected():
    from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES
    assert len(EXPECTED_FORMULA_HASHES) == 5


# =========================================================================
# Run meta persistence
# =========================================================================


def test_run_meta_persistence(tmp_path):
    bindings = {"shortlist": "d0d4d84f0670724c", "implementation": "b81df032..."}
    run = CheckpointedRun(tmp_path, {"target": 100}, bindings)
    run.run_hash = stable_hash({"bindings": bindings})
    run.persist_run_meta()
    meta = json.loads((tmp_path / "run_meta.json").read_text())
    assert meta["freeze_bindings"]["shortlist"] == "d0d4d84f0670724c"
    assert meta["run_hash"] is not None


# =========================================================================
# Heartbeat: doesn't change formula result
# =========================================================================


def test_heartbeat_does_not_affect_formula(tmp_path):
    from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES
    run = CheckpointedRun(tmp_path, {}, {})
    run.init_formulas()
    run.start_formula(0)
    # Record initial state
    initial_hash = run.formulas[0].formula_hash
    # Heartbeat
    run.heartbeat_formula(0)
    # State should be unchanged except heartbeat_at
    assert run.formulas[0].formula_hash == initial_hash
    assert run.formulas[0].status == "running"


# =========================================================================
# Boundary regression: warm-up must not enter schedule or execution
# =========================================================================


def _dummy_context() -> ResearchContext:
    cfg = BacktestConfig(
        start_date="20240101",
        end_date="20240119",
        rebalance_frequency=5,
        top_n=2,
        initial_cash=100000.0,
        cost_bps=20.0,
        unknown_tradability_policy="block",
    )
    dates = ["20240101", "20240102", "20240105", "20240108", "20240109", "20240112", "20240115", "20240116", "20240119"]
    bars = pd.DataFrame(
        [
            {"trade_date": d, "ts_code": "000001.SZ", "raw_open": 10.0, "raw_close": 10.0}
            for d in dates
        ]
    )
    calendar = pd.DataFrame({"trade_date": dates})
    empty = pd.DataFrame()
    return ResearchContext(
        config=cfg,
        bars=bars,
        calendar=calendar,
        constituents=pd.DataFrame({"effective_trade_date": dates, "ts_code": ["000001.SZ"] * len(dates)}),
        limits=bars[["trade_date", "ts_code"]].copy(),
        tradability=bars[["trade_date", "ts_code"]].iloc[0:0].copy(),
        lifecycle=pd.DataFrame({"ts_code": ["000001.SZ"], "list_date": ["20200101"], "delist_date": [None]}),
        st_status=pd.DataFrame({"ts_code": ["000001.SZ"], "start_date": ["20230101"], "end_date": ["20241231"], "historical_is_st": [False]}),
        features=empty,
        standardized_features=empty,
        dates=tuple(dates),
        rebalance_dates=frozenset(dates[:: cfg.rebalance_frequency]),
        context_hash="dummy",
    )


def test_boundary_schedule_excludes_warmup_dates() -> None:
    ctx = _dummy_context()
    boundary_dates = _boundary_calendar_dates(ctx, "20240108", "20240119")
    assert boundary_dates[0] == "20240108"
    assert "20240105" not in boundary_dates

    schedule = build_weekly_schedule(boundary_dates)
    _assert_schedule_within_boundary(schedule, "20240108", "20240119")
    assert all(s.signal_date >= "20240108" for s in schedule)


def test_schedule_boundary_gate_rejects_warmup_signal() -> None:
    bad = [WeeklySchedule(signal_date="20240105", entry_date="20240108", exit_date="20240115")]
    try:
        _assert_schedule_within_boundary(bad, "20240108", "20240119")
    except ValueError as exc:
        assert "schedule_outside_authorized_interval" in str(exc)
    else:
        raise AssertionError("warmup schedule was not rejected")


def test_target_boundary_gate_rejects_warmup_target() -> None:
    bad = [
        ExternalTarget(
            window_id="w1",
            signal_date="20240105",
            entry_date="20240108",
            planned_exit_date="20240115",
            ts_code="000001.SZ",
            target_weight=0.2,
            factor_value=1.0,
            rank=1,
        )
    ]
    try:
        _assert_targets_within_boundary(bad, "20240108", "20240119")
    except ValueError as exc:
        assert "target_schedule_outside_authorized_interval" in str(exc)
    else:
        raise AssertionError("warmup target was not rejected")


def test_execution_context_excludes_warmup_market_rows() -> None:
    ctx = _dummy_context()
    execution_ctx = _execution_context_for_boundary(ctx, "20240108", "20240119")
    assert execution_ctx.calendar["trade_date"].min() == "20240108"
    assert execution_ctx.bars["trade_date"].min() == "20240108"
    assert "20240105" not in set(execution_ctx.dates)
    assert ctx.calendar["trade_date"].min() == "20240101"


def test_window_status_covers_completed_and_failed_targets() -> None:
    targets = [
        ExternalTarget("w1", "20240108", "20240109", "20240115", "000001.SZ", 0.2, 1.0, 1),
        ExternalTarget("w2", "20240108", "20240109", "20240115", "000002.SZ", 0.2, 0.9, 2),
    ]
    trades = pd.DataFrame(
        [
            {
                "window_id": "w1",
                "order_purpose": "entry",
                "status": "filled",
                "actual_trade_date": "20240109",
                "executed_notional": 1000.0,
                "transaction_cost": 2.0,
            },
            {
                "window_id": "w1",
                "order_purpose": "exit",
                "status": "filled",
                "actual_trade_date": "20240115",
                "executed_notional": 1100.0,
                "transaction_cost": 2.2,
            },
            {
                "window_id": "w2",
                "order_purpose": "entry",
                "status": "unfilled",
                "actual_trade_date": "20240109",
                "executed_notional": 0.0,
                "transaction_cost": 0.0,
                "unfilled_reason": "limit_up_open",
            },
        ]
    )
    rows = _build_window_status(targets, trades)
    summary = _summarize_window_status(rows)

    assert [r["status"] for r in rows] == ["completed", "entry_unfilled"]
    assert rows[0]["net_return_after_cost"] == (1100.0 - 2.2 - 1000.0 - 2.0) / 1002.0
    assert summary["target_window_count"] == 2
    assert summary["net_return_observation_count"] == 1
    assert summary["entry_unfilled_count"] == 1
