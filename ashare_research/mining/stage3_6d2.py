from __future__ import annotations

import json
import time
from pathlib import Path

from ashare_research.config import load_simple_yaml
from ashare_research.registry.artifacts import stable_hash


GENERATOR_LABELS = {
    "uniform_random": "UniformRandomGenerator",
    "position_logit": "PositionLogitGenerator",
}


SORTING_RULE = "train_reward_desc_then_formula_hash_asc"


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def load_completed_records(run_dir: Path, generator: str) -> list[dict]:
    rows = []
    for group_dir in sorted((run_dir / "group_manifests").glob(f"{generator}_seed*")):
        group_result = _read_json(group_dir / "group_result.json")
        seed = int(group_result["seed"])
        completed = _read_json(group_dir / "progress.json")
        order = {formula_hash: i + 1 for i, formula_hash in enumerate(group_result.get("completed_sequence", []))}
        for formula_hash, record in completed.items():
            if record["status"] != "completed" or not record.get("summary_path"):
                continue
            summary = _read_json(Path(record["summary_path"]))
            rows.append(
                {
                    "generator": generator,
                    "group_id": group_dir.name,
                    "seed": seed,
                    "formula_hash": formula_hash,
                    "formula_text": summary["formula_text"],
                    "token_sequence": summary["tokens"],
                    "formula_length": len(summary["tokens"]),
                    "train_reward": summary["metrics"].get("sortino"),
                    "train_metrics": summary["metrics"],
                    "discovery_order": order.get(formula_hash),
                }
            )
    return rows


def aggregate_by_formula(rows: list[dict], metadata: dict) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["formula_hash"], []).append(row)
    aggregated = []
    for formula_hash, items in grouped.items():
        best = sorted(items, key=lambda r: (-(r["train_reward"] if r["train_reward"] is not None else -1e99), r["formula_hash"]))[0]
        aggregated.append(
            {
                "generator": GENERATOR_LABELS[best["generator"]],
                "formula_hash": formula_hash,
                "formula_text": best["formula_text"],
                "token_sequence": best["token_sequence"],
                "formula_length": best["formula_length"],
                "source_seeds": sorted({item["seed"] for item in items}),
                "best_source_seed": best["seed"],
                "source_group_ids": sorted({item["group_id"] for item in items}),
                "discovery_orders": [
                    {"seed": item["seed"], "group_id": item["group_id"], "order": item["discovery_order"], "train_reward": item["train_reward"]}
                    for item in sorted(items, key=lambda r: (r["seed"], r["discovery_order"] or 10**9))
                ],
                "train_reward": best["train_reward"],
                "train_metrics": best["train_metrics"],
                "data_snapshot_hash": metadata["data_snapshot_hash"],
                "research_context_hash": metadata["context_hash"],
                "backtest_config_hash": metadata["config_hash"],
                "feature_version": metadata["feature_version"],
                "formula_vocabulary_version": metadata.get("formula_vocabulary_version", metadata["operator_version"]),
                "operator_version": metadata["operator_version"],
                "code_commit": metadata["code_commit"],
            }
        )
    return aggregated


def rank_candidates(candidates: list[dict]) -> list[dict]:
    ranked = sorted(candidates, key=lambda r: (-(r["train_reward"] if r["train_reward"] is not None else -1e99), r["formula_hash"]))
    return [{**row, "train_rank_within_generator": i + 1} for i, row in enumerate(ranked)]


def freeze_top_candidates(run_dir: Path, top_n_per_searcher: int, *, freeze_id: str | None = None) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    metadata = _read_json(manifest_path)
    freeze_payload = {
        "run_id": metadata["run_id"],
        "top_n_per_searcher": int(top_n_per_searcher),
        "sorting_rule": SORTING_RULE,
        "source_config_hash": metadata["config_hash"],
        "context_hash": metadata["context_hash"],
        "data_snapshot_hash": metadata["data_snapshot_hash"],
        "code_commit": metadata["code_commit"],
    }
    freeze_id = freeze_id or stable_hash(freeze_payload)[:16]
    out_dir = run_dir / "frozen_candidates" / freeze_id
    if out_dir.exists():
        raise FileExistsError(out_dir)
    out_dir.mkdir(parents=True)

    by_generator = {}
    full_ranked = {}
    for generator in ("uniform_random", "position_logit"):
        rows = load_completed_records(run_dir, generator)
        aggregated = aggregate_by_formula(rows, metadata)
        ranked = rank_candidates(aggregated)
        full_ranked[generator] = ranked
        by_generator[generator] = ranked[:top_n_per_searcher]

    uniform = by_generator["uniform_random"]
    position = by_generator["position_logit"]
    uniform_hashes = {row["formula_hash"] for row in uniform}
    position_hashes = {row["formula_hash"] for row in position}
    overlap_hashes = sorted(uniform_hashes & position_hashes)
    global_map = {}
    for row in uniform + position:
        global_map.setdefault(row["formula_hash"], row)
    global_unique = [global_map[key] for key in sorted(global_map)]
    provenance = {
        "uniform_random_total_completed": len(load_completed_records(run_dir, "uniform_random")),
        "position_logit_total_completed": len(load_completed_records(run_dir, "position_logit")),
        "uniform_random_unique_completed": len(full_ranked["uniform_random"]),
        "position_logit_unique_completed": len(full_ranked["position_logit"]),
        "sorting_rule": SORTING_RULE,
        "selection_rule": "per_searcher_top_n_after_merging_three_seeds_and_formula_hash_dedup",
    }
    overlap = {
        "cross_searcher_overlap_count": len(overlap_hashes),
        "overlap_formula_hashes": overlap_hashes,
        "overlap_not_backfilled": True,
    }
    file_payloads = {
        "uniform_candidates.json": uniform,
        "position_logit_candidates.json": position,
        "global_unique_candidates.json": global_unique,
        "candidate_overlap.json": overlap,
        "candidate_provenance.json": provenance,
    }
    for name, payload in file_payloads.items():
        (out_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    hashes = {
        "uniform_candidates_hash": stable_hash(uniform),
        "position_logit_candidates_hash": stable_hash(position),
        "global_unique_candidates_hash": stable_hash(global_unique),
    }
    freeze_manifest = {
        **freeze_payload,
        "freeze_id": freeze_id,
        "created_at_unix": time.time(),
        "train_candidates_frozen": True,
        "ready_for_frozen_candidate_validation": True,
        "validation_data_accessed": False,
        "blind_test_data_accessed": False,
        "uniform_candidates_count": len(uniform),
        "position_logit_candidates_count": len(position),
        "global_unique_candidates_count": len(global_unique),
        "cross_searcher_overlap_count": len(overlap_hashes),
        **hashes,
    }
    freeze_manifest["freeze_manifest_hash"] = stable_hash({k: v for k, v in freeze_manifest.items() if k != "created_at_unix"})
    (out_dir / "freeze_manifest.json").write_text(json.dumps(freeze_manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {
        "freeze_dir": str(out_dir),
        "freeze_manifest": freeze_manifest,
        "uniform_candidates": uniform,
        "position_logit_candidates": position,
        "global_unique_candidates": global_unique,
        "candidate_overlap": overlap,
        "candidate_provenance": provenance,
    }


def run_candidate_freeze(config_path: str | Path, repo_root: Path) -> dict:
    cfg = load_simple_yaml(config_path)
    run_dir = Path(repo_root) / "runs" / cfg["source_run_id"]
    top_n = int(cfg["candidate_freeze"]["top_n_per_searcher"])
    return freeze_top_candidates(run_dir, top_n)
