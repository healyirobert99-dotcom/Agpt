from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ashare_research.factor_research_v2.candidate_generator import CandidateGeneratorV2, canonicalize
from ashare_research.factor_research_v2.checkpoint import CheckpointV2
from ashare_research.factor_research_v2.correlation_filter import deduplicate_by_correlation
from ashare_research.factor_research_v2.factor_registry import FactorRegistryV2
from ashare_research.factor_research_v2.fast_screen import compute_forward_returns, screen_candidates
from ashare_research.factor_research_v2.pipeline import resume_pipeline, run_pipeline
from ashare_research.factor_research_v2.report import formula_to_chinese, write_report
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.registry.artifacts import stable_hash
from tools.generate_factor_research_v2_diagnostics import generate_diagnostics
from tools.revalidate_factor_research_v2_94 import _final_grade, _window_results, extract_deduplicated_inputs


def _features_and_bars() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    bars = []
    dates = [f"202401{i:02d}" for i in range(1, 31)]
    for code_idx, code in enumerate(["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"]):
        price = 10.0 + code_idx
        for i, date in enumerate(dates):
            ret5 = code_idx * 0.01 + i * 0.001
            rows.append({
                "trade_date": date,
                "ts_code": code,
                "RET1": ret5 / 5,
                "RET5": ret5,
                "VOL_RATIO20": 1.0 + code_idx * 0.1,
                "VOLUME_WEIGHTED_RET": ret5 * 0.5,
                "TREND60": ret5 * 2,
            })
            close = price * (1 + ret5)
            bars.append({"trade_date": date, "ts_code": code, "raw_close": close, "raw_open": close})
    return pd.DataFrame(rows), pd.DataFrame(bars)


def test_candidate_generation_same_seed_is_deterministic():
    a, _ = CandidateGeneratorV2(seed=7).generate(20)
    b, _ = CandidateGeneratorV2(seed=7).generate(20)
    assert [x.formula_hash for x in a] == [x.formula_hash for x in b]
    assert len(set(x.formula_hash for x in a)) == len(a)


def test_complexity_limit_and_illegal_formula_rejected():
    gen, _ = CandidateGeneratorV2(seed=8, max_prefix_tokens=3, max_tree_depth=2).generate(10)
    assert all(len(c.tokens) <= 3 for c in gen)
    assert Expression(("ADD", "RET1")).validate()[0] is False


def test_structural_equivalent_formula_canonicalizes():
    a = canonicalize(parse_formula_text("ADD(RET1,RET5)"))
    b = canonicalize(parse_formula_text("ADD(RET5,RET1)"))
    assert a.sha256() == b.sha256()


def test_forward_return_uses_future_label_not_factor_input():
    _, bars = _features_and_bars()
    labels = compute_forward_returns(bars, horizon=2)
    one = bars[(bars["trade_date"] == "20240101") & (bars["ts_code"] == "000001.SZ")].iloc[0]
    future = bars[(bars["trade_date"] == "20240103") & (bars["ts_code"] == "000001.SZ")].iloc[0]
    got = labels[(labels["trade_date"] == "20240101") & (labels["ts_code"] == "000001.SZ")]["forward_return"].iloc[0]
    assert got == pytest.approx(future["raw_close"] / one["raw_close"] - 1.0)


def test_fast_screen_positive_factor_and_constant_rejection():
    features, bars = _features_and_bars()
    candidates, _ = CandidateGeneratorV2(seed=1).generate(5)
    good = parse_formula_text("RET5")
    good_candidate = candidates[0].__class__(
        formula_hash=good.sha256(),
        canonical_formula=good.to_string(),
        tokens=good.tokens,
        generator_type="fixture",
        parent_factor_id=None,
        generation_seed=1,
        complexity=len(good.tokens),
        feature_dependencies=("RET5",),
        operator_dependencies=(),
    )
    rows, _ = screen_candidates([good_candidate], features, bars, thresholds={"min_coverage": 0.1, "min_abs_rank_ic_mean": 0.0, "min_cross_sectional_dispersion": 0.0}, forward_return_horizon=1)
    assert rows[0]["coverage"] > 0
    assert rows[0]["fast_screen_status"] == "passed"


