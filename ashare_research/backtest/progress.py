from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ashare_research.registry.artifacts import stable_hash


TERMINAL_STATES = {"completed", "failed"}
VALID_STATES = {"pending", "running", "completed", "failed", "interrupted"}


def atomic_write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class FormulaProgressRecord:
    formula_hash: str
    formula_text: str
    status: str
    context_hash: str
    config_hash: str
    data_snapshot_hash: str
    code_commit: str
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    failure_reason: str | None = None
    summary_path: str | None = None
    summary_hash: str | None = None

    def with_update(self, **updates) -> "FormulaProgressRecord":
        data = self.__dict__.copy()
        data.update(updates)
        status = data["status"]
        if status not in VALID_STATES:
            raise ValueError(f"invalid_progress_status:{status}")
        return FormulaProgressRecord(**data)


class FormulaProgressStore:
    def __init__(self, run_dir: str | Path, manifest: dict):
        self.run_dir = Path(run_dir)
        self.manifest = manifest
        self.progress_path = self.run_dir / "progress.json"
        self.completed_path = self.run_dir / "completed_results.jsonl"
        self.pending_path = self.run_dir / "pending_formulas.json"
        self.failed_path = self.run_dir / "failed_formulas.json"
        self.interrupted_path = self.run_dir / "interrupted_formulas.json"
        self.summary_dir = self.run_dir / "summaries"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.run_dir / "manifest.json", manifest)
        if not self.progress_path.exists():
            atomic_write_json(self.progress_path, {})

    def load(self) -> dict[str, FormulaProgressRecord]:
        raw = json.loads(self.progress_path.read_text(encoding="utf-8")) if self.progress_path.exists() else {}
        return {key: FormulaProgressRecord(**value) for key, value in raw.items()}

    def save(self, records: dict[str, FormulaProgressRecord]) -> None:
        atomic_write_json(self.progress_path, {key: value.__dict__ for key, value in records.items()})
        atomic_write_json(self.pending_path, [r.__dict__ for r in records.values() if r.status == "pending"])
        atomic_write_json(self.failed_path, [r.__dict__ for r in records.values() if r.status == "failed"])
        atomic_write_json(self.interrupted_path, [r.__dict__ for r in records.values() if r.status == "interrupted"])

    def validate_manifest(self, expected: dict) -> None:
        keys = [
            "run_id",
            "context_hash",
            "config_hash",
            "data_snapshot_hash",
            "feature_version",
            "operator_version",
            "universe_version",
            "tradability_rule_version",
            "price_policy_version",
            "code_commit",
        ]
        for key in keys:
            if self.manifest.get(key) != expected.get(key):
                raise ValueError(f"resume_hash_mismatch:{key}")

    def initialize_queue(self, formulas: Iterable[tuple[str, str]]) -> None:
        records = self.load()
        now = time.time()
        for formula_hash, formula_text in formulas:
            if formula_hash not in records:
                records[formula_hash] = FormulaProgressRecord(
                    formula_hash=formula_hash,
                    formula_text=formula_text,
                    status="pending",
                    context_hash=self.manifest["context_hash"],
                    config_hash=self.manifest["config_hash"],
                    data_snapshot_hash=self.manifest["data_snapshot_hash"],
                    code_commit=self.manifest["code_commit"],
                    created_at=now,
                )
        self.save(records)

    def mark_running(self, formula_hash: str) -> None:
        records = self.load()
        record = records[formula_hash]
        if record.status == "completed":
            return
        records[formula_hash] = record.with_update(status="running", started_at=time.time(), failure_reason=None)
        self.save(records)

    def mark_interrupted_running(self) -> None:
        records = self.load()
        changed = False
        for key, record in list(records.items()):
            if record.status == "running":
                records[key] = record.with_update(status="interrupted")
                changed = True
        if changed:
            self.save(records)

    def write_summary(self, formula_hash: str, payload: dict) -> tuple[str, str]:
        summary_hash = stable_hash(payload)
        tmp_path = self.summary_dir / f"{formula_hash}.json.tmp"
        final_path = self.summary_dir / f"{formula_hash}.json"
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
        if stable_hash(json.loads(tmp_path.read_text(encoding="utf-8"))) != summary_hash:
            raise ValueError("summary_hash_verification_failed")
        os.replace(tmp_path, final_path)
        return str(final_path), summary_hash

    def mark_completed(self, formula_hash: str, summary_payload: dict) -> None:
        records = self.load()
        record = records[formula_hash]
        summary_path, summary_hash = self.write_summary(formula_hash, summary_payload)
        records[formula_hash] = record.with_update(
            status="completed",
            completed_at=time.time(),
            failure_reason=None,
            summary_path=summary_path,
            summary_hash=summary_hash,
        )
        self.save(records)
        with self.completed_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(records[formula_hash].__dict__, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def mark_failed(self, formula_hash: str, reason: str) -> None:
        records = self.load()
        record = records[formula_hash]
        records[formula_hash] = record.with_update(status="failed", completed_at=time.time(), failure_reason=reason)
        self.save(records)

    def completed_hashes(self) -> set[str]:
        return {key for key, record in self.load().items() if record.status == "completed"}

    def executable_hashes(self) -> list[str]:
        records = self.load()
        return [key for key, record in records.items() if record.status in {"pending", "interrupted"}]
