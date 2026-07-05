from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.mining.new_unseen_runner import atomic_write_json
from ashare_research.recommendation.protocol_b_v1 import EXPECTED_FORMULA_HASHES, PROTOCOL_ID


STRATEGY_VERSION = "b_v1_forward_paper_v1"
TRACKER_RUN_DIR = Path("runs/forward_paper_tracking_b_v1_20260627")
LOG_FILES = (
    "event_log.jsonl",
    "signal_snapshots.jsonl",
    "target_orders.jsonl",
    "paper_executions.jsonl",
    "window_status.jsonl",
    "daily_nav.jsonl",
    "errors.jsonl",
)


@dataclass(frozen=True)
class ForwardPaperResult:
    run_dir: str
    activation_status: str
    activation_requested_at: str | None
    activation_gate_passed_at: str | None
    activated_at: str | None
    activation_date: str | None
    next_eligible_signal_date: str | None
    calendar_ready: bool
    daily_data_ready: bool
    activation_gate_passed: bool
    due_event_found: bool
    signal_generated: bool
    paper_order_generated: bool
    paper_execution_generated: bool
    data_available_through: str | None
    data_snapshot_hash: str | None
    validation_accessed: bool = False
    blind_test_accessed: bool = False


def run_forward_paper_once(
    config_path: str | Path,
    repo_root: str | Path,
    *,
    now: datetime | None = None,
    provider: LocalSQLiteProvider | None = None,
) -> dict[str, Any]:
    """Advance the B-v1.0 forward paper tracker by one idempotent step."""
    repo = Path(repo_root)
    cfg_path = Path(config_path)
    if not cfg_path.is_absolute():
        cfg_path = repo / cfg_path
    cfg = load_simple_yaml(cfg_path)
    _validate_forward_config(cfg)

    run_dir = repo / TRACKER_RUN_DIR
    run_dir.mkdir(parents=True, exist_ok=True)
    _ensure_logs(run_dir)

    state_path = run_dir / "state.json"
    state = _read_json(state_path) if state_path.exists() else {}
    now = now or datetime.now(timezone(timedelta(hours=8)))
    now_text = now.isoformat()
    activation_requested_at = (
        state.get("activation_requested_at")
        or cfg.get("activation_requested_at")
        or state.get("activated_at")
        or cfg.get("activated_at")
        or now_text
    )
    prior_active = state.get("activation_status") == "active" and state.get("activation_date")
    activated_at = state.get("activated_at") if prior_active else None
    local_date = now.strftime("%Y%m%d")

    if provider is None:
        data_cfg = cfg.get("data", {})
        sqlite_path = repo / str(data_cfg.get("sqlite_path", "stock-data/ashare_research.sqlite3"))
        raw_path = repo / str(data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"))
        provider = LocalSQLiteProvider(sqlite_path, raw_path)

    initial_capital = _resolve_initial_capital(cfg, repo)
    source_commit = _git_output(repo, ["git", "rev-parse", "HEAD"])
    git_status = _git_output(repo, ["git", "status", "--short"])
    tracked_hashes = _tracked_file_hashes(repo)
    activation_request_date = _date_from_timestamp(str(activation_requested_at)) or local_date
    request_calendar = _calendar_after_activation(provider, activation_request_date)
    gate_calendar = _calendar_after_activation(provider, local_date)
    data_available = _data_available_through(provider)
    first_open_after_request = request_calendar[0] if request_calendar else None
    calendar_available_through = request_calendar[-1] if request_calendar else _calendar_available_through(provider)
    calendar_ready = bool(first_open_after_request and gate_calendar)
    daily_data_ready = bool(data_available and _date_in_calendar(provider, data_available) and data_available <= local_date)
    activation_gate_passed = calendar_ready and daily_data_ready
    activation_gate_passed_at = state.get("activation_gate_passed_at") if prior_active else None
    activation_date = state.get("activation_date") if prior_active else None
    if activation_gate_passed and not activation_date:
        activation_gate_passed_at = now_text
        activation_date = gate_calendar[0]
        activated_at = now_text
    activation_status = "active" if activation_date and activation_gate_passed else "pending_data_update"
    next_signal = _next_weekly_signal_date(gate_calendar, activation_date) if activation_status == "active" else None
    data_available = _data_available_through(provider)
    data_snapshot_hash = _stable_hash({
        "calendar": request_calendar,
        "data_available_through": data_available,
        "source_commit": source_commit,
    })

    base_state = {
        **state,
        "protocol_id": PROTOCOL_ID,
        "strategy_version": STRATEGY_VERSION,
        "activation_status": activation_status,
        "activation_requested_at": activation_requested_at,
        "activation_gate_passed_at": activation_gate_passed_at,
        "activated_at": activated_at,
        "activation_date": activation_date,
        "activation_calendar_source": "calendar_open_days",
        "next_eligible_signal_date": next_signal,
        "source_commit": source_commit,
        "git_worktree_clean": git_status == "",
        "tracked_file_hashes": tracked_hashes,
        "initial_capital": initial_capital,
        "data_cutoff_rule": "signal_after_close_and_daily_bar_ready_no_backfill",
        "timezone": "Asia/Shanghai",
        "data_available_through": data_available,
        "calendar_source": "calendar_open_days",
        "calendar_available_through": calendar_available_through,
        "first_open_date_after_activation_request": first_open_after_request,
        "calendar_ready": calendar_ready,
        "daily_data_ready": daily_data_ready,
        "activation_gate_passed": activation_gate_passed,
        "data_snapshot_hash": data_snapshot_hash,
        "data_cutoff_timestamp": now_text,
        "calendar_snapshot_hash": _stable_hash(request_calendar),
        "backfill_allowed": False,
        "historical_replay_allowed": False,
        "validation_access_allowed": False,
        "blind_test_access_allowed": False,
        "auto_trading_enabled": False,
        "broker_connection_enabled": False,
        "historical_signal_generated": False,
        "historical_order_generated": False,
        "historical_execution_generated": False,
    }

    if not prior_active:
        _append_unique_event(run_dir / "event_log.jsonl", {
            "event_id": (
                f"{PROTOCOL_ID}:activation:"
                f"{activated_at or activation_requested_at}:"
                f"{_stable_hash(cfg)[:12]}:"
                f"{str(tracked_hashes.get('ashare_research/mining/forward_paper_runner.py'))[:12]}"
            ),
            "event_type": "forward_tracking_activated" if activation_status == "active" else "activation_pending",
            "created_at": now_text,
            "input_hash": _stable_hash({"config": cfg, "source_commit": source_commit}),
            "strategy_version": STRATEGY_VERSION,
            "activation_status": activation_status,
            "activation_requested_at": activation_requested_at,
            "activation_gate_passed_at": activation_gate_passed_at,
            "activated_at": activated_at,
            "activation_date": activation_date,
            "next_eligible_signal_date": next_signal,
            "source_commit": source_commit,
            "calendar_snapshot_hash": _stable_hash(request_calendar),
            "data_snapshot_hash": data_snapshot_hash,
        })

    due = _due_signal_event(next_signal, local_date, data_available, run_dir)
    result_payload = {
        "event_id": f"{PROTOCOL_ID}:due_check:{now.strftime('%Y%m%dT%H%M%S')}",
        "event_type": "due_check",
        "created_at": now_text,
        "input_hash": _stable_hash({
            "activation_date": activation_date,
            "next_signal": next_signal,
            "data_available_through": data_available,
            "source_commit": source_commit,
        }),
        "strategy_version": STRATEGY_VERSION,
        "due_event_found": due["due_event_found"],
        "reason": due["reason"],
    }
    _append_unique_event(run_dir / "event_log.jsonl", result_payload)

    signal_generated = False
    paper_order_generated = False
    paper_execution_generated = False
    if due["reason"] == "missed_signal_cycle":
        _append_unique_event(run_dir / "errors.jsonl", {
            "event_id": f"{PROTOCOL_ID}:missed_signal_cycle:{next_signal}",
            "event_type": "missed_signal_cycle",
            "created_at": now_text,
            "input_hash": _stable_hash({"next_signal": next_signal, "today": local_date}),
            "strategy_version": STRATEGY_VERSION,
            "signal_date": next_signal,
        })

    final_state = {
        **base_state,
        "status": "active_waiting_for_forward_signal" if activation_status == "active" else "pending_data_update",
        "current_stock_recommendation_generated": signal_generated,
        "recommendations_generated": signal_generated,
        "paper_order_generated": paper_order_generated,
        "paper_execution_generated": paper_execution_generated,
        "last_due_check_at": now_text,
        "last_due_check_reason": due["reason"],
        "next_step": "wait_for_data_update" if activation_status != "active" else "wait_for_due_forward_event",
    }
    atomic_write_json(state_path, final_state)
    return ForwardPaperResult(
        run_dir=str(run_dir),
        activation_status=activation_status,
        activation_requested_at=activation_requested_at,
        activation_gate_passed_at=activation_gate_passed_at,
        activated_at=activated_at,
        activation_date=activation_date,
        next_eligible_signal_date=next_signal,
        calendar_ready=calendar_ready,
        daily_data_ready=daily_data_ready,
        activation_gate_passed=activation_gate_passed,
        due_event_found=bool(due["due_event_found"]),
        signal_generated=signal_generated,
        paper_order_generated=paper_order_generated,
        paper_execution_generated=paper_execution_generated,
        data_available_through=data_available,
        data_snapshot_hash=data_snapshot_hash,
    ).__dict__


def build_signal_snapshot_record(
    *,
    signal_date: str,
    data_available_through: str,
    data_snapshot_hash: str,
    formula_status: list[dict[str, Any]],
    selected_targets: list[dict[str, Any]],
    source_commit: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "event_id": f"{PROTOCOL_ID}:{signal_date}",
        "signal_event_id": f"{PROTOCOL_ID}:{signal_date}",
        "signal_date": signal_date,
        "generated_at": created_at,
        "created_at": created_at,
        "strategy_version": STRATEGY_VERSION,
        "source_commit": source_commit,
        "data_available_through": data_available_through,
        "data_snapshot_hash": data_snapshot_hash,
        "formula_hashes": list(EXPECTED_FORMULA_HASHES),
        "formula_status": formula_status,
        "formula_values_snapshot_hash": _stable_hash(formula_status),
        "selected_top_5": selected_targets,
        "target_count": len(selected_targets),
        "input_hash": _stable_hash({
            "signal_date": signal_date,
            "data_snapshot_hash": data_snapshot_hash,
            "selected_targets": selected_targets,
        }),
    }


def summarize_completed_window_returns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        float(r["net_return_after_cost"])
        for r in rows
        if r.get("status") == "exit_completed" and r.get("net_return_after_cost") is not None
    ]
    return {
        "completed_window_count": len(completed),
        "winning_completed_window_count": sum(1 for v in completed if v > 0),
        "window_win_rate": (sum(1 for v in completed if v > 0) / len(completed)) if completed else None,
    }


