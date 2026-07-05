"""
Forward observation for the frozen primary low-vol candidate.

Fixed candidate: NEG(RET_STD20) + 5d rebalance
OBSERVATION ONLY. No trading, no order generation, no broker connection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_config(config_path: str | Path) -> dict[str, Any]:
    try:
        import yaml
        return yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        from ashare_research.config import load_simple_yaml
        return load_simple_yaml(config_path)


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate that the config is observation-only and matches the frozen candidate."""
    errors = []

    if config.get("trading_allowed") is not False:
        errors.append("trading_allowed must be false")
    if config.get("order_generation_allowed") is not False:
        errors.append("order_generation_allowed must be false")
    if config.get("broker_connection_allowed") is not False:
        errors.append("broker_connection_allowed must be false")

    candidate = config.get("candidate", {})
    if candidate.get("formula") != "NEG(RET_STD20)":
        errors.append(f"formula must be 'NEG(RET_STD20)', got {candidate.get('formula')!r}")
    if candidate.get("rebalance_frequency") != 5:
        errors.append(f"rebalance_frequency must be 5, got {candidate.get('rebalance_frequency')}")
    if candidate.get("candidate_id") != "primary_low_vol_5d":
        errors.append(f"candidate_id must be 'primary_low_vol_5d', got {candidate.get('candidate_id')!r}")

    return errors


def _connect_db(sqlite_path: str | Path) -> Any:
    path = Path(sqlite_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")
    import sqlite3
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def get_latest_trade_date(con: Any) -> str:
    row = con.execute("SELECT MAX(trade_date) FROM daily_price").fetchone()
    if row is None or row[0] is None:
        raise ValueError("No trade dates found in daily_price")
    return str(row[0])


def get_bars_for_date_range(con: Any, start_date: str, end_date: str) -> pd.DataFrame:
    """Get daily bars with enough history for 20-day rolling features."""
    sql = """
        SELECT p.trade_date, p.ts_code, p.close, p.volume, p.amount,
               lp.limit_up, lp.limit_down, lp.pre_close
        FROM daily_price p
        LEFT JOIN derived_limit_price lp
          ON lp.ts_code = p.ts_code AND lp.trade_date = p.trade_date
        WHERE p.trade_date BETWEEN ? AND ?
          AND p.source = 'tushare_raw'
        ORDER BY p.ts_code, p.trade_date
    """
    return pd.read_sql_query(sql, con, params=[start_date, end_date])


def get_csi800_members(con: Any, trade_date: str) -> set[str]:
    """Get CSI800 members as-of a given trade date."""
    sql = """
        SELECT w.con_code AS ts_code
        FROM csi800_weight_tushare w
        WHERE w.trade_date = (
            SELECT MAX(w2.trade_date) FROM csi800_weight_tushare w2
            WHERE w2.trade_date <= ?
        )
    """
    rows = con.execute(sql, [trade_date]).fetchall()
    return {str(r[0]) for r in rows}


def get_st_status(con: Any, trade_date: str) -> set[str]:
    """Get ST stocks as of a given trade date."""
    sql = """
        SELECT ts_code FROM historical_st_status
        WHERE start_date <= ? AND end_date >= ?
    """
    rows = con.execute(sql, [trade_date, trade_date]).fetchall()
    return {str(r[0]) for r in rows}


def compute_neg_ret_std20(bars: pd.DataFrame) -> pd.DataFrame:
    """Compute NEG(RET_STD20) on the given bars DataFrame."""
    df = bars.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.sort_values(["ts_code", "trade_date"], kind="mergesort")

    g = df.groupby("ts_code", sort=False, group_keys=False)
    df["RET1"] = g["close"].pct_change(1)
    df["RET_STD20"] = df["RET1"].groupby(df["ts_code"], sort=False).transform(
        lambda s: s.rolling(20, min_periods=20).std(ddof=0)
    )
    df["NEG_RET_STD20"] = -df["RET_STD20"]
    return df


def get_tradability_info(con: Any, trade_date: str, ts_codes: list[str]) -> pd.DataFrame:
    """Get tradability flags for a list of stocks on a given date."""
    if not ts_codes:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in ts_codes)
    sql = f"""
        SELECT ts_code, tradability_proxy, proxy_reason
        FROM derived_tradability
        WHERE trade_date = ? AND ts_code IN ({placeholders})
    """
    params = [trade_date] + ts_codes
    return pd.read_sql_query(sql, con, params=params)


