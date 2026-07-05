from pathlib import Path

import pandas as pd

from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, make_backtest_config


def _run(provider: FakeProvider, tmp_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = DeterministicBacktestEngine(provider, make_backtest_config(tmp_path)).run(Expression(("RET1",)))
    planned = pd.read_csv(Path(result["run_dir"]) / "planned_orders.csv", dtype=str)
    executions = pd.read_csv(Path(result["run_dir"]) / "executions.csv", dtype=str)
    return planned, executions


def test_changing_next_open_does_not_change_signal_plan_quantity(tmp_path) -> None:
    baseline_plan, _ = _run(FakeProvider(), tmp_path / "base")
    changed = FakeProvider()
    changed.bars.loc[(changed.bars["trade_date"] == "20240109") & (changed.bars["ts_code"] == "000001.SZ"), "raw_open"] = 99.0

    changed_plan, _ = _run(changed, tmp_path / "changed")

    base_first = baseline_plan[baseline_plan["signal_date"] == "20240108"].sort_values(["rank", "ts_code"]).reset_index(drop=True)
    changed_first = changed_plan[changed_plan["signal_date"] == "20240108"].sort_values(["rank", "ts_code"]).reset_index(drop=True)
    assert list(base_first["ts_code"]) == list(changed_first["ts_code"])
    assert list(base_first["target_quantity"]) == list(changed_first["target_quantity"])


def test_future_limit_and_st_changes_do_not_rewrite_past_trades(tmp_path) -> None:
    baseline_plan, baseline_exec = _run(FakeProvider(), tmp_path / "base")
    changed = FakeProvider()
    changed.limits.loc[changed.limits["trade_date"] == "20240116", "limit_derivation_status"] = "special_case_unknown"
    changed.st_status.loc[:, "start_date"] = "20240110"
    changed.constituents.loc[changed.constituents["effective_trade_date"] == "20240116", "ts_code"] = "999999.SH"

    changed_plan, changed_exec = _run(changed, tmp_path / "changed")

    past_plan = baseline_plan[baseline_plan["signal_date"] == "20240108"].sort_values(["ts_code"]).reset_index(drop=True)
    changed_past_plan = changed_plan[changed_plan["signal_date"] == "20240108"].sort_values(["ts_code"]).reset_index(drop=True)
    past_exec = baseline_exec[baseline_exec["actual_trade_date"] == "20240109"].sort_values(["ts_code"]).reset_index(drop=True)
    changed_past_exec = changed_exec[changed_exec["actual_trade_date"] == "20240109"].sort_values(["ts_code"]).reset_index(drop=True)

    assert list(past_plan["ts_code"]) == list(changed_past_plan["ts_code"])
    assert list(past_exec["status"]) == list(changed_past_exec["status"])
    assert list(past_exec["unfilled_reason"].fillna("")) == list(changed_past_exec["unfilled_reason"].fillna(""))
