from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.backtest.records import ExternalTarget
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, make_backtest_config


def _target(
    window_id: str,
    signal_date: str,
    entry_date: str,
    exit_date: str,
    ts_code: str,
    *,
    weight: float = 0.30,
    rank: int = 1,
) -> ExternalTarget:
    return ExternalTarget(
        window_id=window_id,
        signal_date=signal_date,
        entry_date=entry_date,
        planned_exit_date=exit_date,
        ts_code=ts_code,
        target_weight=weight,
        factor_value=1.0 / rank,
        rank=rank,
    )


def test_external_target_schedule_normal_entry_and_exit(tmp_path: Path) -> None:
    engine = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path))
    result = engine.run_external_target_schedule([
        _target("w1", "20240105", "20240108", "20240115", "000001.SZ")
    ])

    planned = result["planned"]
    trades = result["trades"]
    accounts = result["accounts"]
    holdings = result["holdings"]

    assert len(planned) == 1
    assert planned.iloc[0]["planned_quantity"] % 100 == 0
    assert planned.iloc[0]["window_id"] == "w1"
    assert planned.iloc[0]["order_purpose"] == "entry"
    assert set(trades["order_purpose"]) == {"entry", "exit"}
    assert list(trades["status"]) == ["filled", "filled"]
    assert all(trades["transaction_cost"] > 0)
    assert len(accounts) == len(FakeProvider().calendar)
    assert "total_equity" in accounts.columns
    assert "market_value" in holdings.columns


def test_external_target_schedule_records_failures(tmp_path: Path) -> None:
    engine = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path))
    result = engine.run_external_target_schedule([
        _target("limit-up", "20240108", "20240109", "20240110", "300001.SZ"),
        _target("missing-open", "20240115", "20240116", "20240116", "688001.SH"),
        _target("cash", "20240108", "20240109", "20240110", "000001.SZ", weight=2.0),
    ])

    trades = result["trades"]
    reasons = set(trades["unfilled_reason"].dropna())
    assert "limit_up_open" in reasons
    assert "missing_bar_on_open_day" in reasons
    assert "insufficient_cash" in reasons
    assert set(trades[trades["status"] == "unfilled"]["window_id"]) == {"limit-up", "missing-open", "cash"}


def test_external_target_schedule_delays_unfilled_exit(tmp_path: Path) -> None:
    engine = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path))
    result = engine.run_external_target_schedule([
        _target("delayed-exit", "20240108", "20240109", "20240116", "600001.SH")
    ])

    trades = result["trades"]
    exit_rows = trades[trades["order_purpose"] == "exit"]
    assert len(exit_rows) == 1
    assert exit_rows.iloc[0]["status"] == "unfilled"
    assert exit_rows.iloc[0]["unfilled_reason"] == "limit_down_open"


def test_external_target_schedule_same_stock_exit_then_reentry(tmp_path: Path) -> None:
    engine = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path))
    result = engine.run_external_target_schedule([
        _target("week-1", "20240105", "20240108", "20240115", "000001.SZ"),
        _target("week-2", "20240112", "20240115", "20240116", "000001.SZ"),
    ])

    trades = result["trades"]
    same_day = trades[(trades["actual_trade_date"] == "20240115") & (trades["ts_code"] == "000001.SZ")]
    assert list(same_day["side"]) == ["sell", "buy"]
    assert list(same_day["window_id"]) == ["week-1", "week-2"]
    assert list(same_day["order_purpose"]) == ["exit", "entry"]
    assert all(same_day["transaction_cost"] > 0)


def test_legacy_single_formula_path_regression(tmp_path: Path) -> None:
    engine = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path))
    result = engine.run(Expression(("RET1",)))
    run_dir = Path(result["run_dir"])

    import pandas as pd

    planned = pd.read_csv(run_dir / "planned_orders.csv", dtype={"signal_date": str, "planned_trade_date": str})
    executions = pd.read_csv(run_dir / "executions.csv", dtype={"actual_trade_date": str})
    account = pd.read_csv(run_dir / "daily_account.csv", dtype={"trade_date": str})

    first_plan = planned[planned["signal_date"] == "20240108"]
    assert list(first_plan.sort_values(["rank", "ts_code"])["ts_code"]) == ["300001.SZ", "000001.SZ", "600001.SH"]
    assert int(first_plan[first_plan["ts_code"] == "000001.SZ"]["target_quantity"].iloc[0]) == 300
    normal_buy = executions[(executions["actual_trade_date"] == "20240109") & (executions["ts_code"] == "000001.SZ")].iloc[0]
    assert normal_buy["status"] == "filled"
    assert normal_buy["transaction_cost"] == pytest.approx(6.54)
    assert float(account[account["trade_date"] == "20240109"]["cash"].iloc[0]) == pytest.approx(3567.16)


def test_b_v1_does_not_own_phase2_execution_state() -> None:
    from ashare_research.mining import b_v1_executor

    source = inspect.getsource(b_v1_executor.CompositeBacktestExecutor)
    assert "Account(" not in source
    assert "_execute_one" not in source
    assert "mark_to_market" not in source
    assert "refresh_available" not in source
    assert "transaction_cost" not in source
