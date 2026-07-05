import json
from pathlib import Path

import pytest

from ashare_research.mining.stage3_6d2 import aggregate_by_formula, freeze_top_candidates, rank_candidates
from ashare_research.registry.artifacts import stable_hash


def _metadata():
    return {
        "run_id": "run",
        "context_hash": "ctx",
        "config_hash": "cfg",
        "data_snapshot_hash": "data",
        "feature_version": "features",
        "operator_version": "operators",
        "code_commit": "commit",
    }


def _row(generator, seed, formula_hash, reward, group_id=None, order=1):
    return {
        "generator": generator,
        "group_id": group_id or f"{generator}_seed{seed}",
        "seed": seed,
        "formula_hash": formula_hash,
        "formula_text": formula_hash,
        "token_sequence": ("RET1",),
        "formula_length": 1,
        "train_reward": reward,
        "train_metrics": {"sortino": reward},
        "discovery_order": order,
    }


def test_aggregate_by_searcher_dedups_formula_hash_and_preserves_sources() -> None:
    rows = [
        _row("uniform_random", 11, "same", 1.0, order=5),
        _row("uniform_random", 23, "same", 2.0, order=7),
        _row("uniform_random", 47, "other", 0.5, order=1),
    ]

    aggregated = aggregate_by_formula(rows, _metadata())
    by_hash = {row["formula_hash"]: row for row in aggregated}

    assert len(aggregated) == 2
    assert by_hash["same"]["source_seeds"] == [11, 23]
    assert by_hash["same"]["best_source_seed"] == 23
    assert len(by_hash["same"]["discovery_orders"]) == 2


def test_rank_candidates_uses_reward_desc_then_hash_stable() -> None:
    rows = aggregate_by_formula(
        [
            _row("uniform_random", 11, "b", 1.0),
            _row("uniform_random", 11, "a", 1.0),
            _row("uniform_random", 11, "c", 2.0),
        ],
        _metadata(),
    )

    ranked = rank_candidates(rows)

    assert [row["formula_hash"] for row in ranked] == ["c", "a", "b"]
    assert [row["train_rank_within_generator"] for row in ranked] == [1, 2, 3]


def _write_group(root: Path, generator: str, seed: int, formulas: list[tuple[str, float]]) -> None:
    d = root / "group_manifests" / f"{generator}_seed{seed}"
    summaries = d / "summaries"
    summaries.mkdir(parents=True)
    progress = {}
    completed_sequence = []
    for idx, (formula_hash, reward) in enumerate(formulas, start=1):
        summary = {
            "formula_hash": formula_hash,
            "formula_text": formula_hash,
            "tokens": ["RET1"],
            "metrics": {"sortino": reward},
            "failure_reason": None,
        }
        path = summaries / f"{formula_hash}.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        progress[formula_hash] = {"status": "completed", "summary_path": str(path), "failure_reason": None}
        completed_sequence.append(formula_hash)
    (d / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
    (d / "group_result.json").write_text(json.dumps({"seed": seed, "completed_sequence": completed_sequence}), encoding="utf-8")


def test_freeze_top_per_searcher_overlap_not_backfilled_and_no_overwrite(tmp_path: Path) -> None:
    manifest = {
        **_metadata(),
        "tradability_rule_version": "tradability",
        "price_policy_version": "price",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    # One overlapping top formula appears in both searchers. top_n=2 means no backfill to make global unique 4.
    _write_group(tmp_path, "uniform_random", 11, [("overlap", 10.0), ("u2", 9.0), ("u3", 8.0)])
    _write_group(tmp_path, "uniform_random", 23, [])
    _write_group(tmp_path, "uniform_random", 47, [])
    _write_group(tmp_path, "position_logit", 11, [("overlap", 11.0), ("p2", 7.0), ("p3", 6.0)])
    _write_group(tmp_path, "position_logit", 23, [])
    _write_group(tmp_path, "position_logit", 47, [])

    frozen = freeze_top_candidates(tmp_path, 2, freeze_id="unit")

    assert len(frozen["uniform_candidates"]) == 2
    assert len(frozen["position_logit_candidates"]) == 2
    assert frozen["candidate_overlap"]["cross_searcher_overlap_count"] == 1
    assert len(frozen["global_unique_candidates"]) == 3
    assert frozen["freeze_manifest"]["uniform_candidates_hash"] == stable_hash(frozen["uniform_candidates"])
    with pytest.raises(FileExistsError):
        freeze_top_candidates(tmp_path, 2, freeze_id="unit")


def test_top_n_change_creates_different_freeze_id_payload(tmp_path: Path) -> None:
    manifest = {
        **_metadata(),
        "tradability_rule_version": "tradability",
        "price_policy_version": "price",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _write_group(tmp_path, "uniform_random", 11, [("u1", 1.0), ("u2", 0.5)])
    _write_group(tmp_path, "position_logit", 11, [("p1", 1.0), ("p2", 0.5)])

    one = freeze_top_candidates(tmp_path, 1)
    two = freeze_top_candidates(tmp_path, 2)

    assert one["freeze_manifest"]["freeze_id"] != two["freeze_manifest"]["freeze_id"]
