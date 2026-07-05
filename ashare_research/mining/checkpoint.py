from __future__ import annotations

import json
from pathlib import Path

from .model import AlphaGPTLite


def save_checkpoint(path: Path, *, run_id: str, iteration: int, model: AlphaGPTLite, metadata: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "iteration": iteration,
        "model": model.state_dict(),
        "metadata": metadata,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return model.state_hash()


def load_checkpoint(path: Path, *, run_id: str, config_hash: str, data_snapshot_hash: str) -> tuple[int, AlphaGPTLite, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["run_id"] != run_id:
        raise ValueError("checkpoint_run_id_mismatch")
    meta = payload["metadata"]
    if meta.get("config_hash") != config_hash:
        raise ValueError("checkpoint_config_hash_mismatch")
    if meta.get("data_snapshot_hash") != data_snapshot_hash:
        raise ValueError("checkpoint_data_snapshot_hash_mismatch")
    return int(payload["iteration"]), AlphaGPTLite.from_state_dict(payload["model"]), meta
