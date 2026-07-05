from __future__ import annotations

import json
from pathlib import Path


def write_mining_report(path: Path, *, run_id: str, manifest: dict, summary: dict) -> None:
    path.write_text(
        "\n".join(
            [
                "# AlphaGPT Mining Report",
                "",
                "ENGINEERING MINING TEST ONLY" if manifest.get("test_only") else "RESEARCH RUN REPORT",
                "NOT A VALIDATED INVESTMENT STRATEGY",
                "B-READY DATA WITH APPROXIMATE TRADABILITY",
                "BLIND TEST RESULTS MUST NOT BE USED FOR RETRAINING",
                "",
                f"- run_id: `{run_id}`",
                f"- status: `{summary.get('status')}`",
                f"- config_hash: `{manifest.get('config_hash')}`",
                f"- data_snapshot_hash: `{manifest.get('data_snapshot_hash')}`",
                f"- seed: `{manifest.get('seed')}`",
                "",
                "## Summary",
                "",
                "```json",
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
                "```",
                "",
                "## Limitations",
                "",
                "- Current data remains B-ready, not A-grade strict backtest data.",
                "- Official full-history suspension records remain incomplete.",
                "- CSI800 ex-finance total-return benchmark is not confirmed.",
                "- Historical industry classification remains unresolved.",
                "- Smoke mining parameters are engineering checks only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
