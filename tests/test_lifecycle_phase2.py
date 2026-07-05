import pandas as pd

from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, make_backtest_config


def test_not_yet_listed_member_is_excluded_from_portfolio(tmp_path) -> None:
    provider = FakeProvider()
    provider.lifecycle.loc[provider.lifecycle["ts_code"] == "300001.SZ", "list_date"] = "20240110"

    result = DeterministicBacktestEngine(provider, make_backtest_config(tmp_path, top_n=2)).run(Expression(("RET1",)))
    planned = pd.read_csv(f"{result['run_dir']}/planned_orders.csv", dtype=str)

    first_signal = planned[planned["signal_date"] == "20240108"]
    assert "300001.SZ" not in set(first_signal["ts_code"])
