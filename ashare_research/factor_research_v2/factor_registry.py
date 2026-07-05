from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EVALUATION_VERSION = "factor_research_v2_mvp_v1"


class FactorRegistryV2:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "factor_events.jsonl"
        self.quarantine_path = self.root / "quarantine_events.jsonl"

    @staticmethod
    def event_id(run_id: str, formula_hash: str, evaluation_version: str = EVALUATION_VERSION) -> str:
        return f"{run_id}:{formula_hash}:{evaluation_version}"

    def existing_event_ids(self) -> set[str]:
        ids: set[str] = set()
        if not self.path.exists():
            return ids
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                event_id = record.get("registry_event_id")
                if not event_id and record.get("first_seen_run_id") and record.get("formula_hash"):
                    event_id = self.event_id(str(record["first_seen_run_id"]), str(record["formula_hash"]), str(record.get("evaluation_version", EVALUATION_VERSION)))
                if event_id:
                    ids.add(str(event_id))
        return ids

    def append(self, record: dict[str, Any]) -> None:
        run_id = str(record.get("first_seen_run_id") or record.get("latest_evaluation_run_id") or "")
        formula_hash = str(record.get("formula_hash") or "")
        record.setdefault("evaluation_version", EVALUATION_VERSION)
        if run_id and formula_hash:
            record.setdefault("registry_event_id", self.event_id(run_id, formula_hash, str(record["evaluation_version"])))
        if record.get("registry_event_id") in self.existing_event_ids():
            return
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(payload + "\n")

    def append_many(self, records: list[dict[str, Any]]) -> dict[str, int]:
        before = self.existing_event_ids()
        skipped = 0
        appended = 0
        for record in records:
            self.append(record)
            after = self.existing_event_ids()
            if len(after) == len(before):
                skipped += 1
            else:
                appended += 1
                before = after
        return {"appended": appended, "skipped_duplicate": skipped}

    def quarantine_run(self, run_id: str, reason: str) -> None:
        event = {
            "run_id": run_id,
            "source_run_status": "invalid_resume_duplicate_run",
            "eligible_for_research_selection": False,
            "reason": reason,
        }
        existing = set()
        if self.quarantine_path.exists():
            for line in self.quarantine_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.add(json.loads(line).get("run_id"))
        if run_id in existing:
            return
        with self.quarantine_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def quarantined_run_ids(self) -> set[str]:
        if not self.quarantine_path.exists():
            return set()
        ids = set()
        for line in self.quarantine_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(str(json.loads(line).get("run_id")))
        return ids

    def active_records(self) -> list[dict[str, Any]]:
        quarantined = self.quarantined_run_ids()
        records: list[dict[str, Any]] = []
        if not self.path.exists():
            return records
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("first_seen_run_id") in quarantined or record.get("latest_evaluation_run_id") in quarantined:
                    continue
                if record.get("source_run_status") == "invalid_resume_duplicate_run":
                    continue
                if record.get("eligible_for_research_selection") is False:
                    continue
                records.append(record)
        return records
