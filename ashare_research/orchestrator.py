from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.expression import Expression
from ashare_research.mining.candidate_pool import Candidate, CandidatePool
from ashare_research.mining.checkpoint import save_checkpoint
from ashare_research.mining.deduplicator import FormulaDeduplicator
from ashare_research.mining.generator import FormulaGenerator
from ashare_research.mining.model import AlphaGPTLite
from ashare_research.mining.reward import invalid_reward, reward_from_metrics
from ashare_research.mining.trainer import ReinforceTrainer
from ashare_research.registry.artifacts import sha256_file, stable_hash
from ashare_research.registry.database import ResearchRegistry
from ashare_research.reporting.mining_report import write_mining_report


REQUIRED_FORMAL_FIELDS = {
    "research_split": ["train_start", "train_end", "validation_start", "validation_end", "blind_test_start", "blind_test_end"],
    "backtest": ["rebalance_frequency", "top_n", "initial_cash", "one_way_cost_bps", "unknown_tradability_policy"],
    "mining": ["batch_size", "max_iterations", "candidate_pool_size", "validation_shortlist_size", "min_valid_rows", "min_trade_count"],
}


class ResearchOrchestrator:
    def __init__(self, config_path: str | Path, repo_root: str | Path):
        self.config_path = Path(config_path)
        self.repo_root = Path(repo_root)
        self.cfg = load_simple_yaml(self.config_path)
        self.run_id = "mine_" + uuid.uuid4().hex[:12]
        self.run_dir = self.repo_root / self.cfg.get("output", {}).get("runs_dir", "runs") / self.run_id
        self.registry = ResearchRegistry(self.repo_root / self.cfg.get("registry", {}).get("path", "runs/research_registry.sqlite3"))

    def validate_config(self) -> None:
        if self.cfg.get("test_only") is True:
            return
        missing: list[str] = []
        for section, keys in REQUIRED_FORMAL_FIELDS.items():
            values = self.cfg.get(section, {})
            for key in keys:
                if values.get(key) is None:
                    missing.append(f"{section}.{key}")
        if missing:
            raise ValueError(f"Missing formal research parameters: {missing}")

    def run(self) -> dict:
        self.validate_config()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        created_at = utc_now()
        config_text = self.config_path.read_text(encoding="utf-8")
        config_hash = stable_hash(self.cfg)
        data_snapshot = json.loads((self.repo_root / "docs/b_ready_data_snapshot.json").read_text(encoding="utf-8"))
        data_snapshot_hash = data_snapshot.get("snapshot_hash") or data_snapshot.get("hash") or stable_hash(data_snapshot)
        seed = int(self.cfg.get("mining", {}).get("seed", 0))
        git_commit = current_git_commit(self.repo_root)
        manifest = {
            "run_id": self.run_id,
            "test_only": self.cfg.get("test_only") is True,
            "created_at": created_at,
            "git_commit": git_commit,
            "config_hash": config_hash,
            "data_snapshot_hash": data_snapshot_hash,
            "seed": seed,
        }
        self._write_text("config_snapshot.yaml", config_text)
        self._write_json("data_snapshot.json", data_snapshot)
        self._write_json("manifest.json", manifest)
        self.registry.upsert_run(
            run_id=self.run_id,
            status="running",
            created_at=created_at,
            completed_at=None,
            git_commit=git_commit,
            config_hash=config_hash,
            data_snapshot_hash=data_snapshot_hash,
            seed=seed,
            current_iteration=0,
            model_checkpoint=None,
            error_message=None,
        )

        model = AlphaGPTLite(seed=seed, learning_rate=float(self.cfg.get("mining", {}).get("learning_rate", 0.05)))
        generator = FormulaGenerator(model)
        trainer = ReinforceTrainer(model)
        dedup = FormulaDeduplicator()
        pool = CandidatePool(capacity=int(self.cfg["mining"]["candidate_pool_size"]))
        provider = self._provider()
        base_config = self._base_backtest_config()
        train_split, validation_split, blind_split = self._splits()
        history: list[dict] = []
        eval_cache: dict[tuple, tuple[dict, float, str]] = {}
        stats = {
            "generated_count": 0,
            "syntax_valid_count": 0,
            "unique_count": 0,
            "backtest_count": 0,
            "cache_hit_count": 0,
            "update_skipped_count": 0,
            "update_skipped_reasons": {},
            "failure_reasons": {},
        }

        for iteration in range(1, int(self.cfg["mining"]["max_iterations"]) + 1):
            generated_batch = generator.generate_batch(int(self.cfg["mining"]["batch_size"]))
            batch_updates: list[tuple[object, float]] = []
            for generated in generated_batch:
                stats["generated_count"] += 1
                expr = generated.expression
                valid, reason = expr.validate()
                if not valid:
                    reward_result = invalid_reward(reason or "invalid_formula")
                    batch_updates.append((generated, reward_result.reward))
                    self._bump_failure(stats, reward_result.failure_reason)
                    continue
                stats["syntax_valid_count"] += 1
                formula_hash = expr.sha256()
                if not dedup.accept(formula_hash):
                    stats["cache_hit_count"] += 1
                    continue
                stats["unique_count"] += 1
                metrics, reward, bt_run_dir = self._evaluate_cached(
                    provider, base_config, train_split, expr, "train", base_config.cost_bps, eval_cache
                )
                stats["backtest_count"] += 1
                reward_result = reward_from_metrics(metrics, min_trade_count=int(self.cfg["mining"]["min_trade_count"]))
                batch_updates.append((generated, reward_result.reward))
                candidate = Candidate(
                    formula_hash=formula_hash,
                    formula_text=expr.to_string(),
                    token_sequence=list(expr.tokens),
                    formula_length=len(expr.tokens),
                    train_metrics=metrics,
                    train_reward=reward_result.reward,
                    validity_status=reward_result.validity_status,
                    failure_reason=reward_result.failure_reason,
                    data_snapshot_hash=str(data_snapshot_hash),
                    backtest_config_hash=self._backtest_hash(base_config),
                    model_checkpoint=None,
                    created_iteration=iteration,
                )
                pool.add(candidate)
                self.registry.insert_formula(
                    formula_hash=formula_hash,
                    formula_text=expr.to_string(),
                    token_sequence=list(expr.tokens),
                    formula_length=len(expr.tokens),
                    syntax_valid=True,
                    execution_valid=reward_result.validity_status == "valid",
                    failure_reason=reward_result.failure_reason,
                    first_seen_run_id=self.run_id,
                )
                self.registry.insert_evaluation(
                    run_id=self.run_id,
                    formula_hash=formula_hash,
                    dataset_split="train",
                    cost_bps=base_config.cost_bps,
                    reward=reward_result.reward,
                    metrics=metrics,
                    evaluated_at=utc_now(),
                )
                if reward_result.failure_reason:
                    self._bump_failure(stats, reward_result.failure_reason)
                history.append({"iteration": iteration, "formula_hash": formula_hash, "reward": reward_result.reward, "backtest_run_dir": bt_run_dir})

            skip_reason = trainer.update_batch(batch_updates)
            if skip_reason:
                stats["update_skipped_count"] += 1
                stats["update_skipped_reasons"][skip_reason] = stats["update_skipped_reasons"].get(skip_reason, 0) + 1

            checkpoint_path = self.run_dir / "checkpoints" / f"iteration_{iteration}.json"
            checkpoint_hash = save_checkpoint(
                checkpoint_path,
                run_id=self.run_id,
                iteration=iteration,
                model=model,
                metadata={"config_hash": config_hash, "data_snapshot_hash": data_snapshot_hash, "vocabulary_version": "phase1-fixed"},
            )
            self.registry.upsert_run(
                run_id=self.run_id,
                status="running",
                created_at=created_at,
                completed_at=None,
                git_commit=git_commit,
                config_hash=config_hash,
                data_snapshot_hash=data_snapshot_hash,
                seed=seed,
                current_iteration=iteration,
                model_checkpoint=str(checkpoint_path),
                error_message=None,
            )

        train_candidates = [c.__dict__ for c in pool.ranked()]
        train_hash = stable_hash(train_candidates)
        validation_results = self._evaluate_candidates(provider, base_config, validation_split, train_candidates, "validation", eval_cache)
        shortlist_size = int(self.cfg["mining"]["validation_shortlist_size"])
        shortlist = sorted(validation_results, key=lambda r: (-float(r["reward"]), r["formula_hash"]))[:shortlist_size]
        shortlist_hash = stable_hash(shortlist)
        blind_results = self._evaluate_candidates(provider, base_config, blind_split, shortlist, "blind_test", eval_cache)

        summary = {
            "status": "complete",
            **stats,
            "model_update_count": trainer.update_count,
            "train_candidate_count": len(train_candidates),
            "train_candidates_hash": train_hash,
            "validation_result_count": len(validation_results),
            "shortlist_count": len(shortlist),
            "shortlist_hash": shortlist_hash,
            "blind_test_result_count": len(blind_results),
            "primary_reward": "train_sortino_net_of_primary_cost",
            "cost_sensitivity_bps": self.cfg.get("cost", {}).get("sensitivity_one_way_bps", [10, 20, 40]),
            "checkpoint_hash": checkpoint_hash,
        }

        self._write_json("training_history.json", history)
        self._write_parquet("train_candidates.parquet", train_candidates)
        self._write_parquet("validation_results.parquet", validation_results)
        self._write_json("shortlist.json", {"shortlist_hash": shortlist_hash, "formulas": shortlist})
        self._write_parquet("blind_test_results.parquet", blind_results)
        write_mining_report(self.run_dir / "report.md", run_id=self.run_id, manifest=manifest, summary=summary)
        self._register_artifacts()
        self.registry.upsert_run(
            run_id=self.run_id,
            status="complete",
            created_at=created_at,
            completed_at=utc_now(),
            git_commit=git_commit,
            config_hash=config_hash,
            data_snapshot_hash=data_snapshot_hash,
            seed=seed,
            current_iteration=int(self.cfg["mining"]["max_iterations"]),
            model_checkpoint=str(checkpoint_path),
            error_message=None,
        )
        return {"run_id": self.run_id, "run_dir": str(self.run_dir), "summary": summary}

    def _evaluate_candidates(self, provider, base_config, split, candidates: list[dict], split_name: str, eval_cache: dict) -> list[dict]:
        rows: list[dict] = []
        sensitivity = list(self.cfg.get("cost", {}).get("sensitivity_one_way_bps", [10, 20, 40]))
        primary = base_config.cost_bps
        for candidate in candidates:
            expr = Expression(tuple(candidate["token_sequence"]))
            metrics, reward, bt_run_dir = self._evaluate_cached(provider, base_config, split, expr, split_name, primary, eval_cache)
            row = {
                "formula_hash": candidate["formula_hash"],
                "formula_text": candidate["formula_text"],
                "token_sequence": candidate["token_sequence"],
                "dataset_split": split_name,
                "cost_bps": primary,
                "reward": reward,
                "metrics": metrics,
                "backtest_run_dir": bt_run_dir,
            }
            for bps in sensitivity:
                metrics_s, reward_s, _ = self._evaluate_cached(provider, base_config, split, expr, split_name, float(bps), eval_cache)
                row[f"metrics_{bps}bps"] = metrics_s
                row[f"reward_{bps}bps"] = reward_s
            rows.append(row)
            self.registry.insert_evaluation(
                run_id=self.run_id,
                formula_hash=candidate["formula_hash"],
                dataset_split=split_name,
                cost_bps=primary,
                reward=reward,
                metrics=metrics,
                evaluated_at=utc_now(),
            )
        return rows

    def _evaluate_cached(self, provider, base_config, split, expr: Expression, split_name: str, cost_bps: float, cache: dict) -> tuple[dict, float, str]:
        cfg = replace(base_config, start_date=split[0], end_date=split[1], cost_bps=float(cost_bps))
        key = (expr.sha256(), self._backtest_hash(cfg), split_name, float(cost_bps))
        if key in cache:
            return cache[key]
        try:
            result = DeterministicBacktestEngine(provider, cfg).run(expr)
            metrics = result["metrics"]
            run_dir = str(result["run_dir"])
            reward = reward_from_metrics(metrics, min_trade_count=int(self.cfg["mining"]["min_trade_count"]))
        except Exception as exc:  # noqa: BLE001
            metrics = {"status": "failed", "failure_reason": str(exc)}
            run_dir = ""
            reward = invalid_reward(str(exc))
        cache[key] = (metrics, reward.reward, run_dir)
        return cache[key]

    def _provider(self) -> LocalSQLiteProvider:
        data_cfg = self.cfg["data"]
        if data_cfg.get("allow_network", False):
            raise ValueError("Mining requires allow_network=false")
        return LocalSQLiteProvider(self.repo_root / data_cfg["sqlite_path"], self.repo_root / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"))

    def _base_backtest_config(self) -> BacktestConfig:
        b = dict(self.cfg["backtest"])
        cost = self.cfg.get("cost", {})
        b["start_date"] = "19000101"
        b["end_date"] = "19000102"
        b["cost_bps"] = b.get("one_way_cost_bps", cost.get("primary_one_way_bps"))
        cfg = {
            **self.cfg,
            "backtest": b,
            "cost": {"primary_one_way_bps": b["cost_bps"]},
            "output": {"runs_dir": str(self.run_dir / "backtests")},
            "storage": {**self.cfg.get("storage", {}), "temp_dir": str(self.run_dir / "tmp")},
        }
        return BacktestConfig.from_dict(cfg)

    def _splits(self) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
        s = self.cfg["research_split"]
        train = tuple(s.get("train") or [s["train_start"], s["train_end"]])
        validation = tuple(s.get("validation") or [s["validation_start"], s["validation_end"]])
        blind = tuple(s.get("blind_test") or [s["blind_test_start"], s["blind_test_end"]])
        if not (train[1] < validation[0] and validation[1] < blind[0]):
            raise ValueError("overlapping_or_unordered_research_split")
        return train, validation, blind

    def _backtest_hash(self, config: BacktestConfig) -> str:
        return stable_hash(config.__dict__)

    def _write_json(self, name: str, payload: object) -> None:
        (self.run_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")

    def _write_text(self, name: str, text: str) -> None:
        (self.run_dir / name).write_text(text, encoding="utf-8")

    def _write_parquet(self, name: str, rows: list[dict]) -> None:
        pd.DataFrame(rows).to_parquet(self.run_dir / name, index=False)

    def _register_artifacts(self) -> None:
        for path in self.run_dir.glob("*"):
            if path.is_file():
                self.registry.insert_artifact(run_id=self.run_id, artifact_type=path.name, path=str(path), sha256=sha256_file(path), created_at=utc_now())

    @staticmethod
    def _bump_failure(stats: dict, reason: str | None) -> None:
        key = reason or "unknown"
        stats["failure_reasons"][key] = stats["failure_reasons"].get(key, 0) + 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    except Exception:
        return "unknown"
