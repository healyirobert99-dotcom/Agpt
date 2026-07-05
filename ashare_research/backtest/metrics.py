from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_metrics(accounts: pd.DataFrame, trades: pd.DataFrame, *, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> dict[str, float | int | None]:
    if accounts.empty or len(accounts) < 2:
        return {"status": "insufficient_data"}
    net = accounts["net_return"].astype(float).dropna()
    equity = accounts["total_equity"].astype(float)
    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0
    ann_return = (1.0 + total_return) ** (periods_per_year / max(len(net), 1)) - 1.0 if total_return > -1 else None
    vol = net.std(ddof=0) * math.sqrt(periods_per_year) if len(net) else None
    sharpe = None if not vol or vol == 0 or ann_return is None else (ann_return - risk_free_rate) / vol
    downside = net[net < 0]
    down_std = downside.std(ddof=0) * math.sqrt(periods_per_year) if len(downside) else None
    sortino = None if not down_std or down_std == 0 or ann_return is None else (ann_return - risk_free_rate) / down_std
    running = equity.cummax()
    dd = equity / running - 1.0
    max_dd = float(dd.min())
    calmar = None if max_dd == 0 or ann_return is None else ann_return / abs(max_dd)
    filled = trades[trades["status"] == "filled"] if not trades.empty else trades
    return {
        "total_return": float(total_return),
        "annualized_return": None if ann_return is None else float(ann_return),
        "annualized_volatility": None if vol is None else float(vol),
        "sharpe": None if sharpe is None else float(sharpe),
        "sortino": None if sortino is None else float(sortino),
        "max_drawdown": max_dd,
        "calmar": None if calmar is None else float(calmar),
        "turnover": float(accounts["turnover"].sum()),
        "trade_count": int(len(filled)),
        "win_rate": None,
        "gross_return": float(accounts["gross_return"].add(1).prod() - 1),
        "net_return": float(accounts["net_return"].add(1).prod() - 1),
        "cumulative_cost": float(accounts["cumulative_cost"].iloc[-1]),
        "unfilled_buy_count": int(((trades.get("side") == "buy") & (trades.get("status") == "unfilled")).sum()) if not trades.empty else 0,
        "unfilled_sell_count": int(((trades.get("side") == "sell") & (trades.get("status") == "unfilled")).sum()) if not trades.empty else 0,
        "cash_ratio": float(accounts["cash"].iloc[-1] / accounts["total_equity"].iloc[-1]) if accounts["total_equity"].iloc[-1] else None,
    }

