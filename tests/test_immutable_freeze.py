from __future__ import annotations

import json
from pathlib import Path

from ashare_research.registry.immutable_freeze import (
    canonical_json_bytes,
    copy_payload_files,
    sha256_bytes,
    verify_freeze_directory,
    write_canonical_json,
)


def _make_freeze(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a").mkdir()
    (repo / "a" / "one.txt").write_text("one", encoding="utf-8")
    (repo / "b.txt").write_text("two", encoding="utf-8")
    freeze_dir = tmp_path / "freeze"
    payload_files = copy_payload_files(repo, freeze_dir / "payload", ["b.txt", "a/one.txt"])
    payload_manifest = {
        "schema_version": 1,
        "protocol_id": "trade_recommendation_b_v1",
        "created_at_excluded_from_hash": "not_present",
        "payload_files": payload_files,
    }
    payload_manifest.pop("created_at_excluded_from_hash")
    payload_hash = write_canonical_json(freeze_dir / "payload_manifest.json", payload_manifest)
    freeze_manifest = {
        "schema_version": 1,
        "freeze_id": payload_hash,
        "payload_manifest_hash": payload_hash,
        "created_at": "2026-06-27T00:00:00Z",
    }
    freeze_hash = write_canonical_json(freeze_dir / "freeze_manifest.json", freeze_manifest)
    (freeze_dir / "freeze_manifest.sha256").write_text(f"{freeze_hash}  freeze_manifest.json\n", encoding="utf-8")
    (freeze_dir / "SEALED").write_text("sealed\n", encoding="utf-8")
    return freeze_dir


def test_payload_file_change_fails_verification(tmp_path: Path) -> None:
    freeze_dir = _make_freeze(tmp_path)
    assert verify_freeze_directory(freeze_dir)["payload_files_verified"] is True
    (freeze_dir / "payload" / "b.txt").write_text("changed", encoding="utf-8")
    assert verify_freeze_directory(freeze_dir)["payload_files_verified"] is False


def test_payload_manifest_change_fails_freeze_id_verification(tmp_path: Path) -> None:
    freeze_dir = _make_freeze(tmp_path)
    manifest_path = freeze_dir / "payload_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["protocol_id"] = "changed"
    write_canonical_json(manifest_path, manifest)
    result = verify_freeze_directory(freeze_dir)
    assert result["payload_manifest_verified"] is False
    assert result["freeze_id_verified"] is False


def test_freeze_manifest_change_fails_sidecar_verification(tmp_path: Path) -> None:
    freeze_dir = _make_freeze(tmp_path)
    manifest_path = freeze_dir / "freeze_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = "changed"
    write_canonical_json(manifest_path, manifest)
    assert verify_freeze_directory(freeze_dir)["freeze_manifest_hash_verified"] is False


def test_project_status_and_created_at_do_not_affect_payload_hash(tmp_path: Path) -> None:
    payload = {"payload_files": [{"relative_path": "a", "sha256": "x", "size_bytes": 1}], "schema_version": 1}
    first = sha256_bytes(canonical_json_bytes(payload))
    (tmp_path / "PROJECT_STATUS.md").write_text("changed outside payload\n", encoding="utf-8")
    assert sha256_bytes(canonical_json_bytes(payload)) == first
    assert "created_at" not in payload


def test_file_order_does_not_affect_payload_records(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a", encoding="utf-8")
    (repo / "b.txt").write_text("b", encoding="utf-8")
    one = copy_payload_files(repo, tmp_path / "one", ["b.txt", "a.txt"])
    two = copy_payload_files(repo, tmp_path / "two", ["a.txt", "b.txt"])
    assert one == two


def test_absolute_path_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        copy_payload_files(repo, tmp_path / "payload", [str(tmp_path / "abs.txt")])
    except ValueError as exc:
        assert "invalid_relative_path" in str(exc)
    else:
        raise AssertionError("absolute path accepted")
