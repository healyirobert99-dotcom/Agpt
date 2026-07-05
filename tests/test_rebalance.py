from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, make_backtest_config


def test_rebalance_creates_multiple_signal_dates(tmp_path) -> None:
    engine = DeterministicBacktestEngine(FakeProvider(), make_backtest_config(tmp_path))

    result = engine.run(Expression(("RET1",)))
    planned = __import__("pandas").read_csv(f"{result['run_dir']}/planned_orders.csv", dtype={"signal_date": str, "planned_trade_date": str})

    assert set(planned["signal_date"]) == {"20240108", "20240115"}
    assert set(planned["planned_trade_date"]) == {"20240109", "20240116"}
