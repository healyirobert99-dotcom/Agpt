from pathlib import Path

from ashare_research.backtest.progress import FormulaProgressStore
from ashare_research.factors.expression import Expression
from ashare_research.mining.model import GeneratedFormula, UniformRandomGenerator
from ashare_research.mining.stage3_6c2 import (
    CompletedBudgetConfig,
    budget_counts,
    continuous_generation_reference,
    generate_until_completed,
    should_stop,
)


class FakeResult:
    def __init__(self, sortino=1.0, failure_reason=None):
        self.metrics = {"sortino": sortino, "trade_count": 1} if failure_reason is None else {"status": "failed", "failure_reason": failure_reason}
        self.failure_reason = failure_reason


class FakeEvaluator:
    def __init__(self, failures=None):
        self.failures = failures or {}
        self.calls = []

    def evaluate(self, expr):
        self.calls.append(expr.sha256())
        reason = self.failures.get(expr.to_string())
        return FakeResult(failure_reason=reason)


class FixedGenerator:
    def __init__(self, expressions):
        self.expressions = list(expressions)
        self.index = 0

    def state_dict(self):
        return {"index": self.index, "expressions": [expr.tokens for expr in self.expressions]}

    def generate(self):
        expr = self.expressions[self.index]
        self.index += 1
        return GeneratedFormula(expr, [])


def _manifest():
    return {
        "run_id": "unit",
        "context_hash": "ctx",
        "config_hash": "cfg",
        "data_snapshot_hash": "data",
        "feature_version": "feature",
        "operator_version": "operator",
        "universe_version": "universe",
        "tradability_rule_version": "tradability",
        "price_policy_version": "price",
        "code_commit": "commit",
    }


def _budget(**overrides):
    data = dict(
        completed_full_backtest_target=2,
        max_unique_formula_attempts=4,
        max_generation_attempts=10,
        seed=101,
        save_detail_policy="summary_only",
    )
    data.update(overrides)
    return CompletedBudgetConfig(**data)


def test_budget_counts_completed_only_and_failed_separate(tmp_path: Path) -> None:
    store = FormulaProgressStore(tmp_path, _manifest())
    store.initialize_queue([("h1", "RET1"), ("h2", "RET5")])
    store.mark_running("h1")
    store.mark_completed("h1", {"formula_hash": "h1", "metrics": {"sortino": 1.0}})
    store.mark_running("h2")
    store.mark_failed("h2", "invalid_formula:constant_or_all_missing")

    counts = budget_counts(store.load())

    assert counts["completed_full_backtest_count"] == 1
    assert counts["failed_count"] == 1
    assert counts["formula_execution_invalid_count"] == 1
    assert counts["unique_formula_attempt_count"] == 2


def test_stop_conditions_distinguish_completed_unique_and_generation() -> None:
    cfg = _budget(completed_full_backtest_target=2, max_unique_formula_attempts=3, max_generation_attempts=5)

    assert should_stop({"completed_full_backtest_count": 2, "unique_formula_attempt_count": 2}, 2, cfg)[1] == "completed_full_backtest_target_reached"
    assert should_stop({"completed_full_backtest_count": 1, "unique_formula_attempt_count": 3}, 3, cfg)[1] == "max_unique_formula_attempts_reached"
    assert should_stop({"completed_full_backtest_count": 1, "unique_formula_attempt_count": 2}, 5, cfg)[1] == "max_generation_attempts_reached"


def test_failed_and_duplicate_do_not_consume_completed_budget(tmp_path: Path) -> None:
    exprs = [
        Expression(("RET1",)),
        Expression(("RET1",)),
        Expression(("RET5",)),
        Expression(("TREND60",)),
    ]
    store = FormulaProgressStore(tmp_path, _manifest())
    evaluator = FakeEvaluator(failures={"RET5": "invalid_formula:constant_or_all_missing"})

    result = generate_until_completed(
        generator=FixedGenerator(exprs),
        evaluator=evaluator,  # type: ignore[arg-type]
        store=store,
        config=_budget(completed_full_backtest_target=2, max_unique_formula_attempts=4, max_generation_attempts=4),
        run_dir=tmp_path,
    )
    counts = budget_counts(store.load())

    assert counts["completed_full_backtest_count"] == 2
    assert counts["failed_count"] == 1
    assert result["duplicate_count"] == 1
    assert result["stop_reason"] == "completed_full_backtest_target_reached"


def test_rng_state_restores_generation_sequence() -> None:
    cfg = _budget(seed=101)
    continuous = continuous_generation_reference(cfg, 8)
    generator = UniformRandomGenerator(seed=101)
    first = [generator.generate().expression for _ in range(3)]
    state = generator.state_dict()
    restored = UniformRandomGenerator.from_state_dict(state)
    second = [restored.generate().expression for _ in range(5)]
    resumed = [{"formula_hash": expr.sha256(), "formula_text": expr.to_string(), "tokens": list(expr.tokens)} for expr in first + second]

    assert resumed == continuous


def test_stage3_6c2_does_not_import_position_logit_symbol() -> None:
    source = Path("ashare_research/mining/stage3_6c2.py").read_text(encoding="utf-8")

    assert "PositionLogitGenerator" not in source
