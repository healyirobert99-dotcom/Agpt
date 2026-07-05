"""
Relative alpha forward observation runner for low-vol candidate.

Focus: excess_return_vs_CSI800 (NOT absolute return).
OBSERVATION ONLY. No trading, no orders, no broker.
"""

from __future__ import annotations

import argparse
import json
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


def validate_relative_config(config: dict[str, Any]) -> list[str]:
    errors = []

    if config.get("trading_allowed") is not False:
        errors.append("trading_allowed must be false")
    if config.get("order_generation_allowed") is not False:
        errors.append("order_generation_allowed must be false")
    if config.get("broker_connection_allowed") is not False:
        errors.append("broker_connection_allowed must be false")

    candidate = config.get("candidate", {})
    if candidate.get("formula") != "NEG(RET_STD20)":
        errors.append(f"formula must be NEG(RET_STD20), got {candidate.get('formula')!r}")
    if candidate.get("rebalance_frequency") != 5:
        errors.append(f"rebalance_frequency must be 5, got {candidate.get('rebalance_frequency')}")
    if candidate.get("top_n") != 20:
        errors.append(f"top_n must be 20, got {candidate.get('top_n')}")
    if candidate.get("absolute_return_strategy") is not False:
        errors.append("absolute_return_strategy must be false")
    if candidate.get("relative_alpha_factor") is not True:
        errors.append("relative_alpha_factor must be true")
    if candidate.get("status") != "relative_factor_watch_only":
        errors.append(f"status must be relative_factor_watch_only, got {candidate.get('status')!r}")

    obs = config.get("observation", {})
    if obs.get("primary_metric") != "excess_return_vs_CSI800":
        errors.append("observation.primary_metric must be excess_return_vs_CSI800")

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
        raise ValueError("No trade dates in daily_price")
    return str(row[0])


def get_csi800_index(con: Any, obs_date: str) -> dict[str, Any]:
    """Get CSI800 index data for the observation date."""
    sql = """
        SELECT trade_date, close, pre_close, open, high, low, vol
        FROM index_daily_000906_sh
        WHERE trade_date = ?
    """
    row = con.execute(sql, [obs_date]).fetchone()
    if row is None:
        return {"found": False, "trade_date": obs_date}
    return {
        "found": True,
        "trade_date": str(row[0]),
        "close": float(row[1]),
        "pre_close": float(row[2]),
        "open": float(row[3]),
        "high": float(row[4]),
        "low": float(row[5]),
        "volume": float(row[6]) if row[6] else None,
        "daily_return": float(row[1]) / float(row[2]) - 1 if row[2] else None,
        "index_code": "000906.SH",
        "index_name": "CSI800",
    }


def get_csi800_range_return(con: Any, start_date: str, end_date: str) -> dict[str, Any]:
    """Get CSI800 return over a date range."""
    sql = """
        SELECT trade_date, close
        FROM index_daily_000906_sh
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
    """
    rows = con.execute(sql, [start_date, end_date]).fetchall()
    if len(rows) < 2:
        return {"period_return": None, "start_date": start_date, "end_date": end_date, "trading_days": len(rows)}

    start_close = float(rows[0][1])
    end_close = float(rows[-1][1])
    return {
        "period_return": (end_close / start_close - 1) if start_close else None,
        "start_date": str(rows[0][0]),
        "end_date": str(rows[-1][0]),
        "trading_days": len(rows),
    }


def get_bars_for_history(con: Any, end_date: str, lookback_calendar_days: int) -> pd.DataFrame:
    """Get daily bars with enough history for rolling features."""
    # Calculate start date: end_date minus lookback calendar days
    start_date = _offset_date(end_date, -lookback_calendar_days)

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


def _offset_date(date_str: str, days: int) -> str:
    """Simple date offset (works for YYYYMMDD format)."""
    from datetime import datetime as dt, timedelta
    d = dt.strptime(date_str, "%Y%m%d")
    return (d + timedelta(days=days)).strftime("%Y%m%d")


def get_csi800_members(con: Any, trade_date: str) -> set[str]:
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
    sql = "SELECT ts_code FROM historical_st_status WHERE start_date <= ? AND end_date >= ?"
    rows = con.execute(sql, [trade_date, trade_date]).fetchall()
    return {str(r[0]) for r in rows}


