from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from ashare_research.mining import forward_paper_runner as fpr
from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES, PROTOCOL_ID


class FakeForwardProvider:
    def __init__(self, calendar: list[str]):
        self.calendar = calendar
        self.research_sqlite_path = None

    def get_trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame({"trade_date": [d for d in self.calendar if start_date <= d <= end_date]})


def _write_config(path: Path) -> None:
    path.write_text(
        """
tracker_id: forward_paper_tracking_b_v1
mode: paper_forward_only
initial_capital: 1000000
data_policy:
  backfill_allowed: false
  historical_replay_allowed: false
  blind_interval_creation_allowed: false
  validation_access_allowed: false
  blind_test_access_allowed: false
""".strip(),
        encoding="utf-8",
    )


def test_activation_before_dates_does_not_generate_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240101")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 2, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider(["20240101", "20240103", "20240104", "20240105", "20240108"]),
    )

    assert result["activation_status"] == "active"
    assert result["activation_date"] == "20240103"
    assert result["activated_at"] is not None
    assert result["next_eligible_signal_date"] == "20240105"
    assert result["signal_generated"] is False
    state = json.loads((tmp_path / "runs/forward_test/state.json").read_text())
    assert state["backfill_allowed"] is False


def test_non_week_last_trade_day_is_not_due(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240103")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider(["20240103", "20240104", "20240105", "20240108"]),
    )

    assert result["next_eligible_signal_date"] == "20240105"
    assert result["due_event_found"] is False


def test_repeated_activation_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240101")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)
    provider = FakeForwardProvider(["20240101", "20240103", "20240104", "20240105"])
    now = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)

    fpr.run_forward_paper_once(cfg, tmp_path, now=now, provider=provider)
    fpr.run_forward_paper_once(cfg, tmp_path, now=now, provider=provider)

    events = [
        json.loads(line)
        for line in (tmp_path / "runs/forward_test/event_log.jsonl").read_text().splitlines()
        if line.strip()
    ]
    activation_events = [e for e in events if e["event_type"] == "forward_tracking_activated"]
    assert len(activation_events) == 1


def test_append_only_conflict_refuses_overwrite(tmp_path):
    path = tmp_path / "event_log.jsonl"
    record = {"event_id": "same", "created_at": "a", "input_hash": "1", "strategy_version": fpr.STRATEGY_VERSION}
    fpr._append_unique_event(path, record)
    with pytest.raises(ValueError, match="integrity_conflict"):
        fpr._append_unique_event(path, {**record, "input_hash": "2"})


def test_missed_cycle_is_not_backfilled(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240110")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 10, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider(["20240111", "20240112", "20240115"]),
    )

    assert result["signal_generated"] is False
    assert result["historical_replay_allowed"] is False if "historical_replay_allowed" in result else True


def test_unfinished_daily_bar_does_not_generate_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240104")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 5, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider(["20240105", "20240108"]),
    )

    assert result["activation_status"] == "pending_data_update"
    assert result["activated_at"] is None
    assert result["next_eligible_signal_date"] is None
    assert result["signal_generated"] is False


def test_signal_snapshot_record_has_required_evidence_fields():
    record = fpr.build_signal_snapshot_record(
        signal_date="20240105",
        data_available_through="20240105",
        data_snapshot_hash="abc",
        formula_status=[{"formula_hash": h, "status": "completed"} for h in EXPECTED_FORMULA_HASHES],
        selected_targets=[{"ts_code": "000001.SZ", "rank": 1, "target_weight": 0.2, "window_id": "w1"}],
        source_commit="commit",
        created_at="2024-01-05T16:00:00+08:00",
    )

    assert record["signal_event_id"] == f"{PROTOCOL_ID}:20240105"
    assert record["formula_hashes"] == list(EXPECTED_FORMULA_HASHES)
    assert record["formula_values_snapshot_hash"]
    assert record["selected_top_5"][0]["window_id"] == "w1"
    assert record["input_hash"]


def test_completed_window_only_enters_win_rate():
    summary = fpr.summarize_completed_window_returns(
        [
            {"status": "exit_completed", "net_return_after_cost": 0.01},
            {"status": "exit_completed", "net_return_after_cost": 0.0},
            {"status": "entry_unfilled", "net_return_after_cost": 0.5},
            {"status": "open_or_incomplete", "net_return_after_cost": 0.5},
        ]
    )
    assert summary["completed_window_count"] == 2
    assert summary["winning_completed_window_count"] == 1
    assert summary["window_win_rate"] == 0.5


def test_phase2_interrupted_state_does_not_auto_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240105")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)
    run_dir = tmp_path / "runs/forward_test"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({"phase2_status": "interrupted"}), encoding="utf-8")

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 5, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider(["20240108", "20240109"]),
    )

    state = json.loads((run_dir / "state.json").read_text())
    assert state["phase2_status"] == "interrupted"
    assert result["paper_execution_generated"] is False


def test_stale_prefilled_activation_date_is_not_trusted_without_calendar(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240101")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)
    run_dir = tmp_path / "runs/forward_test"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({"activation_date": "20240102"}), encoding="utf-8")

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider([]),
    )

    assert result["activation_status"] == "pending_data_update"
    assert result["activation_date"] is None
    assert result["activated_at"] is None
    assert result["signal_generated"] is False


def test_pending_state_uses_activation_requested_at_and_null_activated_at(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240101")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)

    result = fpr.run_forward_paper_once(
        cfg,
        tmp_path,
        now=datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
        provider=FakeForwardProvider([]),
    )
    state = json.loads((tmp_path / "runs/forward_test/state.json").read_text())

    assert result["activation_status"] == "pending_data_update"
    assert result["activation_requested_at"] is not None
    assert result["activated_at"] is None
    assert state["activated_at"] is None
    assert state["activation_date"] is None


def test_repeated_active_due_check_does_not_append_activation_again(tmp_path, monkeypatch):
    monkeypatch.setattr(fpr, "TRACKER_RUN_DIR", Path("runs/forward_test"))
    monkeypatch.setattr(fpr, "_data_available_through", lambda provider: "20240101")
    cfg = tmp_path / "forward.yaml"
    _write_config(cfg)
    provider = FakeForwardProvider(["20240101", "20240103", "20240104", "20240105"])
    now = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)

    fpr.run_forward_paper_once(cfg, tmp_path, now=now, provider=provider)
    fpr.run_forward_paper_once(cfg, tmp_path, now=now, provider=provider)

    events = [
        json.loads(line)
        for line in (tmp_path / "runs/forward_test/event_log.jsonl").read_text().splitlines()
        if line.strip()
    ]
    activation_events = [e for e in events if e["event_type"] == "forward_tracking_activated"]
    assert len(activation_events) == 1
