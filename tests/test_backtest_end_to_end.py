import json
from pathlib import Path

import pandas as pd

from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, make_backtest_config


def test_manual_market_case_is_auditable_line_by_line(tmp_path: Path) -> None:
    result = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path)).run(Expression(("RET1",)))
    run_dir = Path(result["run_dir"])

    planned = pd.read_csv(run_dir / "planned_orders.csv", dtype={"signal_date": str, "planned_trade_date": str})
    executions = pd.read_csv(run_dir / "executions.csv", dtype={"actual_trade_date": str, "signal_date": str, "planned_trade_date": str})
    account = pd.read_csv(run_dir / "daily_account.csv", dtype={"trade_date": str})
    holdings = pd.read_csv(run_dir / "daily_holdings.csv", dtype={"trade_date": str})
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    report = (run_dir / "report.md").read_text(encoding="utf-8")

    first_plan = planned[planned["signal_date"] == "20240108"]
    assert list(first_plan.sort_values(["rank", "ts_code"])["ts_code"]) == ["300001.SZ", "000001.SZ", "600001.SH"]
    assert (first_plan[first_plan["ts_code"] == "000001.SZ"]["target_quantity"].iloc[0]) == 300
    assert bool(first_plan[first_plan["ts_code"] == "300001.SZ"]["historical_is_st"].iloc[0]) is True

    normal_buy = executions[(executions["actual_trade_date"] == "20240109") & (executions["ts_code"] == "000001.SZ")].iloc[0]
    assert normal_buy["status"] == "filled"
    assert normal_buy["executed_quantity"] == 300
    assert normal_buy["transaction_cost"] == 6.54

    limit_buy = executions[(executions["actual_trade_date"] == "20240109") & (executions["ts_code"] == "300001.SZ")].iloc[0]
    assert limit_buy["status"] == "unfilled"
    assert limit_buy["unfilled_reason"] == "limit_up_open"

    missing_buy = executions[(executions["actual_trade_date"] == "20240116") & (executions["ts_code"] == "688001.SH")].iloc[0]
    assert missing_buy["status"] == "unfilled"
    assert missing_buy["unfilled_reason"] == "missing_bar_on_open_day"

    blocked_sell = executions[(executions["actual_trade_date"] == "20240116") & (executions["ts_code"] == "600001.SH")].iloc[0]
    assert blocked_sell["status"] == "unfilled"
    assert blocked_sell["unfilled_reason"] == "limit_down_open"

    first_account_after_trade = account[account["trade_date"] == "20240109"].iloc[0]
    assert first_account_after_trade["cash"] == 3567.16
    assert first_account_after_trade["cumulative_cost"] == 12.84
    assert set(holdings[holdings["trade_date"] == "20240109"]["ts_code"]) == {"000001.SZ", "600001.SH"}
    assert metrics["benchmark"]["benchmark_unavailable"] is True
    assert "ENGINEERING BACKTEST ONLY" in report
    assert "NOT A VALIDATED INVESTMENT STRATEGY" in report
    assert "B-READY DATA WITH APPROXIMATE TRADABILITY" in report
