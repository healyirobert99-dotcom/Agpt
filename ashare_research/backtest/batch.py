from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ashare_research.backtest.benchmark import benchmark_status
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import DeterministicBacktestEngine
from ashare_research.backtest.metrics import compute_metrics
from ashare_research.backtest.portfolio import Account
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import Expression
from ashare_research.registry.artifacts import stable_hash


@dataclass
class BatchBacktestResult:
    formula_hash: str
    formula_text: str
    metrics: dict
    failure_reason: str | None
    planned: pd.DataFrame
    trades: pd.DataFrame
    holdings: pd.DataFrame
    accounts: pd.DataFrame
    profile: dict[str, float]
    detail_dir: str | None = None


class BatchBacktestEvaluator:
    def __init__(self, context: ResearchContext, *, save_detail_policy: str = "summary_only", run_dir: str | Path | None = None, audit_hashes: set[str] | None = None):
        if save_detail_policy not in {"summary_only", "audit_selected", "full_detail"}:
            raise ValueError(f"unknown_save_detail_policy:{save_detail_policy}")
        self.context = context
        self.save_detail_policy = save_detail_policy
        self.run_dir = Path(run_dir) if run_dir else None
        self.audit_hashes = audit_hashes or set()
        self._cache: dict[str, BatchBacktestResult] = {}
        self._market_indices: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame] | None = None
        self.engine = DeterministicBacktestEngine(provider=None, config=context.config)  # type: ignore[arg-type]

    def evaluate_many(self, formulas: list[Expression]) -> list[BatchBacktestResult]:
        return [self.evaluate(expr) for expr in formulas]

    def evaluate(self, formula: Expression) -> BatchBacktestResult:
        cache_key = stable_hash({"formula": formula.sha256(), "context": self.context.context_hash, "config": self.context.config.__dict__})
        if cache_key in self._cache:
            return self._cache[cache_key]
        result = self._evaluate_uncached(formula)
        self._cache[cache_key] = result
        return result

    def _get_market_indices(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if self._market_indices is None:
            bars_idx = self.context.bars.set_index(["trade_date", "ts_code"])
            limits_idx = self.context.limits.set_index(["trade_date", "ts_code"])
            tradability_idx = self.context.tradability.set_index(["trade_date", "ts_code"]) if not self.context.tradability.empty else pd.DataFrame()
            lifecycle_idx = self.context.lifecycle.set_index("ts_code") if not self.context.lifecycle.empty else pd.DataFrame()
            self._market_indices = (bars_idx, limits_idx, tradability_idx, lifecycle_idx)
        return self._market_indices

    def _evaluate_uncached(self, formula: Expression) -> BatchBacktestResult:
        profile: dict[str, float] = {}

        def timed(name: str, fn):
            start = time.perf_counter()
            value = fn()
            profile[name] = profile.get(name, 0.0) + time.perf_counter() - start
            return value

        try:
            exec_result = timed("formula_execution_seconds", lambda: FormulaExecutor(min_valid_rows=10).execute(formula, self.context.features))
            if not exec_result.valid or exec_result.values is None:
                raise ValueError(f"invalid_formula:{exec_result.failure_reason}")
            factor = exec_result.values.rename("factor_value").reset_index()
            factor = factor.rename(columns={"level_0": "ts_code", "level_1": "trade_date"})
            if "ts_code" not in factor.columns:
                factor.columns = ["ts_code", "trade_date", "factor_value"]

            bars_idx, limits_idx, tradability_idx, lifecycle_idx = timed("market_index_seconds", self._get_market_indices)

            account = Account(self.context.config.initial_cash)
            planned_rows: list[dict] = []
            trade_rows: list[dict] = []
            holding_rows: list[dict] = []
            account_rows: list[dict] = []
            prev_equity = self.context.config.initial_cash
            prev_gross_equity = self.context.config.initial_cash
            pending_orders = {}

            for i, trade_date in enumerate(self.context.dates):
                account.refresh_available(trade_date)
                daily_cost = 0.0
                daily_notional = 0.0

                orders_to_execute = pending_orders.pop(trade_date, [])
                for order in [o for o in orders_to_execute if o.side == "sell"] + [o for o in orders_to_execute if o.side == "buy"]:
                    row = timed("execution_seconds", lambda o=order: self.engine._execute_one(o, bars_idx, limits_idx, tradability_idx, account))
                    daily_cost += row["transaction_cost"]
                    daily_notional += row["executed_notional"]
                    trade_rows.append(row)

                prices = {
                    code: float(bars_idx.loc[(trade_date, code)]["raw_close"])
                    for code in list(account.positions)
                    if (trade_date, code) in bars_idx.index
                }
                mv, holdings = timed("account_valuation_seconds", lambda: account.mark_to_market(prices))
                total_equity = account.cash + mv
                gross_equity = total_equity + account.cumulative_cost
                gross_return = gross_equity / prev_gross_equity - 1.0 if prev_gross_equity else 0.0
                net_return = total_equity / prev_equity - 1.0 if prev_equity else 0.0
                for h in holdings:
                    h["trade_date"] = trade_date
                    h["weight"] = h["market_value"] / total_equity if total_equity else None
                    is_st, st_source = self.engine._st_at(self.context.st_status, h["ts_code"], trade_date)
                    h["historical_is_st"] = is_st
                    h["st_source"] = st_source
                    holding_rows.append(h)
                account_rows.append(
                    {
                        "trade_date": trade_date,
                        "cash": account.cash,
                        "market_value": mv,
                        "total_equity": total_equity,
                        "gross_return": gross_return,
                        "net_return": net_return,
                        "daily_cost": daily_cost,
                        "cumulative_cost": account.cumulative_cost,
                        "turnover": daily_notional / total_equity if total_equity else 0.0,
                    }
                )
                prev_equity = total_equity
                prev_gross_equity = gross_equity

                if trade_date in self.context.rebalance_dates and i + 1 < len(self.context.dates):
                    planned_trade_date = self.context.dates[i + 1]
                    orders = timed("order_generation_seconds", lambda: self.engine._plan_orders(trade_date, planned_trade_date, factor, self.context.constituents, account, bars_idx, lifecycle_idx, self.context.st_status, formula))
                    planned_rows.extend([o.to_dict() for o in orders])
                    pending_orders.setdefault(planned_trade_date, []).extend(orders)

            planned = pd.DataFrame(planned_rows)
            trades = pd.DataFrame(trade_rows)
            holdings = pd.DataFrame(holding_rows)
            accounts = pd.DataFrame(account_rows)
            metrics = timed("metrics_seconds", lambda: compute_metrics(accounts, trades, risk_free_rate=self.context.config.risk_free_rate))
            detail_dir = self._maybe_write_detail(formula, planned, trades, holdings, accounts, metrics, exec_result.summary(), profile)
            return BatchBacktestResult(formula.sha256(), formula.to_string(), metrics, None, planned, trades, holdings, accounts, profile, detail_dir)
        except Exception as exc:  # noqa: BLE001
            empty = pd.DataFrame()
            return BatchBacktestResult(formula.sha256(), formula.normalized(), {"status": "failed", "failure_reason": str(exc)}, str(exc), empty, empty, empty, empty, profile)

    def _maybe_write_detail(self, formula: Expression, planned: pd.DataFrame, trades: pd.DataFrame, holdings: pd.DataFrame, accounts: pd.DataFrame, metrics: dict, formula_summary: dict, profile: dict[str, float]) -> str | None:
        should_write = self.save_detail_policy == "full_detail" or (self.save_detail_policy == "audit_selected" and formula.sha256() in self.audit_hashes)
        if not should_write:
            return None
        if self.run_dir is None:
            raise ValueError("run_dir_required_for_detail_output")
        detail_dir = self.run_dir / formula.sha256()
        bench = benchmark_status(self.context.config.benchmark_mode, self.context.config.benchmark_source)
        DeterministicBacktestEngine._write_outputs(detail_dir, formula.sha256(), planned, trades, holdings, accounts, metrics, bench, formula_summary)
        (detail_dir / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(detail_dir)

    def cleanup_details(self) -> None:
        if self.run_dir and self.run_dir.exists() and self.save_detail_policy == "summary_only":
            shutil.rmtree(self.run_dir, ignore_errors=True)
