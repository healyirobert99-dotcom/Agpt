from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from ashare_research.mining.stage3_6b import build_config


WARNING_LINES = (
    "DIAGNOSTIC READ ONLY",
    "NO FEATURES COMPUTED",
    "NO BACKTEST EXECUTED",
    "NO VALIDATION OR BLIND TEST ACCESS",
)


def _rows(items) -> list[tuple]:
    return [tuple(item) for item in items]


def run_daily_bar_diagnosis(config_path: str | Path, repo_root: Path, *, batch_size: int = 10000) -> dict:
    run_id = "read_probe_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    cfg, bt, provider = build_config(config_path, run_dir)
    query = provider.daily_bars_query(bt.start_date, bt.end_date)
    with provider._connect() as con:
        table_info = _rows(con.execute("PRAGMA table_info(daily_price)").fetchall())
        index_list = _rows(con.execute("PRAGMA index_list(daily_price)").fetchall())
        index_info = {row[1]: _rows(con.execute(f"PRAGMA index_info({row[1]})").fetchall()) for row in index_list}
        explain = _rows(con.execute("EXPLAIN QUERY PLAN " + query["sql"], query["params"]).fetchall())
        count_sql = """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT p.ts_code) AS symbols,
                   MIN(p.trade_date) AS min_date,
                   MAX(p.trade_date) AS max_date
            FROM daily_price p
            LEFT JOIN daily_basic b ON b.ts_code = p.ts_code AND b.trade_date = p.trade_date
            LEFT JOIN derived_limit_price lp ON lp.ts_code = p.ts_code AND lp.trade_date = p.trade_date
            WHERE p.trade_date BETWEEN ? AND ? AND p.source = 'tushare_raw'
        """
        count_started = time.perf_counter()
        count_row = tuple(con.execute(count_sql, query["params"]).fetchone())
        count_seconds = time.perf_counter() - count_started
        source_rows = _rows(con.execute("SELECT p.source, COUNT(*) FROM daily_price p WHERE p.trade_date BETWEEN ? AND ? GROUP BY p.source", query["params"]).fetchall())
    probe = provider.probe_daily_bars_fetchmany(bt.start_date, bt.end_date, batch_size=batch_size, progress_path=run_dir / "progress.json")
    output = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "warnings": list(WARNING_LINES),
        "validation_accessed": False,
        "blind_test_accessed": False,
        "features_computed": False,
        "backtest_executed": False,
        "query": query,
        "table_info": table_info,
        "index_list": index_list,
        "index_info": index_info,
        "explain_query_plan": explain,
        "count_diagnostic": {"elapsed_seconds": count_seconds, "row": count_row, "source_rows": source_rows},
        "fetchmany_probe": probe,
        "diagnosis": {
            "uses_index": any("USING INDEX" in str(row) for row in explain),
            "uses_temp_btree_sort": any("TEMP B-TREE" in str(row) for row in explain),
            "scan_daily_price": any("SCAN p" in str(row) or "SCAN daily_price" in str(row) for row in explain),
        },
    }
    (run_dir / "daily_bar_diagnosis.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    docs = repo_root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "stage3_6c2r_daily_bar_diagnosis.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (docs / "stage3_6c2r_daily_bar_diagnosis.md").write_text(_markdown(output), encoding="utf-8")
    return output


def _markdown(output: dict) -> str:
    lines = ["# Stage 3.6C-2R Daily Bar Diagnosis\n"]
    lines.extend(f"{line}\n" for line in WARNING_LINES)
    lines.append(f"\nRun dir: `{output['run_dir']}`\n")
    lines.append("\n## SQL\n```sql\n")
    lines.append(output["query"]["sql"])
    lines.append("\n```\n")
    lines.append(f"Params: `{output['query']['params']}`\n")
    lines.append(f"Count diagnostic: `{output['count_diagnostic']}`\n")
    lines.append(f"Fetchmany rows: `{output['fetchmany_probe']['rows']}`\n")
    lines.append(f"First batch seconds: `{output['fetchmany_probe']['first_batch_seconds']}`\n")
    lines.append(f"Total fetchmany seconds: `{output['fetchmany_probe']['elapsed_seconds']}`\n")
    lines.append(f"Explain: `{output['explain_query_plan']}`\n")
    return "".join(lines)
