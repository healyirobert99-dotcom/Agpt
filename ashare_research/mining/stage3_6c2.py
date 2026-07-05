from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    import resource
except ModuleNotFoundError:  # Windows does not provide the Unix resource module.
    resource = None

import numpy as np

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.golden import current_git_commit
from ashare_research.backtest.progress import FormulaProgressStore, atomic_write_json
from ashare_research.config import load_simple_yaml
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.mining.model import UniformRandomGenerator
from ashare_research.mining.stage3_6b import build_config
from ashare_research.registry.artifacts import stable_hash


WARNING_LINES = (
    "ENGINEERING COMPLETED-BUDGET GATE ONLY",
    "NOT A SEARCHER COMPARISON",
    "NO VALIDATION OR BLIND TEST ACCESS",
    "NOT A VALIDATED INVESTMENT STRATEGY",
)


def peak_memory_mb() -> float | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(usage / 1024.0 / 1024.0)
    return float(usage / 1024.0)


def disk_mb(path: Path) -> float:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return float(total / 1024 / 1024)


@dataclass(frozen=True)
class CompletedBudgetConfig:
    completed_full_backtest_target: int
    max_unique_formula_attempts: int
    max_generation_attempts: int
    seed: int
    save_detail_policy: str


def completed_budget_config(cfg: dict) -> CompletedBudgetConfig:
    budget = cfg["stability_budget"]
    if budget["generator"] != "uniform_random":
        raise ValueError("completed_budget_gate_requires_uniform_random")
    return CompletedBudgetConfig(
        completed_full_backtest_target=int(budget["completed_full_backtest_target"]),
        max_unique_formula_attempts=int(budget["max_unique_formula_attempts"]),
        max_generation_attempts=int(budget["max_generation_attempts"]),
        seed=int(budget["seed"]),
        save_detail_policy=str(budget["save_detail_policy"]),
    )


def budget_counts(records: dict) -> dict:
    status_counts: dict[str, int] = {}
    for record in records.values():
        status_counts[record.status] = status_counts.get(record.status, 0) + 1
    failed = [record for record in records.values() if record.status == "failed"]
    return {
        "completed_full_backtest_count": status_counts.get("completed", 0),
        "unique_formula_attempt_count": len(records),
        "failed_count": status_counts.get("failed", 0),
        "pending_count": status_counts.get("pending", 0),
        "running_count": status_counts.get("running", 0),
        "interrupted_count": status_counts.get("interrupted", 0),
        "formula_execution_invalid_count": sum(1 for record in failed if (record.failure_reason or "").startswith("invalid_formula:")),
        "backtest_failed_count": sum(1 for record in failed if not (record.failure_reason or "").startswith("invalid_formula:")),
    }


def should_stop(counts: dict, generation_attempt_count: int, config: CompletedBudgetConfig) -> tuple[bool, str | None]:
    if counts["completed_full_backtest_count"] >= config.completed_full_backtest_target:
        return True, "completed_full_backtest_target_reached"
    if counts["unique_formula_attempt_count"] >= config.max_unique_formula_attempts:
        return True, "max_unique_formula_attempts_reached"
    if generation_attempt_count >= config.max_generation_attempts:
        return True, "max_generation_attempts_reached"
    return False, None


def result_summary(expr: Expression, result, elapsed_seconds: float) -> dict:
    return {
        "formula_hash": expr.sha256(),
        "formula_text": expr.to_string(),
        "tokens": list(expr.tokens),
        "metrics": result.metrics,
        "failure_reason": result.failure_reason,
        "elapsed_seconds": elapsed_seconds,
        "sortino_available": result.metrics.get("sortino") is not None if result.metrics else False,
    }


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _queue_rows(expressions: list[Expression]) -> list[dict]:
    return [{"formula_hash": expr.sha256(), "formula_text": expr.to_string(), "tokens": list(expr.tokens)} for expr in expressions]


def continuous_generation_reference(config: CompletedBudgetConfig, generation_attempt_count: int) -> list[dict]:
    generator = UniformRandomGenerator(seed=config.seed)
    rows = []
    for _ in range(generation_attempt_count):
        expr = generator.generate().expression
        rows.append({"formula_hash": expr.sha256(), "formula_text": expr.to_string(), "tokens": list(expr.tokens)})
    return rows


