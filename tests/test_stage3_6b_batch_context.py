from pathlib import Path

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.factors.expression import Expression
from ashare_research.mining.stage3_5 import SyntheticMomentumProvider, synthetic_backtest_config


def test_research_context_limits_dates_and_computes_features_once(tmp_path: Path) -> None:
    provider = SyntheticMomentumProvider()
    cfg = synthetic_backtest_config(tmp_path)
    progress = tmp_path / "context_progress.json"
    ctx = ResearchContext.build(provider, cfg, progress_path=progress)

    assert min(ctx.bars["trade_date"]) >= cfg.start_date
    assert max(ctx.bars["trade_date"]) <= cfg.end_date
    assert "RET1" in ctx.features.columns
    assert ctx.profile["base_features_seconds"] >= 0
    assert progress.exists()
    assert "context_hash_completed" in progress.read_text(encoding="utf-8")


def test_batch_result_matches_stage2_and_accounts_are_isolated(tmp_path: Path) -> None:
    provider = SyntheticMomentumProvider()
    cfg = synthetic_backtest_config(tmp_path / "cfg")
    ctx = ResearchContext.build(provider, cfg)
    evaluator = BatchBacktestEvaluator(ctx)
    expr = Expression(("RET1",))

    batch_a = evaluator.evaluate(expr)
    batch_b = evaluator.evaluate(Expression(("RET5",)))
    independent = DeterministicBacktestEngine(provider, cfg).run(expr)

    assert batch_a.metrics["net_return"] == independent["metrics"]["net_return"]
    assert batch_a.metrics["sortino"] == independent["metrics"]["sortino"]
    assert batch_a.accounts["cash"].iloc[0] == batch_b.accounts["cash"].iloc[0]


def test_summary_only_does_not_leave_detail_files_and_dedups(tmp_path: Path) -> None:
    provider = SyntheticMomentumProvider()
    cfg = synthetic_backtest_config(tmp_path / "cfg")
    ctx = ResearchContext.build(provider, cfg)
    detail = tmp_path / "details"
    evaluator = BatchBacktestEvaluator(ctx, save_detail_policy="summary_only", run_dir=detail)
    expr = Expression(("RET1",))

    first = evaluator.evaluate(expr)
    second = evaluator.evaluate(expr)

    assert first is second
    assert not detail.exists()
