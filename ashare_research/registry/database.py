from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class ResearchRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    git_commit TEXT,
                    config_hash TEXT NOT NULL,
                    data_snapshot_hash TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    current_iteration INTEGER NOT NULL,
                    model_checkpoint TEXT,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS formulas (
                    formula_hash TEXT PRIMARY KEY,
                    formula_text TEXT NOT NULL,
                    token_sequence TEXT NOT NULL,
                    formula_length INTEGER NOT NULL,
                    syntax_valid INTEGER NOT NULL,
                    execution_valid INTEGER NOT NULL,
                    failure_reason TEXT,
                    first_seen_run_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evaluations (
                    run_id TEXT NOT NULL,
                    formula_hash TEXT NOT NULL,
                    dataset_split TEXT NOT NULL,
                    cost_bps REAL NOT NULL,
                    reward REAL,
                    metrics_json TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, formula_hash, dataset_split, cost_bps)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, artifact_type, path)
                );
                """
            )

    def upsert_run(self, **row) -> None:
        cols = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "run_id")
        with self._connect() as con:
            con.execute(f"INSERT INTO runs ({cols}) VALUES ({placeholders}) ON CONFLICT(run_id) DO UPDATE SET {updates}", list(row.values()))

    def insert_formula(self, **row) -> None:
        row["token_sequence"] = json.dumps(row["token_sequence"], ensure_ascii=False)
        with self._connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO formulas
                (formula_hash, formula_text, token_sequence, formula_length, syntax_valid, execution_valid, failure_reason, first_seen_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    row["formula_hash"],
                    row["formula_text"],
                    row["token_sequence"],
                    row["formula_length"],
                    int(row["syntax_valid"]),
                    int(row["execution_valid"]),
                    row.get("failure_reason"),
                    row["first_seen_run_id"],
                ],
            )

    def insert_evaluation(self, **row) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO evaluations
                (run_id, formula_hash, dataset_split, cost_bps, reward, metrics_json, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    row["run_id"],
                    row["formula_hash"],
                    row["dataset_split"],
                    float(row["cost_bps"]),
                    row.get("reward"),
                    json.dumps(row["metrics"], ensure_ascii=False, sort_keys=True),
                    row["evaluated_at"],
                ],
            )

    def insert_artifact(self, **row) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO artifacts (run_id, artifact_type, path, sha256, created_at) VALUES (?, ?, ?, ?, ?)",
                [row["run_id"], row["artifact_type"], row["path"], row["sha256"], row["created_at"]],
            )

    def status(self, run_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM runs WHERE run_id=?", [run_id]).fetchone()
            return dict(row) if row else None