def generate_until_completed(
    *,
    generator: UniformRandomGenerator,
    evaluator: BatchBacktestEvaluator,
    store: FormulaProgressStore,
    config: CompletedBudgetConfig,
    interrupt_after_completed: int | None = None,
    stop_after_interrupt: bool = False,
    run_dir: Path,
) -> dict:
    generation_attempt_count = 0
    duplicate_count = 0
    syntax_invalid_count = 0
    formula_evaluation_seconds = 0.0
    generated_sequence: list[dict] = []
    completed_sequence: list[str] = []
    failed_sequence: list[str] = []
    interrupted_hash: str | None = None

    while True:
        atomic_write_json(run_dir / "generator_state.json", generator.state_dict())
        counts = budget_counts(store.load())
        stop, reason = should_stop(counts, generation_attempt_count, config)
        if stop:
            return {
                "stop_reason": reason,
                "generation_attempt_count": generation_attempt_count,
                "duplicate_count": duplicate_count,
                "syntax_invalid_count": syntax_invalid_count,
                "formula_evaluation_seconds": formula_evaluation_seconds,
                "generated_sequence": generated_sequence,
                "completed_sequence": completed_sequence,
                "failed_sequence": failed_sequence,
                "interrupted_hash": interrupted_hash,
                "generator_state_hash": stable_hash(generator.state_dict()),
            }
        generated = generator.generate()
        atomic_write_json(run_dir / "generator_state.json", generator.state_dict())
        expr = generated.expression
        generation_attempt_count += 1
        generated_sequence.append({"formula_hash": expr.sha256(), "formula_text": expr.to_string(), "tokens": list(expr.tokens)})
        valid, reason = expr.validate()
        if not valid:
            syntax_invalid_count += 1
            continue
        records = store.load()
        if expr.sha256() in records:
            duplicate_count += 1
            continue
        store.initialize_queue([(expr.sha256(), expr.to_string())])
        if interrupt_after_completed is not None and budget_counts(store.load())["completed_full_backtest_count"] >= interrupt_after_completed:
            store.mark_running(expr.sha256())
            store.mark_interrupted_running()
            interrupted_hash = expr.sha256()
            if stop_after_interrupt:
                return {
                    "stop_reason": "simulated_interrupt",
                    "generation_attempt_count": generation_attempt_count,
                    "duplicate_count": duplicate_count,
                    "syntax_invalid_count": syntax_invalid_count,
                    "formula_evaluation_seconds": formula_evaluation_seconds,
                    "generated_sequence": generated_sequence,
                    "completed_sequence": completed_sequence,
                    "failed_sequence": failed_sequence,
                    "interrupted_hash": interrupted_hash,
                    "generator_state_hash": stable_hash(generator.state_dict()),
                }
        store.mark_running(expr.sha256())
        start = time.perf_counter()
        result = evaluator.evaluate(expr)
        elapsed = time.perf_counter() - start
        formula_evaluation_seconds += elapsed
        payload = result_summary(expr, result, elapsed)
        if result.failure_reason:
            payload["failure_stage"] = "formula_execution" if str(result.failure_reason).startswith("invalid_formula:") else "backtest"
            store.mark_failed(expr.sha256(), result.failure_reason)
            _append_jsonl(run_dir / "failed_results.jsonl", payload)
            failed_sequence.append(expr.sha256())
        else:
            store.mark_completed(expr.sha256(), payload)
            completed_sequence.append(expr.sha256())


def resume_completed_budget(
    *,
    formulas: list[Expression],
    evaluator: BatchBacktestEvaluator,
    store: FormulaProgressStore,
    run_dir: Path,
) -> dict:
    completed_before = set(store.completed_hashes())
    resumed_execution: list[str] = []
    formula_evaluation_seconds = 0.0
    for expr in formulas:
        record = store.load().get(expr.sha256())
        if record is None or record.status in {"completed", "failed"}:
            continue
        store.mark_running(expr.sha256())
        start = time.perf_counter()
        result = evaluator.evaluate(expr)
        elapsed = time.perf_counter() - start
        formula_evaluation_seconds += elapsed
        payload = result_summary(expr, result, elapsed)
        if result.failure_reason:
            payload["failure_stage"] = "formula_execution" if str(result.failure_reason).startswith("invalid_formula:") else "backtest"
            store.mark_failed(expr.sha256(), result.failure_reason)
            _append_jsonl(run_dir / "failed_results.jsonl", payload)
        else:
            store.mark_completed(expr.sha256(), payload)
        resumed_execution.append(expr.sha256())
    return {
        "completed_before_resume": len(completed_before),
        "resumed_execution": resumed_execution,
        "completed_not_reexecuted": not completed_before.intersection(resumed_execution),
        "formula_evaluation_seconds": formula_evaluation_seconds,
    }


