from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ashare_research.registry.artifacts import stable_hash


class CheckpointV2:
    def __init__(self, run_dir: str | Path, config_hash: str):
        self.run_dir = Path(run_dir)
        self.config_hash = config_hash
        self.path = self.run_dir / "checkpoints" / "pipeline_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, stage: str, payload: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        data = {"stage": stage, "config_hash": self.config_hash, "payload_hash": stable_hash(payload), "payload": payload}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("config_hash") != self.config_hash:
            raise ValueError("checkpoint_config_hash_mismatch")
        return data

