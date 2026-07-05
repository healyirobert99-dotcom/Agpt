import json
from pathlib import Path

import pandas as pd
import pytest

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.equivalence import compare_backtest_dirs, compare_dataframes
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.progress import FormulaProgressStore
from ashare_research.factors.expression import Expression
from ashare_research.mining.stage3_5 import SyntheticMomentumProvider, synthetic_backtest_config


def _manifest() -> dict:
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


def test_equivalence_dataframe_sorting_and_float_tolerance() -> None:
    left = pd.DataFrame(
        [
            {"trade_date": "20240102", "ts_code": "000002.SZ", "cash": 1.0},
            {"trade_date": "20240101", "ts_code": "000001.SZ", "cash": 2.0},
        ]
    )
    right = pd.DataFrame(
        [
            {"trade_date": "20240101", "ts_code": "000001.SZ", "cash": 2.0 + 1e-10},
            {"trade_date": "20240102", "ts_code": "000002.SZ", "cash": 1.0},
        ]
    )

    result = compare_dataframes(left, right, "daily_holdings")

    assert result.equal
    assert result.difference_count == 0


def test_equivalence_detects_metric_difference(tmp_path: Path) -> None:
    for root, sortino in [(tmp_path / "a", 1.0), (tmp_path / "b", 2.0)]:
        root.mkdir()
        for name in ["planned_orders.csv", "executions.csv", "daily_holdings.csv", "daily_account.csv"]:
            pd.DataFrame().to_csv(root / name, index=False)
        (root / "metrics.json").write_text(json.dumps({"metrics": {"sortino": sortino}}), encoding="utf-8")

    result = compare_backtest_dirs(tmp_path / "a", tmp_path / "b")

    assert not result["equivalent"]
    assert result["metrics_equal"] is False
    assert "sortino" in result["first_difference"]


def test_formula_progress_state_transitions_and_resume_guards(tmp_path: Path) -> None:
    store = FormulaProgressStore(tmp_path, _manifest())
    store.initialize_queue([("h1", "RET1"), ("h2", "RET5")])

    store.mark_running("h1")
    assert store.load()["h1"].status == "running"
    store.mark_interrupted_running()
    assert store.load()["h1"].status == "interrupted"
    assert "h1" in store.executable_hashes()

    store.mark_running("h1")
    store.mark_completed("h1", {"formula_hash": "h1", "metrics": {"sortino": 1.0}})
    store.mark_failed("h2", "bad_formula")

    records = store.load()
    assert records["h1"].status == "completed"
    assert records["h1"].summary_hash
    assert records["h2"].status == "failed"
    assert store.completed_hashes() == {"h1"}
    assert (tmp_path / "completed_results.jsonl").exists()

    with pytest.raises(ValueError, match="resume_hash_mismatch:context_hash"):
        bad = _manifest()
        bad["context_hash"] = "changed"
        store.validate_manifest(bad)


def test_batch_order_isolation_and_failure_does_not_pollute_context(tmp_path: Path) -> None:
    provider = SyntheticMomentumProvider()
    cfg = synthetic_backtest_config(tmp_path / "cfg")
    ctx = ResearchContext.build(provider, cfg)
    before = ctx.context_hash
    formulas = {
        "A": Expression(("RET1",)),
        "B": Expression(("RET5",)),
        "C": Expression(("ADD", "RET1", "VOL_RATIO20")),
    }

    def run(order):
        evaluator = BatchBacktestEvaluator(ctx)
        return {name: evaluator.evaluate(formulas[name]) for name in order}

    single_a = run(["A"])["A"]
    abc_a = run(["A", "B", "C"])["A"]
    cba_a = run(["C", "B", "A"])["A"]

    assert single_a.metrics == abc_a.metrics == cba_a.metrics
    pd.testing.assert_frame_equal(single_a.accounts.reset_index(drop=True), cba_a.accounts.reset_index(drop=True))
    assert ctx.context_hash == before

    evaluator = BatchBacktestEvaluator(ctx)
    ok_before = evaluator.evaluate(formulas["B"])
    failed = evaluator.evaluate(Expression(("ADD", "RET1")))
    ok_after = evaluator.evaluate(formulas["C"])
    clean_c = BatchBacktestEvaluator(ctx).evaluate(formulas["C"])

    assert failed.failure_reason is not None
    assert ok_before.failure_reason is None
    assert ok_after.metrics == clean_c.metrics
    assert ctx.context_hash == before