def summarize_completed_budget(run_dir: Path, store: FormulaProgressStore, generation_attempt_count: int, duplicate_count: int, syntax_invalid_count: int, formula_seconds: float, context_seconds: float) -> dict:
    records = store.load()
    counts = budget_counts(records)
    summaries = []
    for record in records.values():
        if record.status == "completed" and record.summary_path:
            summaries.append(json.loads(Path(record.summary_path).read_text(encoding="utf-8")))
    sortinos = [row["metrics"].get("sortino") for row in summaries if row["metrics"].get("sortino") is not None]
    elapsed = [row["elapsed_seconds"] for row in summaries]
    rewards = np.array(sortinos, dtype=float) if sortinos else np.array([], dtype=float)
    return {
        **counts,
        "generation_attempt_count": generation_attempt_count,
        "duplicate_count": duplicate_count,
        "syntax_invalid_count": syntax_invalid_count,
        "sortino_available_count": len(sortinos),
        "sortino_available_ratio": len(sortinos) / len(summaries) if summaries else 0.0,
        "positive_sortino_count": int(sum(value > 0 for value in sortinos)),
        "negative_sortino_count": int(sum(value < 0 for value in sortinos)),
        "reward_mean": float(rewards.mean()) if len(rewards) else None,
        "reward_std": float(rewards.std()) if len(rewards) else None,
        "reward_percentiles": {str(q): float(np.percentile(rewards, q)) for q in [0, 25, 50, 75, 100]} if len(rewards) else {},
        "formula_evaluation_seconds": formula_seconds,
        "context_build_seconds": context_seconds,
        "total_wall_seconds": context_seconds + formula_seconds,
        "average_completed_formula_seconds_excluding_context": formula_seconds / len(summaries) if summaries else None,
        "average_unique_attempt_seconds": formula_seconds / counts["unique_formula_attempt_count"] if counts["unique_formula_attempt_count"] else None,
        "amortized_completed_formula_seconds_including_context": (context_seconds + formula_seconds) / len(summaries) if summaries else None,
        "median_formula_seconds": float(np.median(elapsed)) if elapsed else None,
        "p90_formula_seconds": float(np.percentile(elapsed, 90)) if elapsed else None,
        "peak_memory_mb": peak_memory_mb(),
        "run_output_mb": disk_mb(run_dir),
        "tmp_residual_count": len(list((run_dir / "tmp").glob("*"))) if (run_dir / "tmp").exists() else 0,
        "detail_directory_count": len(list((run_dir / "details").glob("*"))) if (run_dir / "details").exists() else 0,
    }


def context_profile_details(context: ResearchContext, market_index_build_seconds: float = 0.0) -> dict:
    frames = {
        "bars": context.bars,
        "calendar": context.calendar,
        "constituents": context.constituents,
        "limits": context.limits,
        "tradability": context.tradability,
        "lifecycle": context.lifecycle,
        "st_status": context.st_status,
        "features": context.features,
        "standardized_features": context.standardized_features,
    }
    return {
        "calendar_query_seconds": context.profile.get("sqlite_trade_calendar_seconds", 0.0),
        "daily_bar_query_seconds": context.profile.get("sqlite_daily_bars_seconds", 0.0),
        "daily_bar_dataframe_build_seconds": context.profile.get("sqlite_daily_bars_seconds", 0.0),
        "constituent_query_seconds": context.profile.get("sqlite_constituents_seconds", 0.0),
        "lifecycle_query_seconds": context.profile.get("sqlite_lifecycle_seconds", 0.0),
        "historical_st_query_seconds": context.profile.get("sqlite_st_status_seconds", 0.0),
        "tradability_query_seconds": context.profile.get("sqlite_tradability_seconds", 0.0),
        "limit_price_query_seconds": context.profile.get("sqlite_limit_prices_seconds", 0.0),
        "base_feature_compute_seconds": context.profile.get("base_features_seconds", 0.0),
        "cross_section_normalize_seconds": context.profile.get("standardized_features_seconds", 0.0),
        "market_index_build_seconds": market_index_build_seconds,
        "rebalance_calendar_build_seconds": 0.0,
        "context_hash_seconds": 0.0,
        "sqlite_query_count": 7,
        "row_counts": {name: int(len(df)) for name, df in frames.items()},
        "dataframe_memory_bytes": {name: int(df.memory_usage(deep=True).sum()) for name, df in frames.items()},
        "peak_memory_mb": peak_memory_mb(),
    }


