from pathlib import Path

from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression
from ashare_research.mining.model import PositionLogitGenerator, TOKEN_NAMES, UniformRandomGenerator
from ashare_research.mining.stage3_5 import SyntheticMomentumProvider, synthetic_backtest_config
from ashare_research.mining.stage3_6 import FullBacktestBatchEvaluator, generate_unique


def test_uniform_random_only_generates_legal_formulas() -> None:
    generator = UniformRandomGenerator(seed=1)

    for _ in range(50):
        expr = generator.generate().expression
        assert expr.validate() == (True, None)


def test_generators_use_same_formula_space() -> None:
    assert set(TOKEN_NAMES)
    assert PositionLogitGenerator(seed=1).logits.shape[1] == len(TOKEN_NAMES)
    assert UniformRandomGenerator(seed=1).logits.shape[1] == len(TOKEN_NAMES)


def test_unique_formula_budget_ignores_duplicates() -> None:
    formulas, generated_count, duplicate_count = generate_unique(UniformRandomGenerator(seed=11), 25)

    assert len(formulas) == 25
    assert generated_count >= 25
    assert duplicate_count == generated_count - 25


def test_batch_evaluator_matches_independent_stage2(tmp_path: Path) -> None:
    provider = SyntheticMomentumProvider()
    config = synthetic_backtest_config(tmp_path / "independent")
    expr = Expression(("RET1",))
    independent = DeterministicBacktestEngine(provider, config).run(expr)

    batch_config = synthetic_backtest_config(tmp_path / "batch")
    batch = FullBacktestBatchEvaluator(provider, batch_config, min_trade_count=1, keep_details=True).evaluate(expr)

    assert batch.metrics["net_return"] == independent["metrics"]["net_return"]
    assert batch.metrics["sortino"] == independent["metrics"]["sortino"]
    assert batch.metrics["max_drawdown"] == independent["metrics"]["max_drawdown"]
    assert batch.metrics["cumulative_cost"] == independent["metrics"]["cumulative_cost"]
    assert batch.metrics["unfilled_buy_count"] == independent["metrics"]["unfilled_buy_count"]


def test_same_seed_unique_sequence_reproducible() -> None:
    a = [expr.normalized() for expr in generate_unique(UniformRandomGenerator(seed=23), 30)[0]]
    b = [expr.normalized() for expr in generate_unique(UniformRandomGenerator(seed=23), 30)[0]]

    assert a == b
