from __future__ import annotations

import json
from pathlib import Path


def write_backtest_report(path: Path, *, run_id: str, metrics: dict, benchmark: dict) -> None:
    path.write_text(
        "\n".join(
            [
                "# Engineering Backtest Report",
                "",
                "ENGINEERING BACKTEST ONLY",
                "NOT A VALIDATED INVESTMENT STRATEGY",
                "B-READY DATA WITH APPROXIMATE TRADABILITY",
                "",
                f"- run_id: `{run_id}`",
                f"- benchmark_unavailable: `{benchmark.get('benchmark_unavailable')}`",
                "- industry_exclusion: `not_implemented_due_to_incomplete_historical_industry_data`",
                "- missing_valuation_policy: `missing_close_carried_last_price_when_prior_price_exists`",
                "- benchmark_note: `no formal CSI800 ex-finance total-return benchmark is used`",
                "",
                "## Metrics",
                "",
                "```json",
                json.dumps(metrics, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