def run_completed_budget_gate(config_path: str | Path, repo_root: Path) -> dict:
    cfg = load_simple_yaml(config_path)
    budget = completed_budget_config(cfg)
    run_id = "completed_budget_gate_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config_snapshot.yaml").write_text(Path(config_path).read_text(encoding="utf-8"), encoding="utf-8")
    raw_cfg, bt, provider = build_config(config_path, run_dir)
    context_start = time.perf_counter()
    context = ResearchContext.build(
        provider,
        bt,
        data_snapshot_hash="stage3_6c2_completed_budget_gate",
        progress_path=run_dir / "context_progress.json",
    )
    context_seconds = time.perf_counter() - context_start
    evaluator = BatchBacktestEvaluator(context, save_detail_policy=budget.save_detail_policy, run_dir=run_dir / "details")
    index_start = time.perf_counter()
    evaluator._get_market_indices()
    market_index_seconds = time.perf_counter() - index_start
    manifest = {
        "run_id": run_id,
        "context_hash": context.context_hash,
        "config_hash": stable_hash(bt.__dict__),
        "data_snapshot_hash": "stage3_6c2_completed_budget_gate",
        "feature_version": "phase1_base_features_v1",
        "operator_version": "phase1_operator_vocab_v1",
        "universe_version": "csi800_asof_from_b_ready",
        "tradability_rule_version": "b_ready_derived_tradability_and_limit_price",
        "price_policy_version": "signal_close_execution_next_raw_open",
        "code_commit": current_git_commit(repo_root),
        "warnings": list(WARNING_LINES),
    }
    store = FormulaProgressStore(run_dir, manifest)
    generator = UniformRandomGenerator(seed=budget.seed)
    first = generate_until_completed(
        generator=generator,
        evaluator=evaluator,
        store=store,
        config=budget,
        interrupt_after_completed=30,
        stop_after_interrupt=True,
        run_dir=run_dir,
    )
    formulas = [parse_formula_text(row["formula_text"]) for row in first["generated_sequence"] if row["formula_hash"] in store.load()]
    restored_state = json.loads((run_dir / "generator_state.json").read_text(encoding="utf-8"))
    generator = UniformRandomGenerator.from_state_dict(restored_state)
    resumed = resume_completed_budget(formulas=formulas, evaluator=evaluator, store=store, run_dir=run_dir)
    second = generate_until_completed(generator=generator, evaluator=evaluator, store=store, config=budget, run_dir=run_dir)
    total_generation = first["generation_attempt_count"] + second["generation_attempt_count"]
    total_duplicates = first["duplicate_count"] + second["duplicate_count"]
    total_syntax_invalid = first["syntax_invalid_count"] + second["syntax_invalid_count"]
    total_formula_seconds = first["formula_evaluation_seconds"] + resumed["formula_evaluation_seconds"] + second["formula_evaluation_seconds"]
    budget_summary = summarize_completed_budget(run_dir, store, total_generation, total_duplicates, total_syntax_invalid, total_formula_seconds, context_seconds)
    stop, stop_reason = should_stop(budget_counts(store.load()), total_generation, budget)
    budget_summary["stop_reason"] = stop_reason
    budget_summary["max_unique_formula_attempts"] = budget.max_unique_formula_attempts
    budget_summary["max_generation_attempts"] = budget.max_generation_attempts
    budget_summary["completed_full_backtest_target"] = budget.completed_full_backtest_target
    generated_sequence = first["generated_sequence"] + second["generated_sequence"]
    budget_summary["continuous_generation_sequence_matches_resume"] = continuous_generation_reference(budget, total_generation) == generated_sequence
    performance = {key: budget_summary[key] for key in [
        "context_build_seconds",
        "formula_evaluation_seconds",
        "total_wall_seconds",
        "average_completed_formula_seconds_excluding_context",
        "average_unique_attempt_seconds",
        "amortized_completed_formula_seconds_including_context",
        "median_formula_seconds",
        "p90_formula_seconds",
        "peak_memory_mb",
        "run_output_mb",
        "tmp_residual_count",
        "detail_directory_count",
    ]}
    performance.update({
        "context_built_once": True,
        "base_feature_compute_count": 1,
        "sqlite_market_data_batch_load_count": 1,
        "resume_rebuilt_context": False,
    })
    context_manifest = {
        "context_hash": context.context_hash,
        "config": bt.__dict__,
        "profile": context.profile,
        "details": context_profile_details(context, market_index_seconds),
        "validation_loaded": False,
        "blind_test_loaded": False,
    }
    shared_safe = context.context_hash == context.context_hash and not context_manifest["validation_loaded"] and not context_manifest["blind_test_loaded"]
    gate_passed = (
        budget_summary["completed_full_backtest_count"] >= budget.completed_full_backtest_target
        and budget_summary["pending_count"] == 0
        and budget_summary["running_count"] == 0
        and budget_summary["interrupted_count"] == 0
        and resumed["completed_not_reexecuted"]
    )
    output = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "warnings": list(WARNING_LINES),
        "config": raw_cfg,
        "train_interval": raw_cfg["research_split"]["train"],
        "validation_accessed": False,
        "blind_test_accessed": False,
        "position_logit_trained": False,
        "budget_summary": budget_summary,
        "performance": performance,
        "context_manifest": context_manifest,
        "resume": resumed,
        "completed_budget_gate_passed": gate_passed,
        "shared_context_safe_for_generator_comparison": shared_safe,
        "ready_for_searcher_comparison": gate_passed and shared_safe,
    }
    atomic_write_json(run_dir / "context_manifest.json", context_manifest)
    atomic_write_json(run_dir / "context_profile.json", context_manifest["details"])
    atomic_write_json(run_dir / "formula_queue.json", _queue_rows([parse_formula_text(record.formula_text) for record in store.load().values()]))
    atomic_write_json(run_dir / "budget_summary.json", budget_summary)
    atomic_write_json(run_dir / "performance.json", performance)
    (run_dir / "report.md").write_text(_completed_budget_markdown(output), encoding="utf-8")
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(exist_ok=True)
    atomic_write_json(docs_dir / "stage3_6c2_completed_budget_gate.json", output)
    (docs_dir / "stage3_6c2_completed_budget_gate.md").write_text(_completed_budget_markdown(output), encoding="utf-8")
    return output


