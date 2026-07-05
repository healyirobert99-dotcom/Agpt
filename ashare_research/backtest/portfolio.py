from __future__ import annotations

from dataclasses import dataclass, field

from .costs import transaction_cost


@dataclass
class Position:
    ts_code: str
    quantity: int = 0
    available_quantity: int = 0
    average_cost: float = 0.0
    last_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    entry_date: str | None = None

    def mark(self, price: float) -> None:
        self.last_price = float(price)
        self.market_value = self.quantity * self.last_price
        self.unrealized_pnl = (self.last_price - self.average_cost) * self.quantity


@dataclass
class Account:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    cumulative_cost: float = 0.0

    def refresh_available(self, trade_date: str) -> None:
        for pos in self.positions.values():
            pos.available_quantity = pos.quantity if pos.entry_date and pos.entry_date < trade_date else 0

    def buy(self, ts_code: str, quantity: int, price: float, trade_date: str, cost_bps: float) -> float:
        notional = quantity * price
        cost = transaction_cost(notional, cost_bps)
        if quantity <= 0 or self.cash + 1e-9 < notional + cost:
            raise ValueError("insufficient_cash")
        self.cash -= notional + cost
        self.cumulative_cost += cost
        pos = self.positions.get(ts_code)
        if pos is None:
            pos = Position(ts_code=ts_code, entry_date=trade_date)
            self.positions[ts_code] = pos
        old_value = pos.average_cost * pos.quantity
        pos.quantity += quantity
        pos.average_cost = (old_value + notional) / pos.quantity
        pos.entry_date = pos.entry_date or trade_date
        pos.available_quantity = 0
        pos.mark(price)
        return cost

    def sell(self, ts_code: str, quantity: int, price: float, cost_bps: float) -> float:
        pos = self.positions.get(ts_code)
        if pos is None or quantity <= 0 or pos.available_quantity < quantity:
            raise ValueError("unavailable_quantity")
        notional = quantity * price
        cost = transaction_cost(notional, cost_bps)
        self.cash += notional - cost
        self.cumulative_cost += cost
        pos.quantity -= quantity
        pos.available_quantity -= quantity
        pos.mark(price)
        if pos.quantity == 0:
            del self.positions[ts_code]
        return cost

    def mark_to_market(self, prices: dict[str, float]) -> tuple[float, list[dict]]:
        rows = []
        mv = 0.0
        for code, pos in sorted(self.positions.items()):
            if code not in prices or prices[code] is None:
                if pos.last_price <= 0:
                    raise ValueError(f"missing_valuation_price:{code}")
                valuation_status = "missing_close_carried_last_price"
                pos.mark(pos.last_price)
            else:
                valuation_status = "close_price"
                pos.mark(float(prices[code]))
            mv += pos.market_value
            rows.append(
                {
                    "ts_code": code,
                    "quantity": pos.quantity,
                    "available_quantity": pos.available_quantity,
                    "close_price": pos.last_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "valuation_status": valuation_status,
                }
            )
        return mv, rows