def _validate_forward_config(cfg: dict[str, Any]) -> None:
    data_policy = cfg.get("data_policy", {})
    for key in ("backfill_allowed", "historical_replay_allowed", "validation_access_allowed", "blind_test_access_allowed"):
        if data_policy.get(key) is not False:
            raise ValueError(f"forward_guardrail_not_false:{key}")


def _resolve_initial_capital(cfg: dict[str, Any], repo: Path) -> float:
    value = cfg.get("initial_capital") or cfg.get("backtest", {}).get("initial_cash")
    if value is None:
        fallback = repo / "config/search_benchmark_completed100_gate.yaml"
        if fallback.exists():
            value = load_simple_yaml(fallback).get("backtest", {}).get("initial_cash")
    if value is None:
        raise ValueError("missing_initial_capital")
    return float(value)


def _calendar_after_activation(provider: LocalSQLiteProvider, local_date: str) -> list[str]:
    end = (datetime.strptime(local_date, "%Y%m%d") + timedelta(days=370)).strftime("%Y%m%d")
    cal = provider.get_trade_calendar(local_date, end)
    if cal.empty:
        return []
    return [str(d) for d in cal["trade_date"].astype(str) if str(d) > local_date]


def _calendar_available_through(provider: LocalSQLiteProvider) -> str | None:
    path = getattr(provider, "research_sqlite_path", None)
    if path is None:
        return None
    import sqlite3

    with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as con:
        row = con.execute("SELECT MAX(trade_date) FROM calendar_open_days").fetchone()
    return str(row[0]) if row and row[0] else None


