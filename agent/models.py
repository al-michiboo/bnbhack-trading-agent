"""
Domain models — the lingua franca of Mavis.

Pydantic models for ticks, signals, trades, narrative events.
Used by all submodules so we get type safety + JSON serialization
for the dashboard.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Quote(BaseModel):
    """A normalized market quote from CMC."""
    symbol: str
    price: float
    pct_change_1h: float = 0.0
    pct_change_24h: float = 0.0
    pct_change_7d: float = 0.0
    volume_24h: float = 0.0
    market_cap: float = 0.0
    cmc_rank: Optional[int] = None
    ts: datetime = Field(default_factory=now_utc)


class NarrativeEvent(BaseModel):
    """A single X/Twitter mention with metadata."""
    handle: str
    text: str
    url: str = ""
    likes: int = 0
    retweets: int = 0
    tickers_mentioned: list[str] = []
    sentiment: float = 0.0  # -1..+1
    ts: datetime = Field(default_factory=now_utc)


class Signal(BaseModel):
    """A trading signal emitted by the LLM analyzer."""
    symbol: str
    side: Side
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    supporting_narratives: list[str] = []
    ts: datetime = Field(default_factory=now_utc)


class Trade(BaseModel):
    """An executed (or paper) trade."""
    id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    notional_usd: float
    mode: str  # "paper" or "live"
    tx_hash: Optional[str] = None
    pnl_usd: float = 0.0
    signal: Optional[Signal] = None
    ts: datetime = Field(default_factory=now_utc)


class Position(BaseModel):
    """Current open position in a symbol."""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    opened_at: datetime = Field(default_factory=now_utc)


class Portfolio(BaseModel):
    """Aggregate state of the agent's portfolio."""
    cash_usd: float
    positions: dict[str, Position] = {}
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    daily_trades_remaining: int = 0
    ts: datetime = Field(default_factory=now_utc)

    @property
    def equity(self) -> float:
        return self.cash_usd + sum(p.quantity * p.current_price for p in self.positions.values())

    @property
    def win_rate(self) -> float:
        closed = self.winning_trades + self.losing_trades
        return self.winning_trades / closed if closed else 0.0
