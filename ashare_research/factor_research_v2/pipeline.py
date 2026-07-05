from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import BacktestConfig
from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import parse_formula_text
from ashare_research.registry.artifacts import stable_hash

from .candidate_generator import CandidateGeneratorV2
from .checkpoint import CheckpointV2
from .config import load_v2_config
from .correlation_filter import _aligned_corr, deduplicate_by_correlation
from .factor_registry import FactorRegistryV2
from .fast_screen import screen_candidates
from .full_backtest import run_full_backtests
from .models import CandidateFormula
from .report import write_report
from .robustness import evaluate_robustness, grade_factor


def run_pipeline(config_path: str | Path, repo_root: str | Path, *, resume: bool = False) -> dict[str, Any]:
    repo = Path(repo_root)
    cfg = load_v2_config(config_path)
    run_id = "factor_research_v2_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = _runs_root(repo, cfg.raw) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "errors.jsonl").touch()
    (run_dir / "run_config.yaml").write_text(Path(config_path).read_text(encoding="utf-8"), encoding="utf-8")
    config_hash = stable_hash(cfg.raw)
    return _execute_pipeline(cfg.raw, str(config_path), repo, run_dir, run_id, config_hash)


def resume_pipeline(run_dir: str | Path, repo_root: str | Path) -> dict[str, Any]:
    repo = Path(repo_root)
    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir_not_found:{run_dir}")
    config_path = run_dir / "run_config.yaml"
    meta_path = run_dir / "run_meta.json"
    if not config_path.exists() or not meta_path.exists():
        raise ValueError("resume_missing_run_config_or_meta")
    cfg = load_v2_config(config_path)
    config_hash = stable_hash(cfg.raw)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("config_hash") != config_hash:
        raise ValueError("resume_config_hash_mismatch")
    checkpoint = CheckpointV2(run_dir, config_hash)
    checkpoint_data = checkpoint.load()
    before_registry_count = _line_count(run_dir / "factor_registry_updates.jsonl")
    before_hash = _run_files_hash(run_dir)
    if checkpoint_data and checkpoint_data.get("stage") == "completed" and (run_dir / "pipeline_summary.json").exists():
        after_hash = _run_files_hash(run_dir)
        return {
            **json.loads((run_dir / "pipeline_summary.json").read_text(encoding="utf-8")),
            "resume_status": "completed_already",
            "run_id": str(meta["run_id"]),
            "run_dir": str(run_dir),
            "new_run_created": False,
            "recomputed_item_count": 0,
            "new_registry_event_count": 0,
            "registry_duplicate_count": 0,
            "run_files_hash_before": before_hash,
            "run_files_hash_after": after_hash,
            "registry_count_before_resume": before_registry_count,
            "registry_count_after_resume": before_registry_count,
        }
    return _execute_pipeline(cfg.raw, str(config_path), repo, run_dir, str(meta["run_id"]), config_hash, resume_existing=True)