def run_observation(config_path: str | Path) -> dict[str, Any]:
    """Run a single forward observation. Returns observation dict."""
    config = load_config(config_path)
    errors = validate_config(config)
    if errors:
        return {"status": "config_validation_failed", "errors": errors}

    candidate = config["candidate"]
    db_path = config.get("sqlite_path", "stock-data/ashare_research.sqlite3")

    con = _connect_db(db_path)
    try:
        obs_date = get_latest_trade_date(con)

        # Get 21 days of data (need 20 prior + 1 current for rolling std)
        # To find the start date, query for enough history
        start_date = _get_start_date_for_history(con, obs_date, 21)
        bars = get_bars_for_date_range(con, start_date, obs_date)
        bars = compute_neg_ret_std20(bars)

        # Filter to observation date only
        obs_bars = bars[bars["trade_date"] == obs_date].copy()
        if obs_bars.empty:
            return {"status": "no_data", "observation_date": obs_date}

        # Get universe
        csi800 = get_csi800_members(con, obs_date)
        st_stocks = get_st_status(con, obs_date)

        # Filter to CSI800 only
        obs_bars = obs_bars[obs_bars["ts_code"].isin(csi800)].copy()
        if obs_bars.empty:
            return {"status": "no_csi800_members", "observation_date": obs_date}

        # Rank by NEG_RET_STD20 (higher = lower vol = better)
        obs_bars["rank"] = obs_bars["NEG_RET_STD20"].rank(ascending=False, method="first")
        obs_bars = obs_bars.sort_values("rank")

        top_n = candidate.get("top_n", 20)
        top20 = obs_bars.head(top_n).copy()

        # Get tradability
        tradability = get_tradability_info(con, obs_date, top20["ts_code"].tolist())
        tradability_map = {}
        if not tradability.empty:
            for _, row in tradability.iterrows():
                tradability_map[row["ts_code"]] = {
                    "tradability_proxy": str(row.get("tradability_proxy", "")),
                    "proxy_reason": str(row.get("proxy_reason", "")),
                }

        # Build observation
        watchlist = []
        for _, row in top20.iterrows():
            code = row["ts_code"]
            is_st = code in st_stocks
            limit_up = float(row.get("limit_up", 0) or 0)
            limit_down = float(row.get("limit_down", 0) or 0)
            pre_close = float(row.get("pre_close", 0) or 0)
            close = float(row["close"])
            at_limit_up = bool(limit_up > 0 and abs(close - limit_up) < 1e-6)
            at_limit_down = bool(limit_down > 0 and abs(close - limit_down) < 1e-6)
            tradable = tradability_map.get(code, {}).get("tradability_proxy", "").upper() not in ("UNTRADABLE", "BLOCKED", "SUSPENDED")

            watchlist.append({
                "ts_code": code,
                "factor_value": round(float(row["NEG_RET_STD20"]), 6),
                "rank": int(row["rank"]),
                "close": round(close, 2),
                "pre_close": round(pre_close, 2),
                "is_st": is_st,
                "at_limit_up": at_limit_up,
                "at_limit_down": at_limit_down,
                "tradable": tradable,
                "theory_weight": round(1.0 / top_n, 4),
            })

        observation = {
            "observation_date": obs_date,
            "database_latest_trade_date": obs_date,
            "candidate_id": candidate["candidate_id"],
            "formula": candidate["formula"],
            "rebalance_frequency": candidate["rebalance_frequency"],
            "is_rebalance_day": _is_rebalance_day(obs_date, bars, candidate["rebalance_frequency"]),
            "top_n": top_n,
            "csi800_member_count": len(csi800),
            "st_count": len(st_stocks),
            "watchlist": watchlist,
            "trading_allowed": False,
            "orders_generated": False,
            "broker_connected": False,
            "next_5d_return_observed": None,
            "portfolio_forward_return": None,
            "benchmark_forward_return": None,
            "excess_return": None,
            "observation_timestamp": datetime.now().isoformat(),
        }
        return observation
    finally:
        con.close()


