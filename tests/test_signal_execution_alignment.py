import pandas as pd

from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, make_backtest_config


def test_signal_date_is_before_actual_trade_date(tmp_path) -> None:
    result = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path)).run(Expression(("RET1",)))

    planned = pd.read_csv(f"{result['run_dir']}/planned_orders.csv", dtype=str)
    executions = pd.read_csv(f"{result['run_dir']}/executions.csv", dtype=str)

    assert (planned["signal_date"] < planned["planned_trade_date"]).all()
    assert (executions["signal_date"] < executions["actual_trade_date"]).all()
    assert set(executions["actual_trade_date"]) == {"20240109", "20240116"}