def test_correlation_filter_clusters_identical_outputs():
    idx = pd.MultiIndex.from_product([["A", "B", "C", "D", "E"], ["20240101", "20240102", "20240103"]], names=["ts_code", "trade_date"])
    s = pd.Series(range(len(idx)), index=idx, dtype=float)
    rows = [
        {"formula_hash": "a", "canonical_formula": "RET1", "fast_screen_status": "passed", "rank_ic_mean": 0.02, "coverage": 1.0},
        {"formula_hash": "b", "canonical_formula": "ADD(RET1,RET5)", "fast_screen_status": "passed", "rank_ic_mean": 0.01, "coverage": 1.0},
    ]
    clusters, kept = deduplicate_by_correlation(rows, {"a": s, "b": s}, 0.99)
    assert len(kept) == 1
    assert clusters["clusters"][0]["member"] == "b"


def test_checkpoint_hash_mismatch_rejects_resume(tmp_path: Path):
    cp = CheckpointV2(tmp_path, "a")
    cp.save("generated", {"x": 1})
    with pytest.raises(ValueError, match="checkpoint_config_hash_mismatch"):
        CheckpointV2(tmp_path, "b").load()


def test_chinese_report_written(tmp_path: Path):
    summary = {
        "research_data_start": "20240101",
        "research_data_end": "20240628",
        "counts": {"generated": 1, "fast_screen_passed": 1, "full_backtest": 1},
        "stage_summaries": [{"stage": "generated", "input_count": 1, "passed_count": 1, "rejected_count": 0}],
        "registry_records": [{"grade": "B", "canonical_formula": "ADD(RET1,RET5)"}],
    }
    write_report(tmp_path, summary)
    text = (tmp_path / "research_report.md").read_text(encoding="utf-8")
    assert "自主因子研究系统 v2 MVP 报告" in text
    assert "1日收益" in formula_to_chinese("RET1")
    assert (tmp_path / "research_report.json").exists()


def _write_v2_config(path: Path, *, runs_dir: str | None = None, registry_dir: str | None = None, candidate_count: int = 1, candidate_source: str | None = None, correlation_input_limit: int = 10, full_backtest_limit: int = 1) -> dict:
    runs_dir = runs_dir or str(path.parent / "runs")
    registry_dir = registry_dir or str(path.parent / "registry")
    candidate_source_line = f"  candidate_source: {candidate_source.replace(chr(92), '/')}\n" if candidate_source else ""
    text = f"""
run:
  name: factor_research_v2_test
data:
  sqlite_path: stock-data/ashare_research.sqlite3
  raw_sqlite_path: stock-data/a_stock_selector.sqlite3
  research_start: "20240101"
  research_end: "20240131"
generation:
  seed: 7
  candidate_count: {candidate_count}
{candidate_source_line.rstrip()}
formula_limits:
  max_prefix_tokens: 8
  max_tree_depth: 2
fast_screen:
  forward_return_horizon: 5
  thresholds:
    min_valid_rows: 1
    min_coverage: 0.0
    min_abs_rank_ic_mean: 0.0
    min_cross_sectional_dispersion: 0.0
correlation:
  output_correlation_threshold: 0.95
  max_correlation_rows: 100
  correlation_input_limit: {correlation_input_limit}
full_backtest:
  limit: {full_backtest_limit}
backtest:
  rebalance_frequency: 5
  top_n: 3
  initial_cash: 1000000
  one_way_cost_bps: 20
  unknown_tradability_policy: block
rating:
  min_positive_period_ratio: 0.45
  grade_a_min_abs_ic: 0.03
  grade_a_max_drawdown: 0.35
  grade_b_min_abs_ic: 0.015
output:
  runs_dir: {runs_dir.replace(chr(92), "/")}
  registry_dir: {registry_dir.replace(chr(92), "/")}
"""
    path.write_text(text, encoding="utf-8")
    import yaml
    return yaml.safe_load(text)


def _completed_run(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "run_config_source.yaml"
    raw = _write_v2_config(cfg_path)
    run_dir = tmp_path / "runs" / "factor_research_v2_done"
    run_dir.mkdir(parents=True)
    config_hash = stable_hash(raw)
    (run_dir / "run_config.yaml").write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "run_meta.json").write_text(json.dumps({"run_id": run_dir.name, "config_hash": config_hash, "research_data_end": "20240131"}), encoding="utf-8")
    summary = {"run_id": run_dir.name, "run_dir": str(run_dir), "counts": {"registry_records": 1}, "forward_data_accessed": False}
    (run_dir / "pipeline_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "candidate_formulas.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "factor_registry_updates.jsonl").write_text(json.dumps({"formula_hash": "abc"}) + "\n", encoding="utf-8")
    CheckpointV2(run_dir, config_hash).save("completed", summary)
    return run_dir