def get_tradability_info(con: Any, trade_date: str, ts_codes: list[str]) -> dict[str, dict]:
    if not ts_codes:
        return {}
    placeholders = ",".join("?" for _ in ts_codes)
    sql = f"""
        SELECT ts_code, tradability_proxy, proxy_reason
        FROM derived_tradability
        WHERE trade_date = ? AND ts_code IN ({placeholders})
    """
    params = [trade_date] + ts_codes
    rows = con.execute(sql, params).fetchall()
    return {str(r[0]): {"tradability_proxy": str(r[1]), "proxy_reason": str(r[2] or "")} for r in rows}


def compute_neg_ret_std20(bars: pd.DataFrame) -> pd.DataFrame:
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


def get_stock_names(con: Any, ts_codes: list[str]) -> dict[str, str]:
    """Get stock names from stock_lifecycle or stock_basic."""
    if not ts_codes:
        return {}
    placeholders = ",".join("?" for _ in ts_codes)
    sql = f"""
        SELECT ts_code, name FROM stock_lifecycle
        WHERE ts_code IN ({placeholders})
    """
    try:
        rows = con.execute(sql, ts_codes).fetchall()
        return {str(r[0]): str(r[1]) for r in rows}
    except Exception:
        return {}


def run_observation(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    errors = validate_relative_config(config)
    if errors:
        return {"status": "config_validation_failed", "errors": errors}

    candidate = config["candidate"]
    db_path = config.get("sqlite_path", "stock-data/ashare_research.sqlite3")

    con = _connect_db(db_path)
    try:
        obs_date = get_latest_trade_date(con)

        # Get bars for factor computation (need 60 days for warmup)
        bars = get_bars_for_history(con, obs_date, 60)
        bars = compute_neg_ret_std20(bars)

        # Filter to observation date
        obs_bars = bars[bars["trade_date"] == obs_date].copy()
        if obs_bars.empty:
            return {"status": "no_data", "observation_date": obs_date}

        # CSI800 universe
        csi800 = get_csi800_members(con, obs_date)
        st_stocks = get_st_status(con, obs_date)

        obs_bars = obs_bars[obs_bars["ts_code"].isin(csi800)].copy()
        if obs_bars.empty:
            return {"status": "no_csi800_members", "observation_date": obs_date}

        # Rank
        obs_bars["rank"] = obs_bars["NEG_RET_STD20"].rank(ascending=False, method="first")
        obs_bars = obs_bars.sort_values("rank")

        top_n = candidate.get("top_n", 20)
        top20 = obs_bars.head(top_n)

        # Tradability
        trad_map = get_tradability_info(con, obs_date, top20["ts_code"].tolist())
        names = get_stock_names(con, top20["ts_code"].tolist())

        watchlist = []
        for _, row in top20.iterrows():
            code = row["ts_code"]
            is_st = code in st_stocks
            limit_up = float(row.get("limit_up", 0) or 0)
            limit_down = float(row.get("limit_down", 0) or 0)
            close = float(row["close"])
            pre_close = float(row.get("pre_close", 0) or 0)
            at_limit_up = bool(limit_up > 0 and abs(close - limit_up) < 1e-6)
            at_limit_down = bool(limit_down > 0 and abs(close - limit_down) < 1e-6)
            trad_info = trad_map.get(code, {})
            tradable = trad_info.get("tradability_proxy", "").upper() not in ("UNTRADABLE", "BLOCKED", "SUSPENDED")

            watchlist.append({
                "rank": int(row["rank"]),
                "ts_code": code,
                "name": names.get(code, ""),
                "factor_value": round(float(row["NEG_RET_STD20"]), 6),
                "RET_STD20": round(float(row["RET_STD20"]), 6),
                "close": round(close, 2),
                "pre_close": round(pre_close, 2),
                "theory_weight": round(1.0 / top_n, 4),
                "is_st": is_st,
                "at_limit_up": at_limit_up,
                "at_limit_down": at_limit_down,
                "tradable": tradable,
            })

        # CSI800 index
        csi800_idx = get_csi800_index(con, obs_date)
        csi800_5d = get_csi800_range_return(con, _offset_date(obs_date, -7), obs_date)
        csi800_20d = get_csi800_range_return(con, _offset_date(obs_date, -30), obs_date)

        is_rebalance = _is_rebalance_day(obs_date, bars)

        observation = {
            "observation_date": obs_date,
            "database_latest_trade_date": obs_date,
            "candidate_id": candidate["candidate_id"],
            "formula": candidate["formula"],
            "rebalance_frequency": candidate["rebalance_frequency"],
            "top_n": top_n,
            "stock_pool": "CSI800_asof",
            "benchmark": "CSI800 (000906.SH)",
            "candidate_status": "relative_factor_watch_only",
            "absolute_return_strategy": False,
            "relative_alpha_factor": True,
            "is_rebalance_day": is_rebalance,
            "CSI800_index": csi800_idx,
            "CSI800_5d_return": csi800_5d.get("period_return"),
            "CSI800_20d_return": csi800_20d.get("period_return"),
            "csi800_member_count": len(csi800),
            "st_count": len(st_stocks),
            "portfolio_top20": watchlist,
            "portfolio_equal_weight": True,
            "orders_generated": False,
            "trading_allowed": False,
            "broker_connected": False,
            "portfolio_forward_return": None,
            "CSI800_forward_return": None,
            "excess_return_vs_CSI800": None,
            "rolling_5d_excess": None,
            "rolling_20d_excess": None,
            "relative_hit_rate": None,
            "observation_timestamp": datetime.now().isoformat(),
        }
        return observation
    finally:
        con.close()


def _is_rebalance_day(obs_date: str, bars: pd.DataFrame) -> bool:
    all_dates = sorted(bars["trade_date"].unique())
    if obs_date not in all_dates:
        return False
    idx = list(all_dates).index(obs_date)
    return (idx + 1) % 5 == 0


def write_observation(observation: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    obs_date = observation["observation_date"]
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / f"{obs_date}_observation.json"
    json_path.write_text(json.dumps(observation, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # Markdown
    md_path = output_dir / f"{obs_date}_observation.md"
    csi = observation.get("CSI800_index", {})
    lines = [
        f"# 相对 Alpha 前向观察: {obs_date}",
        "",
        "> ⚠️ RELATIVE ALPHA OBSERVATION ONLY. No trading, no orders, no broker.",
        "> 主指标: excess_return_vs_CSI800（非绝对收益）",
        "",
        f"- 候选: {observation['candidate_id']}",
        f"- 公式: {observation['formula']}",
        f"- 调仓: {observation['rebalance_frequency']}d",
        f"- 调仓日: {observation['is_rebalance_day']}",
        f"- 状态: {observation['candidate_status']}",
        f"- 绝对收益策略: {observation['absolute_return_strategy']}",
        "",
        "## CSI800 基准",
        f"- close: {csi.get('close', 'N/A')}",
        f"- 当日收益: {csi.get('daily_return')}",
        f"- 近5日收益: {observation.get('CSI800_5d_return')}",
        f"- 近20日收益: {observation.get('CSI800_20d_return')}",
        "",
        "## Top20 理论观察组合",
        "",
        "| rank | ts_code | name | factor_value | RET_STD20 | close | weight | tradable |",
        "|------|---------|------|-------------|-----------|-------|--------|----------|",
    ]
    for w in observation["portfolio_top20"]:
        tradable_str = "✅" if w["tradable"] else "❌"
        lines.append(
            f"| {w['rank']} | {w['ts_code']} | {w.get('name','')} | {w['factor_value']:.6f} | "
            f"{w['RET_STD20']:.6f} | {w['close']:.2f} | {w['theory_weight']:.4f} | {tradable_str} |"
        )

    lines += [
        "",
        "## 约束确认",
        f"- orders_generated: {observation['orders_generated']}",
        f"- trading_allowed: {observation['trading_allowed']}",
        f"- broker_connected: {observation['broker_connected']}",
        "",
        "## 前向指标（待未来数据）",
        f"- portfolio_forward_return: {observation['portfolio_forward_return']}",
        f"- CSI800_forward_return: {observation['CSI800_forward_return']}",
        f"- excess_return_vs_CSI800: {observation['excess_return_vs_CSI800']}",
        "",
        "---",
        f"*观察时间: {observation['observation_timestamp']}*",
        "*本报告仅供研究观察，不构成任何投资建议。*",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Relative alpha forward observation for low-vol candidate")
    parser.add_argument("--config", default="config/forward_observation_low_vol_relative_alpha.yaml")
    parser.add_argument("--output-dir", default="research_intel/forward_observation/relative_low_vol_5d")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path

    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    db_path = Path(config.get("sqlite_path", "stock-data/ashare_research.sqlite3"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

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
    print(f"  Top20: {len(observation['portfolio_top20'])} stocks")
    print(f"  CSI800 close: {observation.get('CSI800_index', {}).get('close', 'N/A')}")
    print(f"  trading_allowed: False")
    print(f"  orders_generated: False")


if __name__ == "__main__":
    main()
