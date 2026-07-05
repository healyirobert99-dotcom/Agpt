from pathlib import Path

import pytest

from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.factors.expression import Expression

from .backtest_fixtures import FakeProvider, DATES


def test_output_size_failure_cleans_temp_run_dir(tmp_path: Path) -> None:
    cfg = BacktestConfig(
        start_date=DATES[0],
        end_date=DATES[-1],
        rebalance_frequency=5,
        top_n=3,
        initial_cash=10000.0,
        cost_bps=20.0,
        unknown_tradability_policy="reject_trade",
        runs_dir=str(tmp_path / "runs"),
        temp_dir=str(tmp_path / "runs" / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=0.0,
    )

    with pytest.raises(RuntimeError, match="estimated_run_output_exceeds_limit"):
        DeterministicBacktestEngine(FakeProvider(), cfg).run(Expression(("RET1",)))

    tmp_dir = tmp_path / "runs" / "tmp"
    assert tmp_dir.exists()
    assert list(tmp_dir.iterdir()) == []