def test_completed_run_resume_does_not_create_new_dir_or_registry_event(tmp_path: Path):
    run_dir = _completed_run(tmp_path)
    before_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    before_registry = (run_dir / "factor_registry_updates.jsonl").read_text(encoding="utf-8")

    result = resume_pipeline(run_dir, tmp_path)

    assert result["resume_status"] == "completed_already"
    assert result["run_id"] == run_dir.name
    assert result["new_run_created"] is False
    assert result["recomputed_item_count"] == 0
    assert result["new_registry_event_count"] == 0
    assert result["registry_duplicate_count"] == 0
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == before_dirs
    assert (run_dir / "factor_registry_updates.jsonl").read_text(encoding="utf-8") == before_registry


def test_completed_run_resume_is_idempotent_twice(tmp_path: Path):
    run_dir = _completed_run(tmp_path)
    first = resume_pipeline(run_dir, tmp_path)
    second = resume_pipeline(run_dir, tmp_path)
    assert first["resume_status"] == second["resume_status"] == "completed_already"
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == [run_dir.name]


def test_resume_rejects_config_hash_mismatch(tmp_path: Path):
    run_dir = _completed_run(tmp_path)
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    meta["config_hash"] = "wrong"
    (run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="resume_config_hash_mismatch"):
        resume_pipeline(run_dir, tmp_path)


