from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.data.store import ensure_free_space
from ashare_research.factors.base_features import compute_base_features
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import Expression

from .benchmark import benchmark_status
from .execution import execute_order
from .metrics import compute_metrics
from .portfolio import Account
from .records import ExternalTarget, PlannedOrder
from ashare_research.reporting.backtest_report import write_backtest_report


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str
    end_date: str
    rebalance_frequency: int
    top_n: int
    initial_cash: float
    cost_bps: float
    unknown_tradability_policy: str
    runs_dir: str = "runs"
    min_free_space_gb: float = 10.0
    max_run_output_gb: float = 5.0
    temp_dir: str = "runs/tmp"
    risk_free_rate: float = 0.0
    benchmark_mode: str | None = None
    benchmark_source: str | None = None

    @classmethod
    def from_dict(cls, cfg: dict) -> "BacktestConfig":
        b = cfg.get("backtest", {})
        missing = [k for k in ("start_date", "end_date", "rebalance_frequency", "top_n", "initial_cash", "unknown_tradability_policy") if b.get(k) is None]
        if missing:
            raise ValueError(f"Missing formal backtest parameters: {missing}")
        storage = cfg.get("storage", {})
        cost = cfg.get("cost", {})
        benchmark = cfg.get("benchmark", {})
        return cls(
            start_date=str(b["start_date"]),
            end_date=str(b["end_date"]),
            rebalance_frequency=int(b["rebalance_frequency"]),
            top_n=int(b["top_n"]),
            initial_cash=float(b["initial_cash"]),
            cost_bps=float(cost.get("primary_one_way_bps", b.get("cost_bps", 20))),
            unknown_tradability_policy=str(b["unknown_tradability_policy"]),
            runs_dir=str(cfg.get("output", {}).get("runs_dir", "runs")),
            min_free_space_gb=float(storage.get("min_free_space_gb", 10)),
            max_run_output_gb=float(storage.get("max_run_output_gb", 5)),
            temp_dir=str(storage.get("temp_dir", "runs/tmp")),
            risk_free_rate=float(b.get("risk_free_rate", 0.0)),
            benchmark_mode=benchmark.get("mode"),
            benchmark_source=benchmark.get("source"),
        )


