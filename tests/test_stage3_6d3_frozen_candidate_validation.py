from __future__ import annotations

from pathlib import Path

from ashare_research.backtest.progress import FormulaProgressStore
from ashare_research.factors.expression import parse_formula_text
from ashare_research.mining.stage3_6d3 import (
    GENERATOR_POSITION,
    GENERATOR_UNIFORM,
    build_views,
    candidate_source_maps,
    freeze_blind_shortlist,
    load_and_verify_freeze,
    spearman_rank_correlation,
    validation_conclusion,
    verify_freeze_manifest_hash,
)
from ashare_research.registry.artifacts import stable_hash

import pytest


def _candidate(formula: str, generator: str, rank: int, seed: int = 11) -> dict:
    expr = parse_formula_text(formula)
    return {
        "generator": generator,
        "formula_hash": expr.sha256(),
        "formula_text": expr.to_string(),
        "token_sequence": list(expr.tokens),
        "formula_length": len(expr.tokens),
        "source_seeds": [seed],
        "best_source_seed": seed,
        "source_group_ids": [f"{generator}_{seed}"],
        "discovery_orders": [{"seed": seed, "group_id": f"{generator}_{seed}", "order": rank, "train_reward": 1.0 / rank}],
        "train_reward": 1.0 / rank,
        "train_metrics": {"sortino": 1.0 / rank},
        "train_rank_within_generator": rank,
        "data_snapshot_hash": "data",
        "research_context_hash": "ctx",
        "backtest_config_hash": "cfg",
        "formula_vocabulary_version": "vocab",
        "operator_version": "ops",
        "code_commit": "commit",
    }


