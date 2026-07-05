from __future__ import annotations

from dataclasses import replace

from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.expression import Expression
from ashare_research.mining.reward import reward_from_metrics


class ValidationEvaluator:
    split_name = "validation"

    def __init__(self, provider: LocalSQLiteProvider, base_config: BacktestConfig, split: tuple[str, str], min_trade_count: int):
        self.provider = provider
        self.config = replace(base_config, start_date=split[0], end_date=split[1])
        self.min_trade_count = int(min_trade_count)

    def evaluate(self, expression: Expression) -> tuple[dict, float, str]:
        result = DeterministicBacktestEngine(self.provider, self.config).run(expression)
        reward = reward_from_metrics(result["metrics"], min_trade_count=self.min_trade_count)
        return result["metrics"], reward.reward, str(result["run_dir"])