def _get_start_date_for_history(con: Any, end_date: str, lookback_days: int) -> str:
    """Find a start_date that should give us at least lookback_days of data."""
    # Get all dates, take the one lookback_days before end_date
    sql = """
        SELECT DISTINCT trade_date FROM daily_price
        WHERE trade_date <= ?
        ORDER BY trade_date DESC
    """
    rows = con.execute(sql, [end_date]).fetchall()
    if len(rows) < lookback_days:
        return str(rows[-1][0]) if rows else end_date
    return str(rows[lookback_days - 1][0])


def _is_rebalance_day(obs_date: str, bars: pd.DataFrame, frequency: int) -> bool:
    """Check if obs_date is a rebalance day based on trading day count."""
    all_dates = sorted(bars["trade_date"].unique())
    if obs_date not in all_dates:
        return False
    idx = list(all_dates).index(obs_date)
    return (idx + 1) % frequency == 0


def write_observation(observation: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    """Write observation to JSON and Markdown files."""
    output_dir = Path(output_dir)
    obs_date = observation["observation_date"]
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / f"{obs_date}_observation.json"
    json_path.write_text(json.dumps(observation, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # Markdown
    md_path = output_dir / f"{obs_date}_observation.md"
    lines = [
        f"# 前向观察: {obs_date}",
        "",
        "> ⚠️ OBSERVATION ONLY. No trading, no orders, no broker.",
        "",
        f"- 候选: {observation['candidate_id']}",
        f"- 公式: {observation['formula']}",
        f"- 调仓频率: {observation['rebalance_frequency']}d",
        f"- 调仓日: {observation['is_rebalance_day']}",
        f"- CSI800 成分股: {observation['csi800_member_count']}",
        f"- ST 股数: {observation['st_count']}",
        f"- trading_allowed: {observation['trading_allowed']}",
        f"- orders_generated: {observation['orders_generated']}",
        f"- broker_connected: {observation['broker_connected']}",
        "",
        "## Top20 理论观察名单",
        "",
        "| rank | ts_code | factor_value | close | pre_close | tradable | theory_weight |",
        "|------|---------|-------------|-------|-----------|----------|---------------|",
    ]
    for w in observation["watchlist"]:
        flags = []
        if w["is_st"]:
            flags.append("ST")
        if w["at_limit_up"]:
            flags.append("涨停")
        if w["at_limit_down"]:
            flags.append("跌停")
        flag_str = ",".join(flags) if flags else "—"
        tradable_str = "✅" if w["tradable"] else "❌" + (f"({flag_str})" if flags else "")
        lines.append(
            f"| {w['rank']} | {w['ts_code']} | {w['factor_value']:.6f} | {w['close']:.2f} | "
            f"{w['pre_close']:.2f} | {tradable_str} | {w['theory_weight']:.4f} |"
        )

    lines += [
        "",
        "---",
        f"*观察时间: {observation['observation_timestamp']}*",
        "*本报告仅供观察，不构成任何投资建议。*",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward observation for low-vol 5d candidate")
    parser.add_argument("--config", default="config/forward_observation_low_vol_5d.yaml", help="Observation config")
    parser.add_argument("--output-dir", default="research_intel/forward_observation/low_vol_5d", help="Output directory")
    args = parser.parse_args()

    # Resolve config path relative to repo root
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path

    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Check database
    config = load_config(config_path)
    db_path = Path(config.get("sqlite_path", "stock-data/ashare_research.sqlite3"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    # Run observation
    observation = run_observation(config_path)
    if observation.get("status") in ("config_validation_failed", "no_data", "no_csi800_members"):
        print(f"ERROR: {observation.get('status')}", file=sys.stderr)
        if "errors" in observation:
            for e in observation["errors"]:
                print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir

    json_path, md_path = write_observation(observation, output_dir)
    print(f"Observation complete: {observation['observation_date']}")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(f"  Top20: {len(observation['watchlist'])} stocks observed")
    print(f"  trading_allowed: False")


if __name__ == "__main__":
    main()