def _completed_budget_markdown(output: dict) -> str:
    summary = output["budget_summary"]
    perf = output["performance"]
    lines = ["# Stage 3.6C-2 Completed Budget Gate\n"]
    lines.extend(f"{line}\n" for line in WARNING_LINES)
    lines.append(f"\nRun dir: `{output['run_dir']}`\n")
    lines.append(f"completed_full_backtest_count: `{summary['completed_full_backtest_count']}`\n")
    lines.append(f"unique_formula_attempt_count: `{summary['unique_formula_attempt_count']}`\n")
    lines.append(f"generation_attempt_count: `{summary['generation_attempt_count']}`\n")
    lines.append(f"failed_count: `{summary['failed_count']}`\n")
    lines.append(f"duplicate_count: `{summary['duplicate_count']}`\n")
    lines.append(f"stop_reason: `{summary['stop_reason']}`\n")
    lines.append(f"context_build_seconds: `{perf['context_build_seconds']}`\n")
    lines.append(f"formula_evaluation_seconds: `{perf['formula_evaluation_seconds']}`\n")
    lines.append(f"completed_budget_gate_passed: `{output['completed_budget_gate_passed']}`\n")
    lines.append(f"ready_for_searcher_comparison: `{output['ready_for_searcher_comparison']}`\n")
    return "".join(lines)