def _write_freeze(tmp_path: Path) -> Path:
    formulas = [
        "RET1",
        "RET5",
        "VOL_RATIO20",
        "TREND60",
        "VOLUME_WEIGHTED_RET",
        "ADD(RET1,VOL_RATIO20)",
        "SUB(RET5,TREND60)",
        "DIV(TREND60,RET5)",
        "NEG(RET1)",
        "ABS(RET5)",
        "SIGN(RET1)",
        "DELTA5(RET1)",
        "DECAY_LINEAR20(RET1)",
        "ZSCORE20(RET5)",
        "ADD(RET1,RET5)",
        "SUB(RET1,RET5)",
        "MUL(RET1,RET5)",
        "DIV(RET1,RET5)",
        "ADD(TREND60,RET1)",
        "SUB(TREND60,RET5)",
        "ADD(VOL_RATIO20,RET5)",
        "SUB(VOL_RATIO20,RET1)",
        "MUL(TREND60,RET1)",
        "DIV(VOL_RATIO20,RET5)",
        "NEG(TREND60)",
        "ABS(TREND60)",
        "SIGN(TREND60)",
        "DELTA5(RET5)",
        "DECAY_LINEAR20(RET5)",
        "ZSCORE20(RET1)",
        "ADD(VOLUME_WEIGHTED_RET,RET1)",
    ]
    uniform = [_candidate(f, GENERATOR_UNIFORM, i + 1) for i, f in enumerate(formulas[:20])]
    position = [_candidate(f, GENERATOR_POSITION, i + 1, seed=23) for i, f in enumerate(formulas[11:31])]
    global_map = {}
    for row in uniform + position:
        global_map.setdefault(row["formula_hash"], row)
    global_unique = [global_map[k] for k in sorted(global_map)]
    overlap_hashes = sorted({r["formula_hash"] for r in uniform} & {r["formula_hash"] for r in position})
    out = tmp_path / "freeze"
    out.mkdir()
    payloads = {
        "uniform_candidates.json": uniform,
        "position_logit_candidates.json": position,
        "global_unique_candidates.json": global_unique,
        "candidate_overlap.json": {"cross_searcher_overlap_count": len(overlap_hashes), "overlap_formula_hashes": overlap_hashes},
        "candidate_provenance.json": {"sorting_rule": "train_reward_desc_then_formula_hash_asc"},
    }
    for name, payload in payloads.items():
        (out / name).write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "run_id": "run",
        "top_n_per_searcher": 20,
        "source_config_hash": "cfg",
        "context_hash": "ctx",
        "data_snapshot_hash": "data",
        "code_commit": "commit",
        "uniform_candidates_count": 20,
        "position_logit_candidates_count": 20,
        "global_unique_candidates_count": 31,
        "cross_searcher_overlap_count": 9,
        "uniform_candidates_hash": stable_hash(uniform),
        "position_logit_candidates_hash": stable_hash(position),
        "global_unique_candidates_hash": stable_hash(global_unique),
        "created_at_unix": 1.0,
    }
    manifest["freeze_manifest_hash"] = verify_freeze_manifest_hash(manifest)
    (out / "freeze_manifest.json").write_text(__import__("json").dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return out / "freeze_manifest.json"


def test_freeze_manifest_hash_mismatch_refuses_run(tmp_path: Path):
    path = _write_freeze(tmp_path)
    text = path.read_text(encoding="utf-8").replace("commit", "changed", 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="freeze_hash_mismatch"):
        load_and_verify_freeze(path)


def test_only_31_unique_and_overlap_maps_to_both_searchers(tmp_path: Path):
    bundle = load_and_verify_freeze(_write_freeze(tmp_path))
    assert len(bundle.global_unique) == 31
    assert len({row["formula_hash"] for row in bundle.global_unique}) == 31
    source = candidate_source_maps(bundle)
    overlap = [item for item in source.values() if set(item["source_generators"]) == {GENERATOR_UNIFORM, GENERATOR_POSITION}]
    assert len(overlap) == 9
    assert all(item["uniform_train_rank"] is not None and item["position_logit_train_rank"] is not None for item in overlap)


def test_views_have_20_20_11_11_and_shared_results(tmp_path: Path):
    bundle = load_and_verify_freeze(_write_freeze(tmp_path))
    results = []
    for row in bundle.global_unique:
        results.append({"formula_hash": row["formula_hash"], "validation_sortino": 1.0, "validation_status": "completed", "validation_metrics": {"sortino": 1.0}})
    views = build_views(bundle, results)
    assert len(views["uniform"]) == 20
    assert len(views["position_logit"]) == 20
    assert len(views["uniform_exclusive"]) == 11
    assert len(views["position_logit_exclusive"]) == 11
    assert len(views["overlap"]) == 9


def test_shortlist_positive_only_max_5_and_no_backfill(tmp_path: Path):
    rows = [
        {"formula_hash": f"h{i}", "validation_status": "completed", "validation_sortino": val, "train_sortino": 10 - i}
        for i, val in enumerate([3, 2, 1, 0, -1, None])
    ]
    cfg = {"blind_shortlist": {"top_n": 5}}
    out = freeze_blind_shortlist(tmp_path, rows, cfg, "vh")
    assert out["shortlist_manifest"]["eligible_blind_candidates"] == 3
    assert out["shortlist_manifest"]["frozen_blind_shortlist_count"] == 3
    assert [row["formula_hash"] for row in out["global_shortlist"]] == ["h0", "h1", "h2"]
    with pytest.raises(FileExistsError):
        freeze_blind_shortlist(tmp_path, rows, cfg, "vh")


def test_validation_conclusion_requires_full_and_exclusive_direction():
    stats = {
        "position_logit_full": {"validation_sortino_median": 2, "validation_top_10_mean": 2, "validation_positive_ratio": 0.8, "validation_sortino_available_ratio": 1},
        "uniform_full": {"validation_sortino_median": 1, "validation_top_10_mean": 1, "validation_positive_ratio": 0.5, "validation_sortino_available_ratio": 1},
        "position_logit_exclusive": {"validation_sortino_median": 2, "validation_top_10_mean": 2, "validation_positive_ratio": 0.8},
        "uniform_exclusive": {"validation_sortino_median": 1, "validation_top_10_mean": 1, "validation_positive_ratio": 0.5},
    }
    assert validation_conclusion(stats) == "position_logit_advantage"
    stats["position_logit_exclusive"], stats["uniform_exclusive"] = stats["uniform_exclusive"], stats["position_logit_exclusive"]
    assert validation_conclusion(stats) == "inconclusive"


def test_progress_completed_not_reexecuted_and_interrupted_retries(tmp_path: Path):
    manifest = {
        "run_id": "r",
        "context_hash": "ctx",
        "config_hash": "cfg",
        "data_snapshot_hash": "data",
        "feature_version": "f",
        "operator_version": "o",
        "universe_version": "u",
        "tradability_rule_version": "t",
        "price_policy_version": "p",
        "code_commit": "c",
    }
    store = FormulaProgressStore(tmp_path, manifest)
    store.initialize_queue([("a", "RET1"), ("b", "RET5")])
    store.mark_running("a")
    store.mark_completed("a", {"formula_hash": "a", "metrics": {"sortino": 1}})
    store.mark_running("b")
    store.mark_interrupted_running()
    records = store.load()
    assert records["a"].status == "completed"
    assert records["b"].status == "interrupted"
    assert store.executable_hashes() == ["b"]


def test_spearman_rank_correlation_matches_rank_then_pearson_and_drops_pairs():
    value = spearman_rank_correlation([1.0, 2.0, 2.0, 4.0, float("nan")], [4.0, 1.0, 2.0, 3.0, 9.0])
    expected = -0.316227766016838
    assert value == pytest.approx(expected)
    assert spearman_rank_correlation([1.0, float("nan")], [2.0, 3.0]) is None
