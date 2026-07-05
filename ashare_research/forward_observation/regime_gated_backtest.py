"""
Regime-gated low-vol defensive backtest.

CSI800 > MA120 → risk-on: hold NEG(RET_STD20) top20
CSI800 <= MA120 → risk-off: cash

Locked historical blind test. No parameter optimization.
OBSERVATION ONLY. No trading, no orders, no broker.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _connect_db(path: str) -> Any:
    import sqlite3
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def get_csi800_daily(con: Any, start: str, end: str) -> pd.DataFrame:
    """Get CSI800 index daily data."""
    sql = """
        SELECT trade_date, close, pre_close
        FROM index_daily_000906_sh
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
    """
    df = pd.read_sql_query(sql, con, params=[start, end])
    df["trade_date"] = df["trade_date"].astype(str)
    df["ret"] = df["close"] / df["pre_close"] - 1
    return df


def get_daily_bars(con: Any, start: str, end: str) -> pd.DataFrame:
    """Get daily bars for factor computation."""
    sql = """
        SELECT p.trade_date, p.ts_code, p.close,
               lp.pre_close
        FROM daily_price p
        LEFT JOIN derived_limit_price lp
          ON lp.ts_code = p.ts_code AND lp.trade_date = p.trade_date
        WHERE p.trade_date BETWEEN ? AND ?
          AND p.source = 'tushare_raw'
        ORDER BY p.ts_code, p.trade_date
    """
    df = pd.read_sql_query(sql, con, params=[start, end])
    df["trade_date"] = df["trade_date"].astype(str)
    return df


def get_csi800_members_asof(con: Any, dates: list[str]) -> dict[str, set[str]]:
    """Get CSI800 members for each date."""
    result = {}
    for d in dates:
        sql = """
            SELECT con_code FROM csi800_weight_tushare
            WHERE trade_date = (SELECT MAX(trade_date) FROM csi800_weight_tushare WHERE trade_date <= ?)
        """
        rows = con.execute(sql, [d]).fetchall()
        result[d] = {str(r[0]) for r in rows}
    return result


def compute_factor(bars: pd.DataFrame) -> pd.DataFrame:
    """Compute NEG(RET_STD20)."""
    df = bars.copy()
    df = df.sort_values(["ts_code", "trade_date"], kind="mergesort")
    # Use close/pre_close from derived_limit_price for accurate returns
    df["ret1"] = df["close"] / df["pre_close"] - 1
    # Fill NaN returns (if pre_close missing) with 0
    df["ret1"] = df["ret1"].fillna(0)
    df["ret_std20"] = df.groupby("ts_code", sort=False)["ret1"].transform(
        lambda s: s.rolling(20, min_periods=20).std(ddof=0)
    )
    df["neg_ret_std20"] = -df["ret_std20"]
    return df


def run_regime_backtest(
    db_path: str,
    warmup_start: str,
    test_start: str,
    test_end: str,
    top_n: int = 20,
    rebalance_freq: int = 5,
    cost_bps: float = 20,
) -> dict[str, Any]:
    """Run regime-gated backtest."""
    con = _connect_db(db_path)

    # Get CSI800 data (includes warmup for MA120)
    csi800 = get_csi800_daily(con, warmup_start, test_end)
    csi800["ma120"] = csi800["close"].rolling(120, min_periods=1).mean()
    # Shift signal: t-day signal applied at t+1
    csi800["regime_signal"] = (csi800["close"] > csi800["ma120"]).astype(int)
    csi800["regime_signal"] = csi800["regime_signal"].shift(1).fillna(0).astype(bool)

    # Filter to test period
    csi800_test = csi800[(csi800["trade_date"] >= test_start) & (csi800["trade_date"] <= test_end)].copy()
    test_dates = csi800_test["trade_date"].tolist()

    # Get bars
    bars = get_daily_bars(con, warmup_start, test_end)
    bars = compute_factor(bars)

    # Get CSI800 members
    members = get_csi800_members_asof(con, test_dates)

    # Build daily portfolio returns
    daily_results = []
    current_holdings: list[str] = []
    current_weights: dict[str, float] = {}

    for di, date in enumerate(test_dates):
        regime_on = bool(csi800_test[csi800_test["trade_date"] == date]["regime_signal"].values[0])
        is_rebalance = (di % rebalance_freq) == 0

        date_bars = bars[bars["trade_date"] == date].copy()
        csi800_members = members.get(date, set())

        # Filter to CSI800 members
        date_bars = date_bars[date_bars["ts_code"].isin(csi800_members)].copy()

        if regime_on and is_rebalance and not date_bars.empty:
            # Select topN by NEG(RET_STD20)
            ranked = date_bars.dropna(subset=["neg_ret_std20"])
            ranked = ranked.sort_values("neg_ret_std20", ascending=False)
            top = ranked.head(top_n)
            current_holdings = top["ts_code"].tolist()
            current_weights = {code: 1.0 / top_n for code in current_holdings}

        if not regime_on:
            current_holdings = []
            current_weights = {}

        # Compute daily return
        port_ret = 0.0
        turnover = 0.0
        if current_holdings:
            ret_series = date_bars.set_index("ts_code")["close"] / date_bars.set_index("ts_code")["pre_close"] - 1
            for code, weight in current_weights.items():
                if code in ret_series.index and not np.isnan(ret_series[code]):
                    port_ret += weight * ret_series[code]
                else:
                    port_ret += 0.0  # missing bar = 0 return

        # Cost: only on rebalance days when regime is on
        if regime_on and is_rebalance and current_holdings:
            turnover = cost_bps / 10000 * 2  # buy + sell cost
            port_ret -= turnover

        csi800_ret = float(csi800_test[csi800_test["trade_date"] == date]["ret"].values[0])

        daily_results.append({
            "trade_date": date,
            "regime_on": regime_on,
            "is_rebalance": is_rebalance,
            "portfolio_return": port_ret,
            "csi800_return": csi800_ret,
            "holdings_count": len(current_holdings),
        })

    con.close()
    return _summarize_results(daily_results)


def _summarize_results(daily: list[dict]) -> dict[str, Any]:
    df = pd.DataFrame(daily)
    df["port_cum"] = (1 + df["portfolio_return"]).cumprod()
    df["csi800_cum"] = (1 + df["csi800_return"]).cumprod()

    n = len(df)
    port_ret = float(df["port_cum"].iloc[-1] - 1)
    csi800_ret = float(df["csi800_cum"].iloc[-1] - 1)
    excess = port_ret - csi800_ret

    # Sharpe (annualized)
    port_daily = df["portfolio_return"]
    port_sharpe = float(port_daily.mean() / port_daily.std() * np.sqrt(252)) if port_daily.std() > 0 else 0

    # Sortino
    downside = port_daily[port_daily < 0]
    sortino = float(port_daily.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0

    # Max drawdown
    cummax = df["port_cum"].cummax()
    drawdown = (df["port_cum"] - cummax) / cummax
    max_dd = float(drawdown.min())

    # Calmar
    annualized = (1 + port_ret) ** (252 / n) - 1 if n > 0 else 0
    calmar = annualized / abs(max_dd) if max_dd != 0 else 0

    # Time in market
    risk_on_days = int(df["regime_on"].sum())
    risk_off_days = n - risk_on_days
    switch_count = int((df["regime_on"].diff() != 0).sum())

    # Wins
    win_days = int((df["portfolio_return"] > 0).sum())
    win_rate = win_days / n if n > 0 else 0

    # Monthly
    df["month"] = df["trade_date"].str[:6]
    monthly = df.groupby("month").agg(
        port_return=("portfolio_return", lambda x: (1 + x).prod() - 1),
        csi800_return=("csi800_return", lambda x: (1 + x).prod() - 1),
    )
    best_month = monthly["port_return"].max()
    worst_month = monthly["port_return"].min()
    monthly_table = [
        {"month": idx, "port_return": float(row["port_return"]), "csi800_return": float(row["csi800_return"])}
        for idx, row in monthly.iterrows()
    ]

    return {
        "total_return": port_ret,
        "annualized_return": annualized,
        "sharpe": port_sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "win_rate": win_rate,
        "trade_count": n,
        "risk_on_days": risk_on_days,
        "risk_off_days": risk_off_days,
        "time_in_market_pct": risk_on_days / n if n > 0 else 0,
        "switch_count": switch_count,
        "benchmark_return": csi800_ret,
        "excess_return_vs_csi800": excess,
        "excess_return_vs_cash": port_ret,  # cash = 0
        "best_month": float(best_month),
        "worst_month": float(worst_month),
        "monthly_return_table": monthly_table,
    }


def main() -> None:
    db_path = "D:/alphaGPT/github_safe_sync/stock-data/ashare_research.sqlite3"
    import os
    if not os.path.exists(db_path):
        print("ERROR: database not found")
        return

    periods = {
        "2021": ("20200701", "20210101", "20211231"),
        "2022": ("20210701", "20220101", "20221231"),
        "2023": ("20220701", "20230101", "20231231"),
        "2021_2023": ("20200701", "20210101", "20231231"),
    }

    results: dict[str, Any] = {}

    for pname, (warmup, start, end) in periods.items():
        print(f"=== {pname}: {start} to {end} (warmup from {warmup}) ===")
        r = run_regime_backtest(db_path, warmup, start, end)
        results[pname] = r
        print(f"  regime-gated: ret={r['total_return']:+.4f} sharpe={r['sharpe']:+.3f} dd={r['max_drawdown']:+.4f}")
        print(f"  CSI800:       ret={r['benchmark_return']:+.4f}")
        print(f"  excess:       {r['excess_return_vs_csi800']:+.4f}")
        print(f"  time_in_mkt:  {r['time_in_market_pct']:.0%}")
        print(f"  switches:     {r['switch_count']}")

    # Also get always-on results from previous blind test
    # These we already have from the locked blind test
    always_on = {
        "2021": {"total_return": -0.0118, "sharpe": -0.151, "max_drawdown": -0.1243},
        "2022": {"total_return": -0.1779, "sharpe": -1.569, "max_drawdown": -0.1993},
        "2023": {"total_return": -0.1226, "sharpe": -1.356, "max_drawdown": -0.1945},
        "2021_2023": {"total_return": -0.2402, "sharpe": -0.884, "max_drawdown": -0.2983},
    }

    # Write full results
    output = {}
    for pname in periods:
        r = results[pname]
        ao = always_on.get(pname, {})
        csi800_ret = r["benchmark_return"]
        output[pname] = {
            "period": pname,
            "cash_return": 0.0,
            "cash_sharpe": 0.0,
            "cash_max_drawdown": 0.0,
            "csi800_return": csi800_ret,
            "low_vol_always_on_return": ao.get("total_return", 0),
            "low_vol_always_on_sharpe": ao.get("sharpe", 0),
            "low_vol_always_on_max_drawdown": ao.get("max_drawdown", 0),
            "regime_gated_return": r["total_return"],
            "regime_gated_sharpe": r["sharpe"],
            "regime_gated_max_drawdown": r["max_drawdown"],
            "regime_gated_sortino": r["sortino"],
            "regime_gated_calmar": r["calmar"],
            "excess_vs_csi800": r["excess_return_vs_csi800"],
            "excess_vs_cash": r["excess_return_vs_cash"],
            "time_in_market_pct": r["time_in_market_pct"],
            "switch_count": r["switch_count"],
            "risk_on_days": r["risk_on_days"],
            "risk_off_days": r["risk_off_days"],
            "best_month": r["best_month"],
            "worst_month": r["worst_month"],
        }

    # Write results
    import os as _os
    _os.makedirs("research_intel/library", exist_ok=True)
    with open("research_intel/library/low_vol_regime_gated_defensive_test_results.jsonl", "w") as f:
        for pname, v in output.items():
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    with open("low_vol_regime_gated_raw.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print("\nFULL COMPARISON:")
    for pname in periods:
        r = output[pname]
        print(f"\n{pname}:")
        print(f"  Cash:             ret=0.00% sharpe=0.000 dd=0.00%")
        print(f"  CSI800:           ret={r['csi800_return']*100:+.2f}%")
        print(f"  Low-vol always:   ret={r['low_vol_always_on_return']*100:+.2f}% sharpe={r['low_vol_always_on_sharpe']:+.3f} dd={r['low_vol_always_on_max_drawdown']*100:+.1f}%")
        print(f"  Regime-gated:     ret={r['regime_gated_return']*100:+.2f}% sharpe={r['regime_gated_sharpe']:+.3f} dd={r['regime_gated_max_drawdown']*100:+.1f}% time={r['time_in_market_pct']:.0%}")


if __name__ == "__main__":
    main()