def test_resume_reuses_existing_fast_screen_results_without_rescreening(tmp_path: Path, monkeypatch):
    import ashare_research.factor_research_v2.pipeline as pipeline

    cfg = tmp_path / "config.yaml"
    _write_v2_config(cfg, candidate_count=1, correlation_input_limit=1, full_backtest_limit=1, registry_dir=str(tmp_path / "registry"))
    raw = pipeline.load_v2_config(cfg).raw
    config_hash = stable_hash(raw)
    run_dir = tmp_path / "runs" / "existing_run"
    run_dir.mkdir(parents=True)
    (run_dir / "run_config.yaml").write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "run_meta.json").write_text(json.dumps({"run_id": "existing_run", "config_hash": config_hash}), encoding="utf-8")
    (run_dir / "errors.jsonl").touch()
    candidate = {
        "formula_hash": "44f11a17fa7bba330223e442cf08e26ecc490a0845ab089d8b0e8f700a990941",
        "canonical_formula": "RET1",
        "tokens": ["RET1"],
        "generator_type": "fixture",
        "parent_factor_id": None,
        "generation_seed": 7,
        "complexity": 1,
        "feature_dependencies": ["RET1"],
        "operator_dependencies": [],
    }
    (run_dir / "candidate_formulas.jsonl").write_text(json.dumps(candidate, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "generation_summary.json").write_text(json.dumps({"generated_count": 1, "mode_counts": {}}), encoding="utf-8")
    pd.DataFrame([{
        "formula_hash": candidate["formula_hash"],
        "canonical_formula": "RET1",
        "fast_screen_status": "passed",
        "rank_ic_mean": 0.1,
        "coverage": 1.0,
        "rejection_reason": None,
    }]).to_csv(run_dir / "fast_screen_results.csv", index=False)
    CheckpointV2(run_dir, config_hash).save("screened", {"passed": 1})

    class DummyContext:
        context_hash = "ctx"
        features = pd.DataFrame()
        bars = pd.DataFrame()

    monkeypatch.setattr(pipeline.LocalSQLiteProvider, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(pipeline.ResearchContext, "build", lambda *args, **kwargs: DummyContext())
    monkeypatch.setattr(pipeline, "BatchBacktestEvaluator", lambda *args, **kwargs: object())
    monkeypatch.setattr(pipeline, "screen_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("resume should reuse fast_screen_results.csv")))
    monkeypatch.setattr(pipeline, "_deduplicate_by_correlation_lazy", lambda rows, *args, **kwargs: ({"threshold": 0.95, "max_rows": 100, "clusters": [], "kept_count": len(rows), "input_count": len(rows)}, rows))
    monkeypatch.setattr(pipeline, "run_full_backtests", lambda rows, *args, **kwargs: [{"formula_hash": r["formula_hash"], "canonical_formula": r["canonical_formula"], "full_backtest_status": "passed", "failure_reason": None, "metrics": {"total_return": 0.1}, "trade_count": 1, "completed_trade_count": 1, "unfilled_count": 0} for r in rows])
    monkeypatch.setattr(pipeline, "evaluate_robustness", lambda rows, *args, **kwargs: [{"formula_hash": r["formula_hash"], "robustness_status": "passed", "positive_period_ratio": 1.0, "sortino": 1.0} for r in rows])

    result = resume_pipeline(run_dir, tmp_path)
    checkpoint = CheckpointV2(run_dir, config_hash).load()
    assert result["counts"]["fast_screen_passed"] == 1
    assert result["counts"]["selected_for_correlation"] == 1
    assert checkpoint["stage"] == "completed"


def test_registry_event_idempotency_and_quarantine(tmp_path: Path):
    registry = FactorRegistryV2(tmp_path / "registry")
    record = {"first_seen_run_id": "run_a", "latest_evaluation_run_id": "run_a", "formula_hash": "f1", "grade": "A"}
    assert registry.append_many([record]) == {"appended": 1, "skipped_duplicate": 0}
    assert registry.append_many([record]) == {"appended": 0, "skipped_duplicate": 1}
    registry.quarantine_run("run_a", "test")
    assert registry.active_records() == []


def test_run_creates_empty_errors_jsonl_and_uses_absolute_runs_root(tmp_path: Path, monkeypatch):
    import ashare_research.factor_research_v2.pipeline as pipeline

    monkeypatch.delenv("ALPHAGPT_RUNS_ROOT", raising=False)
    cfg = tmp_path / "config.yaml"
    runs_root = tmp_path / "runtime" / "runs"
    _write_v2_config(cfg, runs_dir=str(runs_root), registry_dir=str(tmp_path / "runtime" / "registry"))

    class DummyContext:
        context_hash = "ctx"
        features = pd.DataFrame()
        bars = pd.DataFrame()

    monkeypatch.setattr(pipeline.LocalSQLiteProvider, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(pipeline.ResearchContext, "build", lambda *args, **kwargs: DummyContext())
    monkeypatch.setattr(pipeline, "BatchBacktestEvaluator", lambda *args, **kwargs: object())
    monkeypatch.setattr(pipeline, "screen_candidates", lambda *args, **kwargs: ([{"formula_hash": "h", "canonical_formula": "RET1", "fast_screen_status": "passed", "rank_ic_mean": 0.1, "coverage": 1.0}], {"h": pd.Series([1.0])}))
    monkeypatch.setattr(pipeline, "run_full_backtests", lambda *args, **kwargs: [{"formula_hash": "h", "canonical_formula": "RET1", "full_backtest_status": "passed", "failure_reason": None, "metrics": {"total_return": 0.1}, "trade_count": 1, "completed_trade_count": 1, "unfilled_count": 0}])
    monkeypatch.setattr(pipeline, "evaluate_robustness", lambda *args, **kwargs: [{"formula_hash": "h", "robustness_status": "passed", "positive_period_ratio": 1.0, "sortino": 1.0}])

    result = run_pipeline(cfg, tmp_path)
    run_dir = Path(result["run_dir"])
    assert run_dir.parent == runs_root
    assert (run_dir / "errors.jsonl").exists()
    assert (run_dir / "errors.jsonl").read_text(encoding="utf-8") == ""


def test_run_uses_candidate_source_without_regeneration(tmp_path: Path, monkeypatch):
    import ashare_research.factor_research_v2.pipeline as pipeline

    source = tmp_path / "fixed_candidates.jsonl"
    source_candidate = {
        "formula_hash": "44f11a17fa7bba330223e442cf08e26ecc490a0845ab089d8b0e8f700a990941",
        "canonical_formula": "RET1",
        "tokens": ["RET1"],
        "generator_type": "fixture",
        "parent_factor_id": None,
        "generation_seed": 7,
        "complexity": 1,
        "feature_dependencies": ["RET1"],
        "operator_dependencies": [],
    }
    source.write_text(json.dumps(source_candidate, sort_keys=True) + "\n", encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    _write_v2_config(cfg, candidate_source=str(source))

    class DummyContext:
        context_hash = "ctx"
        features = pd.DataFrame()
        bars = pd.DataFrame()

    def fail_generate(*args, **kwargs):
        raise AssertionError("candidate generator should not run when candidate_source is configured")

    monkeypatch.setattr(pipeline.CandidateGeneratorV2, "generate", fail_generate)
    monkeypatch.setattr(pipeline.LocalSQLiteProvider, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(pipeline.ResearchContext, "build", lambda *args, **kwargs: DummyContext())
    monkeypatch.setattr(pipeline, "BatchBacktestEvaluator", lambda *args, **kwargs: object())
    monkeypatch.setattr(pipeline, "screen_candidates", lambda *args, **kwargs: ([{"formula_hash": source_candidate["formula_hash"], "canonical_formula": "RET1", "fast_screen_status": "passed", "rank_ic_mean": 0.1, "coverage": 1.0}], {source_candidate["formula_hash"]: pd.Series([1.0])}))
    monkeypatch.setattr(pipeline, "run_full_backtests", lambda *args, **kwargs: [{"formula_hash": source_candidate["formula_hash"], "canonical_formula": "RET1", "full_backtest_status": "passed", "failure_reason": None, "metrics": {"total_return": 0.1}, "trade_count": 1, "completed_trade_count": 1, "unfilled_count": 0}])
    monkeypatch.setattr(pipeline, "evaluate_robustness", lambda *args, **kwargs: [{"formula_hash": source_candidate["formula_hash"], "robustness_status": "passed", "positive_period_ratio": 1.0, "sortino": 1.0}])

    result = run_pipeline(cfg, tmp_path)
    run_dir = Path(result["run_dir"])
    written = [json.loads(line) for line in (run_dir / "candidate_formulas.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = json.loads((run_dir / "generation_summary.json").read_text(encoding="utf-8"))
    assert written == [source_candidate]
    assert summary["candidate_source"] == str(source)


def test_correlation_input_limit_marks_budget_exclusions():
    import ashare_research.factor_research_v2.pipeline as pipeline

    rows = [
        {"formula_hash": f"h{i:03d}", "canonical_formula": f"RET{i}", "fast_screen_status": "passed", "rank_ic_mean": 100 - i, "coverage": 1.0}
        for i in range(40)
    ]
    ordered = pipeline._ordered_for_correlation(rows)
    selected = ordered[:30]
    excluded = ordered[30:]
    status_rows = pipeline._candidate_status_rows(
        rows,
        {r["formula_hash"] for r in selected},
        {r["formula_hash"] for r in excluded},
        set(),
        {r["formula_hash"] for r in selected},
        set(),
    )
    counts = pipeline._status_counts(status_rows)
    assert counts["selected_for_full_backtest"] == 30
    assert counts["excluded_by_correlation_budget"] == 10
    assert all(not r["rejected"] for r in status_rows if r["pipeline_status"] == "excluded_by_correlation_budget")
    assert all(r["budget_excluded"] for r in status_rows if r["pipeline_status"] == "excluded_by_correlation_budget")


def test_correlation_input_limit_500_selects_at_most_500_and_is_deterministic():
    import ashare_research.factor_research_v2.pipeline as pipeline

    rows = [
        {"formula_hash": f"h{i:03d}", "canonical_formula": "RET1", "fast_screen_status": "passed", "rank_ic_mean": 1.0, "coverage": 0.5}
        for i in reversed(range(550))
    ]
    first = [r["formula_hash"] for r in pipeline._ordered_for_correlation(rows)[:500]]
    second = [r["formula_hash"] for r in pipeline._ordered_for_correlation(rows)[:500]]
    assert len(first) == 500
    assert first == second
    assert first[:3] == ["h000", "h001", "h002"]


def test_candidate_status_reconciles_fast_screen_passed_and_full_backtest_budget():
    import ashare_research.factor_research_v2.pipeline as pipeline

    rows = [
        {"formula_hash": "a", "canonical_formula": "RET1", "fast_screen_status": "passed"},
        {"formula_hash": "b", "canonical_formula": "RET5", "fast_screen_status": "passed"},
        {"formula_hash": "c", "canonical_formula": "TREND60", "fast_screen_status": "passed"},
        {"formula_hash": "d", "canonical_formula": "VOL_RATIO20", "fast_screen_status": "rejected"},
    ]
    status_rows = pipeline._candidate_status_rows(
        rows,
        {"a", "b", "c"},
        set(),
        {"b"},
        {"a"},
        {"c"},
    )
    passed_rows = [r for r in status_rows if r["fast_screen_status"] == "passed"]
    counts = pipeline._status_counts(passed_rows)
    assert sum(counts.values()) == 3
    assert counts == {
        "selected_for_full_backtest": 1,
        "deduplicated_by_correlation": 1,
        "excluded_by_full_backtest_budget": 1,
    }
    assert [r for r in passed_rows if r["pipeline_status"] == "excluded_by_full_backtest_budget"][0]["budget_excluded"] is True


def test_pipeline_writes_candidate_status_and_respects_full_backtest_limit(tmp_path: Path, monkeypatch):
    import ashare_research.factor_research_v2.pipeline as pipeline

    monkeypatch.delenv("ALPHAGPT_RUNS_ROOT", raising=False)
    cfg = tmp_path / "config.yaml"
    _write_v2_config(cfg, candidate_count=1, correlation_input_limit=3, full_backtest_limit=2)

    class DummyContext:
        context_hash = "ctx"
        features = pd.DataFrame()
        bars = pd.DataFrame()

    screen_rows = [
        {"formula_hash": f"h{i}", "canonical_formula": f"RET{i}", "fast_screen_status": "passed", "rank_ic_mean": 10 - i, "coverage": 1.0}
        for i in range(5)
    ]
    outputs = {r["formula_hash"]: pd.Series(range(20), dtype=float) for r in screen_rows}
    full_inputs = []

    monkeypatch.setattr(pipeline.LocalSQLiteProvider, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(pipeline.ResearchContext, "build", lambda *args, **kwargs: DummyContext())
    monkeypatch.setattr(pipeline, "BatchBacktestEvaluator", lambda *args, **kwargs: object())
    monkeypatch.setattr(pipeline, "screen_candidates", lambda *args, **kwargs: (screen_rows, outputs))
    monkeypatch.setattr(pipeline, "deduplicate_by_correlation", lambda rows, *args, **kwargs: ({"threshold": 0.95, "max_rows": 100, "clusters": [{"representative": rows[0]["formula_hash"], "member": rows[1]["formula_hash"], "correlation": 1.0}], "kept_count": 2, "input_count": len(rows)}, [rows[0], rows[2]]))

    def fake_full_backtests(rows, *args, **kwargs):
        full_inputs.extend(rows)
        return [
            {"formula_hash": r["formula_hash"], "canonical_formula": r["canonical_formula"], "full_backtest_status": "passed", "failure_reason": None, "metrics": {"total_return": 0.1, "trade_count": 1}, "trade_count": 1, "completed_trade_count": 1, "unfilled_count": 0}
            for r in rows
        ]

    monkeypatch.setattr(pipeline, "run_full_backtests", fake_full_backtests)
    monkeypatch.setattr(pipeline, "evaluate_robustness", lambda rows, *args, **kwargs: [{"formula_hash": r["formula_hash"], "robustness_status": "passed", "positive_period_ratio": 1.0, "sortino": 1.0} for r in rows])

    result = run_pipeline(cfg, tmp_path)
    run_dir = Path(result["run_dir"])
    statuses = [json.loads(line) for line in (run_dir / "candidate_stage_status.jsonl").read_text(encoding="utf-8").splitlines()]
    counts = result["candidate_status_counts"]
    assert result["counts"]["selected_for_correlation"] == 3
    assert result["counts"]["excluded_by_correlation_budget"] == 2
    assert result["counts"]["selected_for_full_backtest"] == 2
    assert len(full_inputs) == 2
    assert counts["excluded_by_correlation_budget"] == 2
    assert counts["deduplicated_by_correlation"] == 1
    assert counts["selected_for_full_backtest"] == 2
    assert sum(counts[s] for s in ["excluded_by_correlation_budget", "deduplicated_by_correlation", "selected_for_full_backtest"]) == 5
    assert all(not r["rejected"] for r in statuses if r["pipeline_status"].endswith("_budget"))


def test_diagnostic_report_uses_specific_reasons_and_recomputes_grade(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_config.yaml").write_text(
        """
data:
  research_start: "20240101"
  research_end: "20240131"
  split:
    development: ["20240101", "20240110"]
    selection: ["20240111", "20240120"]
    stability: ["20240121", "20240131"]
generation:
  candidate_count: 2
fast_screen:
  thresholds:
    min_valid_rows: 1
    min_coverage: 0.3
    min_abs_rank_ic_mean: 0.001
    min_cross_sectional_dispersion: 0.000001
rating:
  min_positive_period_ratio: 0.45
  grade_a_min_abs_ic: 0.03
  grade_a_max_drawdown: 0.35
  grade_b_min_abs_ic: 0.015
""",
        encoding="utf-8",
    )
    (run_dir / "run_meta.json").write_text(json.dumps({"run_id": "run"}), encoding="utf-8")
    (run_dir / "generation_summary.json").write_text(json.dumps({"attempt_count": 60, "mode_counts": {"fixture": 2}}), encoding="utf-8")
    candidates = [
        {"formula_hash": "good", "canonical_formula": "RET5", "tokens": ["RET5"]},
        {"formula_hash": "bad", "canonical_formula": "RET1", "tokens": ["RET1"]},
    ]
    (run_dir / "candidate_formulas.jsonl").write_text("\n".join(json.dumps(x) for x in candidates) + "\n", encoding="utf-8")
    pd.DataFrame([
        {"formula_hash": "good", "canonical_formula": "RET5", "coverage": 1.0, "rank_ic_mean": 0.02, "rank_ic_std": 0.1, "rank_ic_ir": 0.2, "positive_period_ratio": 0.6, "negative_period_ratio": 0.4, "monotonicity_score": 0.1, "top_bottom_spread": 0.01, "turnover_proxy": 0.2, "signal_stability": 0.8, "fast_screen_status": "passed", "rejection_reason": None},
        {"formula_hash": "bad", "canonical_formula": "RET1", "coverage": 1.0, "rank_ic_mean": 0.02, "rank_ic_std": 0.1, "rank_ic_ir": 0.2, "positive_period_ratio": 0.4, "negative_period_ratio": 0.6, "monotonicity_score": 0.1, "top_bottom_spread": -0.01, "turnover_proxy": 0.2, "signal_stability": 0.8, "fast_screen_status": "passed", "rejection_reason": None},
    ]).to_csv(run_dir / "fast_screen_results.csv", index=False)
    (run_dir / "candidate_stage_status.jsonl").write_text(
        "\n".join(json.dumps({"formula_hash": x["formula_hash"], "pipeline_status": "selected_for_full_backtest"}) for x in candidates) + "\n",
        encoding="utf-8",
    )
    (run_dir / "dedup_clusters.json").write_text(json.dumps({"clusters": [], "input_count": 2, "kept_count": 2, "threshold": 0.95}), encoding="utf-8")
    full_rows = [
        {"formula_hash": "good", "canonical_formula": "RET5", "full_backtest_status": "passed", "failure_reason": None, "metrics": {"total_return": 0.1, "annualized_return": 0.05, "max_drawdown": -0.6, "sortino": 0.2, "sharpe": 0.1, "turnover": 1.0, "trade_count": 10, "win_rate": None}, "trade_count": 10, "completed_trade_count": 9, "unfilled_count": 1, "average_cash_ratio": 0.1},
        {"formula_hash": "bad", "canonical_formula": "RET1", "full_backtest_status": "passed", "failure_reason": None, "metrics": {"total_return": -0.1, "annualized_return": -0.05, "max_drawdown": -0.7, "sortino": -0.2, "sharpe": -0.1, "turnover": 1.5, "trade_count": 8, "win_rate": None}, "trade_count": 8, "completed_trade_count": 8, "unfilled_count": 0, "average_cash_ratio": 0.2},
    ]
    (run_dir / "full_backtest_results.jsonl").write_text("\n".join(json.dumps(x) for x in full_rows) + "\n", encoding="utf-8")
    robust_rows = [
        {"formula_hash": "good", "robustness_status": "passed", "positive_period_ratio": 1.0, "sortino": 0.2, "cost_sensitivity": "not_run_mvp", "holding_period_sensitivity": "not_run_mvp"},
        {"formula_hash": "bad", "robustness_status": "rejected", "positive_period_ratio": 0.0, "sortino": -0.2, "cost_sensitivity": "not_run_mvp", "holding_period_sensitivity": "not_run_mvp"},
    ]
    (run_dir / "robustness_results.jsonl").write_text("\n".join(json.dumps(x) for x in robust_rows) + "\n", encoding="utf-8")
    registry = [
        {"formula_hash": "good", "canonical_formula": "RET5", "grade": "B"},
        {"formula_hash": "bad", "canonical_formula": "RET1", "grade": "Rejected"},
    ]
    (run_dir / "factor_registry_updates.jsonl").write_text("\n".join(json.dumps(x) for x in registry) + "\n", encoding="utf-8")
    summary = {
        "run_id": "run",
        "counts": {"generated": 2, "fast_screen_passed": 2, "selected_for_correlation": 2, "deduplicated": 2, "full_backtest": 2},
        "candidate_status_counts": {"selected_for_full_backtest": 2},
        "forward_data_accessed": False,
    }
    (run_dir / "pipeline_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    report = generate_diagnostics(run_dir, tmp_path)

    assert report["grades"]["rating_recompute_equal"] is True
    assert report["time_split"]["effective"] is False
    assert report["fast_screen"]["rules_loaded"] is True
    assert "成本后总收益为负" in (run_dir / "diagnostics" / "full_backtest_50_factors.csv").read_text(encoding="utf-8")
    assert "通用风险" not in (run_dir / "research_diagnostic_report.md").read_text(encoding="utf-8")


def test_revalidation_window_win_rate_uses_completed_windows_only():
    trades = pd.DataFrame([
        {"actual_trade_date": "20240102", "ts_code": "000001.SZ", "side": "buy", "requested_quantity": 100, "executed_quantity": 100, "execution_price": 10.0, "transaction_cost": 2.0, "status": "filled"},
        {"actual_trade_date": "20240103", "ts_code": "000002.SZ", "side": "buy", "requested_quantity": 100, "executed_quantity": 0, "execution_price": 10.0, "transaction_cost": 0.0, "status": "unfilled"},
        {"actual_trade_date": "20240105", "ts_code": "000001.SZ", "side": "sell", "requested_quantity": 100, "executed_quantity": 100, "execution_price": 11.0, "transaction_cost": 2.2, "status": "filled"},
        {"actual_trade_date": "20240106", "ts_code": "000003.SZ", "side": "buy", "requested_quantity": 100, "executed_quantity": 100, "execution_price": 10.0, "transaction_cost": 2.0, "status": "filled"},
    ])
    windows = _window_results(trades)
    completed = [w for w in windows if w["window_status"] == "completed"]
    wins = [w for w in completed if w["net_return_after_cost"] > 0]
    assert len(completed) == 1
    assert len(wins) / len(completed) == 1.0
    assert any(w["window_status"] == "entry_unfilled" for w in windows)
    assert any(w["window_status"] == "open_or_incomplete" for w in windows)


def test_revalidation_rating_gate_blocks_ab_when_required_metrics_missing_or_bad():
    rules = {"grade_a_min_abs_ic": 0.03, "grade_a_max_drawdown": 0.35, "grade_b_min_abs_ic": 0.015}
    selection = {"total_return": 0.1, "unaccounted_count": 0, "trade_win_rate": 0.6, "profit_loss_ratio": 1.2}
    stability = {"total_return": 0.1, "max_drawdown": -0.2, "unaccounted_count": 0, "trade_win_rate": None, "profit_loss_ratio": 1.2}
    robust = {"robustness_status": "passed"}
    grade, reasons, missing = _final_grade(selection, stability, {"rank_ic_mean": 0.04}, {"rank_ic_mean": 0.04}, robust, rules, "passed")
    assert grade == "Rejected"
    assert "trade_win_rate" in missing

    stability["trade_win_rate"] = 0.6
    robust["robustness_status"] = "not_run"
    grade, reasons, missing = _final_grade(selection, stability, {"rank_ic_mean": 0.04}, {"rank_ic_mean": 0.04}, robust, rules, "passed")
    assert grade == "Rejected"

    robust["robustness_status"] = "passed"
    stability["total_return"] = -0.01
    grade, reasons, missing = _final_grade(selection, stability, {"rank_ic_mean": 0.04}, {"rank_ic_mean": 0.04}, robust, rules, "rejected")
    assert grade == "C"


def test_revalidation_extracts_fixed_94_without_generator(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    rows = [
        {"formula_hash": f"h{i:03d}", "canonical_formula": f"RET{i % 5}", "fast_screen_status": "passed", "rank_ic_mean": 100 - i, "coverage": 1.0}
        for i in range(100)
    ]
    pd.DataFrame(rows).to_csv(source / "fast_screen_results.csv", index=False)
    clusters = [{"representative": f"h{i:03d}", "member": f"h{94 + i:03d}", "correlation": 0.99} for i in range(6)]
    (source / "dedup_clusters.json").write_text(json.dumps({"clusters": clusters, "input_count": 100, "kept_count": 94, "threshold": 0.95}), encoding="utf-8")
    fixed = extract_deduplicated_inputs(source)
    assert len(fixed) == 94
    assert len({r["formula_hash"] for r in fixed}) == 94
    assert all(r["source_run_id"] == "source" for r in fixed)