def _date_in_calendar(provider: LocalSQLiteProvider, trade_date: str) -> bool:
    cal = provider.get_trade_calendar(trade_date, trade_date)
    return not cal.empty and str(cal.iloc[0]["trade_date"]) == trade_date


def _date_from_timestamp(value: str) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value[:10] if ch.isdigit())
    return digits if len(digits) == 8 else None


def _next_weekly_signal_date(calendar: list[str], activation_date: str | None) -> str | None:
    if not activation_date:
        return None
    eligible = [d for d in calendar if d >= activation_date]
    if not eligible:
        return None
    weeks: dict[tuple[int, int], list[str]] = {}
    for d in eligible:
        parsed = datetime.strptime(d, "%Y%m%d")
        weeks.setdefault((parsed.year, parsed.isocalendar()[1]), []).append(d)
    first_key = sorted(weeks)[0]
    return weeks[first_key][-1]


def _data_available_through(provider: LocalSQLiteProvider) -> str | None:
    path = getattr(provider, "research_sqlite_path", None)
    if path is None:
        return None
    import sqlite3

    with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as con:
        row = con.execute("SELECT MAX(trade_date) FROM daily_price WHERE source = 'tushare_raw'").fetchone()
    return str(row[0]) if row and row[0] else None


def _due_signal_event(next_signal: str | None, local_date: str, data_available: str | None, run_dir: Path) -> dict[str, Any]:
    if not next_signal:
        return {"due_event_found": False, "reason": "no_eligible_signal_date"}
    if _event_exists(run_dir / "signal_snapshots.jsonl", f"{PROTOCOL_ID}:{next_signal}"):
        return {"due_event_found": False, "reason": "signal_already_generated"}
    if local_date < next_signal:
        return {"due_event_found": False, "reason": "not_due_yet"}
    if data_available is None or data_available < next_signal:
        return {"due_event_found": False, "reason": "daily_bar_not_ready"}
    if local_date > next_signal:
        return {"due_event_found": False, "reason": "missed_signal_cycle"}
    return {"due_event_found": True, "reason": "signal_due"}


