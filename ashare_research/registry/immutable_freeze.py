from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Iterable


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_canonical_json(path: Path, payload: object) -> str:
    data = canonical_json_bytes(payload)
    atomic_write_bytes(path, data)
    return sha256_bytes(data)


def copy_payload_files(repo_root: Path, payload_root: Path, relative_paths: Iterable[str]) -> list[dict]:
    records: list[dict] = []
    for rel in sorted(str(p) for p in relative_paths):
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise ValueError(f"invalid_relative_path:{rel}")
        src = repo_root / rel
        dst = payload_root / rel
        if not src.is_file():
            raise FileNotFoundError(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        records.append(
            {
                "relative_path": rel,
                "size_bytes": dst.stat().st_size,
                "sha256": sha256_file(dst),
            }
        )
    return records


def chmod_tree_readonly(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    root.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)


def verify_payload_files(payload_root: Path, payload_files: list[dict]) -> bool:
    for row in payload_files:
        rel = row["relative_path"]
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            return False
        path = payload_root / rel
        if not path.is_file():
            return False
        if path.stat().st_size != int(row["size_bytes"]):
            return False
        if sha256_file(path) != row["sha256"]:
            return False
    return True


def payload_manifest_hash(manifest_path: Path) -> str:
    return sha256_file(manifest_path)


def verify_freeze_directory(freeze_dir: Path) -> dict[str, bool | str]:
    payload_manifest_path = freeze_dir / "payload_manifest.json"
    freeze_manifest_path = freeze_dir / "freeze_manifest.json"
    sidecar_path = freeze_dir / "freeze_manifest.sha256"
    sealed_path = freeze_dir / "SEALED"

    payload_manifest = json.loads(payload_manifest_path.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    payload_hash = payload_manifest_hash(payload_manifest_path)
    freeze_hash = sha256_file(freeze_manifest_path)
    sidecar_ok = sidecar_path.read_text(encoding="utf-8") == f"{freeze_hash}  freeze_manifest.json\n"

    return {
        "payload_files_verified": verify_payload_files(freeze_dir / "payload", payload_manifest["payload_files"]),
        "payload_manifest_verified": payload_hash == freeze_manifest["payload_manifest_hash"],
        "freeze_id_verified": payload_hash == freeze_manifest["freeze_id"],
        "freeze_manifest_hash_verified": sidecar_ok,
        "sealed_marker_present": sealed_path.is_file(),
        "payload_manifest_hash": payload_hash,
        "freeze_manifest_hash": freeze_hash,
    }