def _execute_pipeline(
    raw: dict[str, Any],
    config_path: str,
    repo: Path,
    run_dir: Path,
    run_id: str,
    config_hash: str,
    *,
    resume_existing: bool = False,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "errors.jsonl").touch()
    cfg = load_v2_config(config_path)
    meta = {"run_id": run_id, "config_hash": config_hash, "research_data_end": cfg.research_end, "historical_blind_testing": "closed"}
    if not (resume_existing and (run_dir / "run_meta.json").exists()):
        _write_json(run_dir / "run_meta.json", meta)
    stage_summaries: list[dict[str, Any]] = []

    bt = _backtest_config(cfg.raw, run_dir)
    provider = LocalSQLiteProvider(repo / cfg.raw["data"]["sqlite_path"], repo / cfg.raw["data"].get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"))
    context = ResearchContext.build(provider, bt, data_snapshot_hash="factor_research_v2_known_research_data")
    checkpoint = CheckpointV2(run_dir, config_hash)
    if not resume_existing:
        checkpoint.save("prepared", {"context_hash": context.context_hash})

    candidate_source = _candidate_source_path(raw, repo)
    fast_screen_path = run_dir / "fast_screen_results.csv"
    reuse_fast_screen = resume_existing and fast_screen_path.exists()
    if resume_existing and (run_dir / "candidate_formulas.jsonl").exists():
        generated = _read_candidates(run_dir / "candidate_formulas.jsonl")
        gen_summary = json.loads((run_dir / "generation_summary.json").read_text(encoding="utf-8")) if (run_dir / "generation_summary.json").exists() else {"generated_count": len(generated), "mode_counts": {}}
    elif candidate_source:
        generated = _read_candidates(candidate_source)
        if len(generated) != cfg.candidate_count:
            raise ValueError(f"candidate_source_count_mismatch:expected={cfg.candidate_count}:actual={len(generated)}")
        gen_summary = {
            "generated_count": len(generated),
            "attempt_count": 0,
            "mode_counts": {},
            "candidate_source": str(candidate_source),
        }
        _write_jsonl(run_dir / "candidate_formulas.jsonl", [asdict(c) for c in generated])
        _write_json(run_dir / "generation_summary.json", gen_summary)
    else:
        generated, gen_summary = CandidateGeneratorV2(
            seed=cfg.seed,
            max_prefix_tokens=int(cfg.raw["formula_limits"]["max_prefix_tokens"]),
            max_tree_depth=int(cfg.raw["formula_limits"]["max_tree_depth"]),
        ).generate(cfg.candidate_count)
        _write_jsonl(run_dir / "candidate_formulas.jsonl", [asdict(c) for c in generated])
        _write_json(run_dir / "generation_summary.json", {**gen_summary, "mode_counts": dict(gen_summary["mode_counts"])})
    stage_summaries.append(_stage("generated", cfg.candidate_count, len(generated), {}))
    if not reuse_fast_screen:
        checkpoint.save("generated", {"count": len(generated)})

    correlation_input_limit = int(cfg.raw["correlation"].get("correlation_input_limit", len(generated)))
    if reuse_fast_screen:
        screen_rows = _read_fast_screen_results(fast_screen_path)
        outputs: dict[str, pd.Series] = {}
    else:
        screen_rows, outputs = screen_candidates(
            generated,
            context.features,
            context.bars,
            thresholds=cfg.raw["fast_screen"]["thresholds"],
            forward_return_horizon=int(cfg.raw["fast_screen"]["forward_return_horizon"]),
            output_limit=0,
        )
        pd.DataFrame(screen_rows).to_csv(fast_screen_path, index=False)
    fast_passed = [r for r in screen_rows if r["fast_screen_status"] == "passed"]
    stage_summaries.append(_stage("fast_screen", len(screen_rows), len(fast_passed), _reason_counts(screen_rows)))
    checkpoint.save("screened", {"passed": len(fast_passed)})

    ordered_fast_passed = _ordered_for_correlation(fast_passed)
    correlation_input = ordered_fast_passed[:correlation_input_limit]
    correlation_excluded = ordered_fast_passed[correlation_input_limit:]
    if outputs:
        clusters, deduped = deduplicate_by_correlation(
            correlation_input,
            outputs,
            float(cfg.raw["correlation"]["output_correlation_threshold"]),
            int(cfg.raw["correlation"].get("max_correlation_rows", 20000)),
        )
    else:
        clusters, deduped = _deduplicate_by_correlation_lazy(
            correlation_input,
            context.features,
            thresholds=cfg.raw["fast_screen"]["thresholds"],
            threshold=float(cfg.raw["correlation"]["output_correlation_threshold"]),
            max_rows=int(cfg.raw["correlation"].get("max_correlation_rows", 20000)),
            work_dir=run_dir / "correlation_outputs",
        )
    _write_json(run_dir / "dedup_clusters.json", clusters)
    deduped_hashes = {r["formula_hash"] for r in deduped}
    correlation_input_hashes = {r["formula_hash"] for r in correlation_input}
    cluster_member_hashes = {r["member"] for r in clusters.get("clusters", [])}
    full_backtest_input = deduped[: cfg.full_backtest_limit]
    full_backtest_input_hashes = {r["formula_hash"] for r in full_backtest_input}
    candidate_status_rows = _candidate_status_rows(
        screen_rows,
        correlation_input_hashes,
        {r["formula_hash"] for r in correlation_excluded},
        cluster_member_hashes,
        full_backtest_input_hashes,
        deduped_hashes - full_backtest_input_hashes,
    )
    _write_jsonl(run_dir / "candidate_stage_status.jsonl", candidate_status_rows)
    candidate_status_counts = _status_counts(candidate_status_rows)
    stage_summaries.append(_stage("deduplicated", len(fast_passed), len(deduped), {"excluded_by_correlation_budget": len(correlation_excluded), "deduplicated_by_correlation": len(cluster_member_hashes)}))

    evaluator = BatchBacktestEvaluator(context, save_detail_policy="summary_only", run_dir=run_dir / "details")
    full_rows = run_full_backtests(full_backtest_input, evaluator, cfg.full_backtest_limit)
    _write_jsonl(run_dir / "full_backtest_results.jsonl", full_rows)
    full_passed = [r for r in full_rows if r["full_backtest_status"] == "passed"]
    stage_summaries.append(_stage("full_backtest", len(deduped[: cfg.full_backtest_limit]), len(full_passed), _failure_counts(full_rows)))

    robustness_rows = evaluate_robustness(full_rows, cfg.raw)
    _write_jsonl(run_dir / "robustness_results.jsonl", robustness_rows)
    robust_by_hash = {r["formula_hash"]: r for r in robustness_rows}
    fast_by_hash = {r["formula_hash"]: r for r in screen_rows}
    registry_records = []
    for full in full_rows:
        h = full["formula_hash"]
        grade = grade_factor(fast_by_hash.get(h, {}), full, robust_by_hash.get(h, {}), cfg.raw["rating"])
        record = {
            "factor_id": "factor_" + h[:12],
            "formula_hash": h,
            "canonical_formula": full["canonical_formula"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": "candidate" if grade != "Rejected" else "rejected",
            "grade": grade,
            "fast_screen_metrics": fast_by_hash.get(h, {}),
            "full_backtest_metrics": full,
            "robustness_metrics": robust_by_hash.get(h, {}),
            "first_seen_run_id": run_id,
            "latest_evaluation_run_id": run_id,
        }
        registry_records.append(record)
    registry_result = FactorRegistryV2(_registry_root(repo, cfg.raw)).append_many(registry_records)
    _write_jsonl(run_dir / "factor_registry_updates.jsonl", registry_records)
    _write_json(run_dir / "final_shortlist.json", [r for r in registry_records if r["grade"] != "Rejected"])

    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "research_data_start": bt.start_date,
        "research_data_end": bt.end_date,
        "counts": {
            "generated": len(generated),
            "fast_screen_passed": len(fast_passed),
            "selected_for_correlation": len(correlation_input),
            "excluded_by_correlation_budget": len(correlation_excluded),
            "deduplicated": len(deduped),
            "selected_for_full_backtest": len(full_backtest_input),
            "excluded_by_full_backtest_budget": len(deduped) - len(full_backtest_input),
            "full_backtest": len(full_rows),
            "registry_records": len(registry_records),
        },
        "candidate_status_counts": candidate_status_counts,
        "correlation_input_limit": correlation_input_limit,
        "registry_append_result": registry_result,
        "stage_summaries": stage_summaries,
        "registry_records": registry_records,
        "forward_data_accessed": False,
        "validation_or_blind_claimed": False,
    }
    write_report(run_dir, summary)
    _write_json(run_dir / "stage_status.json", stage_summaries)
    _write_json(run_dir / "pipeline_summary.json", summary)
    checkpoint.save("completed", summary)
    return summary


def _runs_root(repo: Path, raw: dict[str, Any]) -> Path:
    override = os.environ.get("ALPHAGPT_RUNS_ROOT")
    if override:
        return Path(override)
    configured = Path(str(raw["output"]["runs_dir"]))
    return configured if configured.is_absolute() else repo / configured


def _registry_root(repo: Path, raw: dict[str, Any]) -> Path:
    configured = Path(str(raw["output"]["registry_dir"]))
    return configured if configured.is_absolute() else repo / configured


def _deduplicate_by_correlation_lazy(
    rows: list[dict[str, Any]],
    features: pd.DataFrame,
    *,
    thresholds: dict[str, Any],
    threshold: float,
    max_rows: int,
    work_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    executor = FormulaExecutor(min_valid_rows=int(thresholds.get("min_valid_rows", 20)))
    kept: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    for row in _ordered_for_correlation([r for r in rows if r.get("fast_screen_status") == "passed"]):
        current = executor.execute(parse_formula_text(str(row["canonical_formula"])), features)
        if not current.valid or current.values is None:
            continue
        h = str(row["formula_hash"])
        duplicate_of = None
        for existing in kept:
            existing_hash = str(existing["formula_hash"])
            existing_values = pd.read_pickle(work_dir / f"{existing_hash}.pkl")
            corr = _aligned_corr(current.values, existing_values, max_rows=max_rows)
            if corr is not None and abs(corr) >= threshold:
                duplicate_of = existing_hash
                clusters.append({"representative": duplicate_of, "member": h, "correlation": corr})
                break
        if duplicate_of is None:
            current.values.to_pickle(work_dir / f"{h}.pkl")
            kept.append(row)
    return {"threshold": threshold, "max_rows": max_rows, "clusters": clusters, "kept_count": len(kept), "input_count": len(rows)}, kept


def _ordered_for_correlation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            -(abs(float(r.get("rank_ic_mean") or 0.0))),
            -float(r.get("coverage") or 0.0),
            len(str(r.get("canonical_formula", ""))),
            str(r.get("formula_hash", "")),
        ),
    )