class DeterministicBacktestEngine:
    def __init__(self, provider: LocalSQLiteProvider, config: BacktestConfig):
        self.provider = provider
        self.config = config

    def run(self, formula: Expression) -> dict[str, object]:
        ensure_free_space(Path("."), int(self.config.min_free_space_gb * 1024**3))
        run_id = "bt_" + uuid.uuid4().hex[:12]
        run_dir = Path(self.config.runs_dir) / run_id
        tmp_parent = Path(self.config.temp_dir)
        tmp_parent.mkdir(parents=True, exist_ok=True)
        tmp_path = Path(tempfile.mkdtemp(prefix=f"{run_id}_", dir=tmp_parent))
        try:
            result = self._run_to_dir(formula, run_id, tmp_path)
            estimated = sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())
            if estimated > self.config.max_run_output_gb * 1024**3:
                raise RuntimeError("estimated_run_output_exceeds_limit")
            run_dir.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.rename(run_dir)
            result["run_dir"] = str(run_dir)
            return result
        finally:
            if tmp_path.exists():
                shutil.rmtree(tmp_path)

    def run_external_target_schedule(
        self,
        targets: list[ExternalTarget],
        *,
        market_data: dict[str, pd.DataFrame] | None = None,
        run_id: str = "external_target_schedule",
        run_dir: Path | None = None,
        write_outputs: bool = False,
    ) -> dict[str, object]:
        """Run a Phase 2 backtest from an external target schedule.

        The caller supplies target windows only. This engine owns order
        generation, execution, account state, valuation and metrics.
        """
        data = market_data if market_data is not None else self._load_market_data()
        result = self._run_external_targets(targets, data)
        if write_outputs:
            if run_dir is None:
                raise ValueError("run_dir_required")
            bench = benchmark_status(self.config.benchmark_mode, self.config.benchmark_source)
            self._write_outputs(
                run_dir,
                run_id,
                result["planned"],
                result["trades"],
                result["holdings"],
                result["accounts"],
                result["metrics"],
                bench,
                {"source": "external_target_schedule", "target_count": len(targets)},
            )
        return {"run_id": run_id, **result}

    def _load_market_data(self) -> dict[str, pd.DataFrame]:
        if self.provider is None:
            raise ValueError("provider_required")
        bars = self.provider.get_daily_bars(self.config.start_date, self.config.end_date)
        if bars.empty:
            raise ValueError("no_daily_bars")
        return {
            "bars": bars,
            "calendar": self.provider.get_trade_calendar(self.config.start_date, self.config.end_date),
            "constituents": self.provider.get_index_constituents("CSI800", self.config.start_date, self.config.end_date),
            "limits": self.provider.get_limit_prices(self.config.start_date, self.config.end_date),
            "tradability": self.provider.get_tradability_flags(self.config.start_date, self.config.end_date),
            "lifecycle": self.provider.get_lifecycle(),
            "st_status": self.provider.get_historical_st_status(self.config.start_date, self.config.end_date),
        }

    def _run_to_dir(self, formula: Expression, run_id: str, run_dir: Path) -> dict[str, object]:
        data = self._load_market_data()
        bars = data["bars"]
        if bars.empty:
            raise ValueError("no_daily_bars")
        calendar = data["calendar"]
        dates = list(calendar["trade_date"])
        constituents = data["constituents"]
        limits = data["limits"]
        tradability = data["tradability"]
        lifecycle = data["lifecycle"]
        st_status = data["st_status"]

        features = compute_base_features(bars)
        exec_result = FormulaExecutor(min_valid_rows=10).execute(formula, features)
        if not exec_result.valid or exec_result.values is None:
            raise ValueError(f"invalid_formula:{exec_result.failure_reason}")
        factor = exec_result.values.rename("factor_value").reset_index()
        factor = factor.rename(columns={"level_0": "ts_code", "level_1": "trade_date"})
        if "ts_code" not in factor.columns:
            factor.columns = ["ts_code", "trade_date", "factor_value"]

        bars_idx = bars.set_index(["trade_date", "ts_code"])
        limits_idx = limits.set_index(["trade_date", "ts_code"])
        tradability_idx = tradability.set_index(["trade_date", "ts_code"]) if not tradability.empty else pd.DataFrame()
        lifecycle_idx = lifecycle.set_index("ts_code") if not lifecycle.empty else pd.DataFrame()

        account = Account(self.config.initial_cash)
        planned_rows: list[dict] = []
        trade_rows: list[dict] = []
        holding_rows: list[dict] = []
        account_rows: list[dict] = []
        prev_equity = self.config.initial_cash
        prev_gross_equity = self.config.initial_cash
        pending_orders: dict[str, list[PlannedOrder]] = {}

        rebalance_dates = set(dates[:: self.config.rebalance_frequency])
        for i, trade_date in enumerate(dates):
            account.refresh_available(trade_date)
            daily_cost = 0.0
            daily_notional = 0.0

            orders_to_execute = pending_orders.pop(trade_date, [])
            for order in [o for o in orders_to_execute if o.side == "sell"] + [o for o in orders_to_execute if o.side == "buy"]:
                row = self._execute_one(order, bars_idx, limits_idx, tradability_idx, account)
                daily_cost += row["transaction_cost"]
                daily_notional += row["executed_notional"]
                trade_rows.append(row)

            prices = {
                code: float(bars_idx.loc[(trade_date, code)]["raw_close"])
                for code in list(account.positions)
                if (trade_date, code) in bars_idx.index
            }
            mv, holdings = account.mark_to_market(prices)
            total_equity = account.cash + mv
            gross_equity = total_equity + account.cumulative_cost
            gross_return = gross_equity / prev_gross_equity - 1.0 if prev_gross_equity else 0.0
            net_return = total_equity / prev_equity - 1.0 if prev_equity else 0.0
            for h in holdings:
                h["trade_date"] = trade_date
                h["weight"] = h["market_value"] / total_equity if total_equity else None
                is_st, st_source = self._st_at(st_status, h["ts_code"], trade_date)
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

            if trade_date in rebalance_dates and i + 1 < len(dates):
                planned_trade_date = dates[i + 1]
                orders = self._plan_orders(trade_date, planned_trade_date, factor, constituents, account, bars_idx, lifecycle_idx, st_status, formula)
                planned_rows.extend([o.to_dict() for o in orders])
                pending_orders.setdefault(planned_trade_date, []).extend(orders)

        planned = pd.DataFrame(planned_rows)
        trades = pd.DataFrame(trade_rows)
        holdings = pd.DataFrame(holding_rows)
        accounts = pd.DataFrame(account_rows)
        metrics = compute_metrics(accounts, trades, risk_free_rate=self.config.risk_free_rate)
        bench = benchmark_status(self.config.benchmark_mode, self.config.benchmark_source)
        self._write_outputs(run_dir, run_id, planned, trades, holdings, accounts, metrics, bench, exec_result.summary())
        return {"run_id": run_id, "metrics": metrics, "formula": exec_result.summary(), "benchmark": bench}

    def _run_external_targets(self, targets: list[ExternalTarget], data: dict[str, pd.DataFrame]) -> dict[str, object]:
        bars = data["bars"]
        calendar = data["calendar"]
        limits = data["limits"]
        tradability = data["tradability"]
        lifecycle = data["lifecycle"]
        st_status = data["st_status"]
        dates = list(calendar["trade_date"].astype(str))

        bars_idx = bars.set_index(["trade_date", "ts_code"])
        limits_idx = limits.set_index(["trade_date", "ts_code"])
        tradability_idx = tradability.set_index(["trade_date", "ts_code"]) if not tradability.empty else pd.DataFrame()
        lifecycle_idx = lifecycle.set_index("ts_code") if not lifecycle.empty else pd.DataFrame()

        targets_by_signal: dict[str, list[ExternalTarget]] = {}
        for target in sorted(targets, key=lambda t: (t.signal_date, t.rank, t.ts_code, t.window_id)):
            targets_by_signal.setdefault(target.signal_date, []).append(target)

        account = Account(self.config.initial_cash)
        planned_rows: list[dict] = []
        trade_rows: list[dict] = []
        holding_rows: list[dict] = []
        account_rows: list[dict] = []
        pending_orders: dict[str, list[PlannedOrder]] = {}
        open_windows: dict[str, dict[str, object]] = {}
        retry_exit_orders: dict[str, list[PlannedOrder]] = {}
        prev_equity = self.config.initial_cash
        prev_gross_equity = self.config.initial_cash

        for i, trade_date in enumerate(dates):
            account.refresh_available(trade_date)
            self._schedule_due_external_exits(trade_date, open_windows, retry_exit_orders, pending_orders, account)
            daily_cost = 0.0
            daily_notional = 0.0

            orders_to_execute = pending_orders.pop(trade_date, [])
            ordered = [o for o in orders_to_execute if o.side == "sell"] + [o for o in orders_to_execute if o.side == "buy"]
            for order in ordered:
                row = self._execute_one(order, bars_idx, limits_idx, tradability_idx, account)
                daily_cost += row["transaction_cost"]
                daily_notional += row["executed_notional"]
                trade_rows.append(row)
                if order.order_purpose == "entry" and row["status"] == "filled":
                    open_windows[str(order.window_id)] = {
                        "target": order,
                        "quantity": int(row["executed_quantity"]),
                        "ts_code": order.ts_code,
                    }
                elif order.order_purpose == "exit":
                    if row["status"] == "filled":
                        open_windows.pop(str(order.window_id), None)
                    else:
                        next_date = dates[i + 1] if i + 1 < len(dates) else None
                        if next_date:
                            retry = PlannedOrder(
                                order.signal_date,
                                next_date,
                                order.ts_code,
                                "sell",
                                order.target_weight,
                                0,
                                int(order.current_quantity),
                                -abs(int(order.planned_quantity)),
                                order.formula_hash,
                                order.factor_value,
                                order.rank,
                                order.snapshot_date,
                                order.effective_trade_date,
                                order.membership_source,
                                order.historical_is_st,
                                order.st_source,
                                order.window_id,
                                order.planned_exit_date,
                                "exit",
                            )
                            retry_exit_orders.setdefault(next_date, []).append(retry)

            prices = {
                code: float(bars_idx.loc[(trade_date, code)]["raw_close"])
                for code in list(account.positions)
                if (trade_date, code) in bars_idx.index
            }
            mv, holdings = account.mark_to_market(prices)
            total_equity = account.cash + mv
            gross_equity = total_equity + account.cumulative_cost
            gross_return = gross_equity / prev_gross_equity - 1.0 if prev_gross_equity else 0.0
            net_return = total_equity / prev_equity - 1.0 if prev_equity else 0.0
            for h in holdings:
                h["trade_date"] = trade_date
                h["weight"] = h["market_value"] / total_equity if total_equity else None
                is_st, st_source = self._st_at(st_status, h["ts_code"], trade_date)
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

            for target in targets_by_signal.get(trade_date, []):
                order = self._plan_external_entry(target, account, bars_idx, lifecycle_idx, st_status, trade_date)
                if order is None:
                    continue
                planned_rows.append(order.to_dict())
                pending_orders.setdefault(target.entry_date, []).append(order)

        planned = pd.DataFrame(planned_rows)
        trades = pd.DataFrame(trade_rows)
        holdings = pd.DataFrame(holding_rows)
        accounts = pd.DataFrame(account_rows)
        metrics = compute_metrics(accounts, trades, risk_free_rate=self.config.risk_free_rate)
        return {"metrics": metrics, "planned": planned, "trades": trades, "holdings": holdings, "accounts": accounts}

    def _plan_external_entry(
        self,
        target: ExternalTarget,
        account: Account,
        bars_idx: pd.DataFrame,
        lifecycle_idx: pd.DataFrame,
        st_status: pd.DataFrame,
        trade_date: str,
    ) -> PlannedOrder | None:
        code = target.ts_code
        if (target.signal_date, code) not in bars_idx.index:
            return None
        if not self._lifecycle_active(lifecycle_idx, code, target.signal_date):
            return None
        equity = account.cash
        for pos_code, pos in account.positions.items():
            if (target.signal_date, pos_code) in bars_idx.index:
                equity += pos.quantity * float(bars_idx.loc[(target.signal_date, pos_code)]["raw_close"])
        price = float(bars_idx.loc[(target.signal_date, code)]["raw_close"])
        if price <= 0:
            return None
        target_qty = int((equity * target.target_weight) // (price * 100)) * 100
        if target_qty < 100:
            return None
        is_st, st_source = self._st_at(st_status, code, target.signal_date)
        return PlannedOrder(
            target.signal_date,
            target.entry_date,
            code,
            "buy",
            target.target_weight,
            target_qty,
            0,
            target_qty,
            "external_target_schedule",
            float(target.factor_value),
            int(target.rank),
            None,
            target.signal_date,
            "external_target_schedule",
            is_st,
            st_source,
            target.window_id,
            target.planned_exit_date,
            "entry",
        )

    def _schedule_due_external_exits(
        self,
        trade_date: str,
        open_windows: dict[str, dict[str, object]],
        retry_exit_orders: dict[str, list[PlannedOrder]],
        pending_orders: dict[str, list[PlannedOrder]],
        account: Account,
    ) -> None:
        due = retry_exit_orders.pop(trade_date, [])
        for window_id, payload in sorted(open_windows.items()):
            target_order = payload["target"]
            if not isinstance(target_order, PlannedOrder):
                continue
            if target_order.planned_exit_date != trade_date:
                continue
            pos = account.positions.get(target_order.ts_code)
            quantity = min(int(payload["quantity"]), pos.quantity if pos else 0)
            if quantity <= 0:
                continue
            due.append(
                PlannedOrder(
                    target_order.signal_date,
                    trade_date,
                    target_order.ts_code,
                    "sell",
                    target_order.target_weight,
                    0,
                    quantity,
                    -quantity,
                    target_order.formula_hash,
                    target_order.factor_value,
                    target_order.rank,
                    target_order.snapshot_date,
                    target_order.effective_trade_date,
                    target_order.membership_source,
                    target_order.historical_is_st,
                    target_order.st_source,
                    target_order.window_id,
                    target_order.planned_exit_date,
                    "exit",
                )
            )
        if due:
            pending_orders.setdefault(trade_date, []).extend(due)

    def _plan_orders(
        self,
        signal_date: str,
        planned_trade_date: str,
        factor: pd.DataFrame,
        constituents: pd.DataFrame,
        account: Account,
        bars_idx: pd.DataFrame,
        lifecycle_idx: pd.DataFrame,
        st_status: pd.DataFrame,
        formula: Expression,
    ) -> list[PlannedOrder]:
        members = constituents[constituents["effective_trade_date"] == signal_date]
        if members.empty:
            return []
        members = members[[self._lifecycle_active(lifecycle_idx, code, signal_date) for code in members["ts_code"]]]
        scores = factor[(factor["trade_date"] == signal_date) & (factor["ts_code"].isin(set(members["ts_code"])))]
        scores = scores.dropna(subset=["factor_value"]).sort_values(["factor_value", "ts_code"], ascending=[False, True], kind="mergesort")
        selected = list(scores.head(self.config.top_n)["ts_code"])
        score_map = dict(zip(scores["ts_code"], scores["factor_value"]))
        member_map = {row.ts_code: row for row in members.itertuples(index=False)}
        equity = account.cash
        for code, pos in account.positions.items():
            if (signal_date, code) in bars_idx.index:
                equity += pos.quantity * float(bars_idx.loc[(signal_date, code)]["raw_close"])
        target_weight = 1.0 / self.config.top_n if self.config.top_n else 0.0
        orders: list[PlannedOrder] = []
        for rank, code in enumerate(selected, 1):
            if (signal_date, code) not in bars_idx.index:
                continue
            price = float(bars_idx.loc[(signal_date, code)]["raw_close"])
            if price <= 0:
                continue
            target_qty = int((equity * target_weight) // (price * 100)) * 100
            current = account.positions.get(code).quantity if code in account.positions else 0
            delta = target_qty - current
            member = member_map[code]
            is_st, st_source = self._st_at(st_status, code, signal_date)
            if delta > 0:
                orders.append(
                    PlannedOrder(
                        signal_date,
                        planned_trade_date,
                        code,
                        "buy",
                        target_weight,
                        target_qty,
                        current,
                        delta,
                        formula.sha256(),
                        float(score_map[code]),
                        rank,
                        member.snapshot_date,
                        member.effective_trade_date,
                        member.membership_source,
                        is_st,
                        st_source,
                    )
                )
            elif delta < 0:
                orders.append(
                    PlannedOrder(
                        signal_date,
                        planned_trade_date,
                        code,
                        "sell",
                        target_weight,
                        target_qty,
                        current,
                        delta,
                        formula.sha256(),
                        float(score_map[code]),
                        rank,
                        member.snapshot_date,
                        member.effective_trade_date,
                        member.membership_source,
                        is_st,
                        st_source,
                    )
                )
        for code in sorted(set(account.positions) - set(selected)):
            current = account.positions[code].quantity
            if current > 0:
                is_st, st_source = self._st_at(st_status, code, signal_date)
                orders.append(PlannedOrder(signal_date, planned_trade_date, code, "sell", 0.0, 0, current, -current, formula.sha256(), float(score_map.get(code, float("nan"))), 0, None, signal_date, None, is_st, st_source))
        return orders

    def _execute_one(self, order: PlannedOrder, bars_idx: pd.DataFrame, limits_idx: pd.DataFrame, tradability_idx: pd.DataFrame, account: Account) -> dict:
        price = None
        if (order.planned_trade_date, order.ts_code) in bars_idx.index:
            price = float(bars_idx.loc[(order.planned_trade_date, order.ts_code)]["raw_open"])
        limit_up = limit_down = None
        status = rule_version = None
        if (order.planned_trade_date, order.ts_code) in limits_idx.index:
            lim = limits_idx.loc[(order.planned_trade_date, order.ts_code)]
            limit_up = None if pd.isna(lim["limit_up"]) else float(lim["limit_up"])
            limit_down = None if pd.isna(lim["limit_down"]) else float(lim["limit_down"])
            status = str(lim["limit_derivation_status"])
            rule_version = str(lim["limit_rule_version"])
        proxy = None
        if not tradability_idx.empty and (order.planned_trade_date, order.ts_code) in tradability_idx.index:
            proxy = "unavailable"
        rec = execute_order(account, order, raw_open=price, limit_up=limit_up, limit_down=limit_down, limit_status=status, limit_rule_version=rule_version, tradability_proxy=proxy, cost_bps=self.config.cost_bps, unknown_policy=self.config.unknown_tradability_policy)
        row = rec.to_dict()
        row["window_id"] = order.window_id
        row["planned_exit_date"] = order.planned_exit_date
        row["order_purpose"] = order.order_purpose
        return row

    @staticmethod
    def _write_outputs(run_dir: Path, run_id: str, planned: pd.DataFrame, trades: pd.DataFrame, holdings: pd.DataFrame, accounts: pd.DataFrame, metrics: dict, benchmark: dict, formula: dict) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        planned.to_csv(run_dir / "planned_orders.csv", index=False)
        trades.to_csv(run_dir / "executions.csv", index=False)
        holdings.to_csv(run_dir / "daily_holdings.csv", index=False)
        accounts.to_csv(run_dir / "daily_account.csv", index=False)
        (run_dir / "metrics.json").write_text(json.dumps({"metrics": metrics, "benchmark": benchmark, "formula": formula}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_backtest_report(run_dir / "report.md", run_id=run_id, metrics=metrics, benchmark=benchmark)

    @staticmethod
    def _lifecycle_active(lifecycle_idx: pd.DataFrame, ts_code: str, trade_date: str) -> bool:
        if lifecycle_idx.empty or ts_code not in lifecycle_idx.index:
            return False
        row = lifecycle_idx.loc[ts_code]
        list_date = row.get("list_date")
        delist_date = row.get("delist_date")
        if pd.isna(list_date) or str(list_date) > trade_date:
            return False
        if not pd.isna(delist_date) and str(delist_date) and str(delist_date) < trade_date:
            return False
        return True

    @staticmethod
    def _st_at(st_status: pd.DataFrame, ts_code: str, trade_date: str) -> tuple[bool | None, str | None]:
        if st_status.empty:
            return None, None
        rows = st_status[(st_status["ts_code"] == ts_code) & (st_status["start_date"] <= trade_date) & (st_status["end_date"] >= trade_date)]
        if rows.empty:
            return False, None
        row = rows.iloc[-1]
        return bool(row["historical_is_st"]), str(row.get("source", "historical_st_status"))