def _ensure_logs(run_dir: Path) -> None:
    for name in LOG_FILES:
        (run_dir / name).touch(exist_ok=True)


def _append_unique_event(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event_id = str(record["event_id"])
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if str(existing.get("event_id")) == event_id:
                existing_payload = json.dumps(existing, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if existing_payload != payload:
                    raise ValueError(f"integrity_conflict:{event_id}")
                return
    with path.open("a", encoding="utf-8") as fh:
        fh.write(payload + "\n")


def _event_exists(path: Path, event_id: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and str(json.loads(line).get("event_id")) == event_id:
            return True
    return False


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tracked_file_hashes(repo: Path) -> dict[str, str | None]:
    files = [
        "config/forward_paper_tracking_b_v1.yaml",
        "config/trade_recommendation_protocol_b_v1.yaml",
        "ashare_research/mining/forward_paper_runner.py",
        "ashare_research/mining/new_unseen_runner.py",
        "ashare_research/mining/b_v1_executor.py",
        "ashare_research/backtest/engine.py",
        "ashare_research/recommendation/protocol_b_v1.py",
    ]
    return {name: _file_sha256(repo / name) if (repo / name).exists() else None for name in files}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _git_output(repo: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(args, cwd=repo, text=True).strip()
    except Exception:
        return ""