def _candidate_status_rows(
    screen_rows: list[dict[str, Any]],
    correlation_input_hashes: set[str],
    correlation_excluded_hashes: set[str],
    cluster_member_hashes: set[str],
    full_backtest_input_hashes: set[str],
    full_backtest_excluded_hashes: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in screen_rows:
        formula_hash = str(row["formula_hash"])
        history = []
        status = str(row.get("fast_screen_status") or "unknown")
        budget_excluded = False
        rejected = status != "passed"
        if status == "passed":
            if formula_hash in correlation_excluded_hashes:
                status = "excluded_by_correlation_budget"
                history.append("excluded_by_correlation_budget")
                budget_excluded = True
            else:
                history.append("selected_for_correlation")
                if formula_hash in cluster_member_hashes:
                    status = "deduplicated_by_correlation"
                    history.append("deduplicated_by_correlation")
                elif formula_hash in full_backtest_input_hashes:
                    status = "selected_for_full_backtest"
                    history.append("selected_for_full_backtest")
                elif formula_hash in full_backtest_excluded_hashes:
                    status = "excluded_by_full_backtest_budget"
                    history.append("excluded_by_full_backtest_budget")
                    budget_excluded = True
                elif formula_hash in correlation_input_hashes:
                    status = "selected_for_correlation"
        rows.append({
            "formula_hash": formula_hash,
            "canonical_formula": row.get("canonical_formula"),
            "fast_screen_status": row.get("fast_screen_status"),
            "pipeline_status": status,
            "status_history": history,
            "budget_excluded": budget_excluded,
            "rejected": rejected,
        })
    return rows


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("pipeline_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _candidate_source_path(raw: dict[str, Any], repo: Path) -> Path | None:
    source = raw.get("candidate_source") or raw.get("generation", {}).get("candidate_source")
    if not source:
        return None
    path = Path(str(source))
    path = path if path.is_absolute() else repo / path
    if not path.exists():
        raise FileNotFoundError(f"candidate_source_not_found:{path}")
    return path


def _read_candidates(path: Path) -> list[CandidateFormula]:
    rows = _read_jsonl(path)
    return [
        CandidateFormula(
            formula_hash=str(row["formula_hash"]),
            canonical_formula=str(row["canonical_formula"]),
            tokens=tuple(row["tokens"]),
            generator_type=str(row["generator_type"]),
            parent_factor_id=row.get("parent_factor_id"),
            generation_seed=int(row["generation_seed"]),
            complexity=int(row["complexity"]),
            feature_dependencies=tuple(row["feature_dependencies"]),
            operator_dependencies=tuple(row["operator_dependencies"]),
        )
        for row in rows
    ]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_fast_screen_results(path: Path) -> list[dict[str, Any]]:
    rows = pd.read_csv(path).to_dict("records")
    for row in rows:
        for key, value in list(row.items()):
            if pd.isna(value):
                row[key] = None
    return rows


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _run_files_hash(run_dir: Path) -> str:
    payload: dict[str, str] = {}
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file()):
        if path.name == "pipeline_state.json.tmp":
            continue
        payload[str(path.relative_to(run_dir))] = stable_hash(path.read_bytes().hex())
    return stable_hash(payload)


def _backtest_config(raw: dict[str, Any], run_dir: Path) -> BacktestConfig:
    b = raw["backtest"]
    data = raw["data"]
    return BacktestConfig(
        start_date=str(data["research_start"]),
        end_date=str(data["research_end"]),
        rebalance_frequency=int(b["rebalance_frequency"]),
        top_n=int(b["top_n"]),
        initial_cash=float(b["initial_cash"]),
        cost_bps=float(b["one_way_cost_bps"]),
        unknown_tradability_policy=str(b["unknown_tradability_policy"]),
        runs_dir=str(run_dir / "phase2"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=1.0,
    )


def _stage(name: str, input_count: int, passed_count: int, reasons: dict[str, int]) -> dict[str, Any]:
    return {"stage": name, "input_count": input_count, "passed_count": passed_count, "rejected_count": input_count - passed_count, "rejection_reasons": reasons}


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("fast_screen_status") != "passed":
            reason = str(row.get("rejection_reason") or "unknown")
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("failure_reason"):
            reason = str(row.get("failure_reason"))
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
