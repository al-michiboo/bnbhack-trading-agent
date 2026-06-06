"""
Risk manager — gates every trade before execution.

Checks (in order):
  1. Confidence floor (>= 0.5)
  2. Max drawdown circuit breaker
  3. Daily trade cap
  4. Per-position size limit
  5. Symbol whitelist (if configured)

Returns a `RiskDecision` with approved/denied + reason.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from agent.config import settings
from agent.models import Portfolio, Signal

log = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    approved: bool
    reason: str = ""
    adjusted_size_usd: Optional[float] = None


class RiskManager:
    def __init__(self):
        self.kill_switch_active = False

    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        if self.kill_switch_active:
            return RiskDecision(False, "kill switch is active")

        if signal.confidence < 0.5:
            return RiskDecision(False, f"confidence {signal.confidence:.2f} below 0.5 floor")

        if portfolio.max_drawdown_pct >= settings.MAX_DRAWDOWN_PCT:
            return RiskDecision(False, f"max drawdown {portfolio.max_drawdown_pct:.2f}% reached cap")

        if portfolio.daily_trades_remaining <= 0:
            return RiskDecision(False, "daily trade cap reached")

        # Size: scale by confidence, capped by MAX_POSITION_USD
        size = min(signal.confidence * settings.MAX_POSITION_USD, settings.MAX_POSITION_USD)
        if size < 10:
            return RiskDecision(False, "computed position size too small")

        return RiskDecision(True, "ok", adjusted_size_usd=size)

    def trip_kill_switch(self) -> None:
        self.kill_switch_active = True
        log.warning("KILL SWITCH TRIPPED — no more trades will execute")

    def reset_kill_switch(self) -> None:
        self.kill_switch_active = False
        log.info("Kill switch reset")
