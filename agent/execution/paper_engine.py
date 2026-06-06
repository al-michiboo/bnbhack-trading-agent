"""
Paper trading engine.

In-memory simulator that:
  - Fills market orders at the latest quote price
  - Tracks cash, positions, realized + unrealized PnL
  - Enforces daily trade cap
  - Updates a `Portfolio` snapshot every tick

Used by default (Mavis_MODE=paper) and as a backtest target.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent.config import settings
from agent.models import Portfolio, Position, Quote, Side, Signal, Trade

log = logging.getLogger(__name__)


class PaperEngine:
    def __init__(self, starting_cash_usd: float = 10_000.0):
        self.starting_cash = starting_cash_usd
        self.cash = starting_cash_usd
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.peak_equity = starting_cash_usd
        self.max_drawdown_pct = 0.0
        self.trades_today = 0
        self._today = datetime.now(timezone.utc).date()

    # --------------------------------------------------------------- core
    def execute(self, signal: Signal, quote: Quote) -> Optional[Trade]:
        if signal.side == Side.HOLD or signal.confidence < 0.5:
            return None
        if not self._can_trade():
            log.warning("Daily trade cap reached; skipping %s", signal.symbol)
            return None
        self._rollover_if_new_day()

        size_usd = min(signal.confidence * settings.MAX_POSITION_USD, settings.MAX_POSITION_USD)
        size_usd = min(size_usd, self.cash)
        if size_usd < 10:
            log.info("Insufficient cash for %s trade", signal.symbol)
            return None

        symbol = signal.symbol
        price = quote.price
        qty = size_usd / price

        if signal.side == Side.BUY:
            self.cash -= size_usd
            pos = self.positions.get(symbol)
            if pos:
                new_qty = pos.quantity + qty
                pos.entry_price = (pos.entry_price * pos.quantity + price * qty) / new_qty
                pos.quantity = new_qty
            else:
                self.positions[symbol] = Position(
                    symbol=symbol, quantity=qty, entry_price=price, current_price=price
                )
        elif signal.side == Side.SELL:
            pos = self.positions.get(symbol)
            if not pos:
                # Short-sim: open a short position
                self.positions[symbol] = Position(
                    symbol=symbol, quantity=-qty, entry_price=price, current_price=price
                )
                self.cash += size_usd
            else:
                # Close partial or full
                close_qty = min(qty, abs(pos.quantity))
                pnl = (price - pos.entry_price) * close_qty * (1 if pos.quantity > 0 else -1)
                self.realized_pnl += pnl
                self._update_streak(pnl)
                self.cash += close_qty * price
                pos.quantity += -close_qty * (1 if pos.quantity > 0 else 1)
                if abs(pos.quantity) < 1e-12:
                    del self.positions[symbol]

        self.total_trades += 1
        self.trades_today += 1

        return Trade(
            id=str(uuid.uuid4())[:12],
            symbol=symbol,
            side=signal.side,
            quantity=qty,
            price=price,
            notional_usd=size_usd,
            mode="paper",
            signal=signal,
        )

    def mark_to_market(self, quotes: dict[str, Quote]) -> Portfolio:
        unreal = 0.0
        for sym, pos in self.positions.items():
            q = quotes.get(sym)
            if q:
                pos.current_price = q.price
                pos.unrealized_pnl = (q.price - pos.entry_price) * pos.quantity
                unreal += pos.unrealized_pnl

        equity = self.cash + unreal
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = ((self.peak_equity - equity) / self.peak_equity * 100) if self.peak_equity else 0
        self.max_drawdown_pct = max(self.max_drawdown_pct, dd)

        return Portfolio(
            cash_usd=self.cash,
            positions=dict(self.positions),
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unreal,
            total_trades=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades,
            max_drawdown_pct=round(self.max_drawdown_pct, 3),
            peak_equity=self.peak_equity,
            daily_trades_remaining=max(0, settings.DAILY_TRADE_CAP - self.trades_today),
        )

    # --------------------------------------------------------- internals
    def _can_trade(self) -> bool:
        self._rollover_if_new_day()
        return self.trades_today < settings.DAILY_TRADE_CAP

    def _rollover_if_new_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._today:
            self._today = today
            self.trades_today = 0

    def _update_streak(self, pnl: float) -> None:
        if pnl > 0:
            self.winning_trades += 1
        elif pnl < 0:
            self.losing_trades += 1
