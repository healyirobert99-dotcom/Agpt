from ashare_research.factors.expression import Expression
from ashare_research.mining.deduplicator import FormulaDeduplicator
from ashare_research.registry.artifacts import stable_hash


def test_same_formula_hash_is_not_accepted_twice() -> None:
    expr = Expression(("RET1",))
    dedup = FormulaDeduplicator()

    assert dedup.accept(expr.sha256())
    assert not dedup.accept(expr.sha256())


def test_cache_hash_includes_data_and_backtest_config() -> None:
    formula_hash = Expression(("RET1",)).sha256()
    key_a = stable_hash({"formula": formula_hash, "data": "snapshot-a", "backtest": {"cost": 20}})
    key_b = stable_hash({"formula": formula_hash, "data": "snapshot-b", "backtest": {"cost": 20}})
    key_c = stable_hash({"formula": formula_hash, "data": "snapshot-a", "backtest": {"cost": 40}})

    assert key_a != key_b
    assert key_a != key_c
