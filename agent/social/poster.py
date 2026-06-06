"""
Narrative / social agent — Track 2 of the hackathon.

Responsibilities:
  1. Aggregate KOL narratives by ticker.
  2. Compute a "narrative heat" score (mentions × sentiment × engagement).
  3. When heat crosses a threshold, post an alpha alert to X.
  4. Maintain a rolling window so we don't spam.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from agent.data.x_stream import XClient
from agent.models import NarrativeEvent, Signal, Trade

log = logging.getLogger(__name__)


@dataclass
class NarrativeState:
    heat: float = 0.0
    mentions: int = 0
    avg_sentiment: float = 0.0
    last_post_ts: float = 0.0
    top_handles: List[str] = field(default_factory=list)


class NarrativeAgent:
    HEAT_POST_THRESHOLD = 1.5
    COOLDOWN_SECONDS = 60 * 30  # 30 min per symbol

    def __init__(self, x: XClient):
        self.x = x
        self.state: Dict[str, NarrativeState] = defaultdict(NarrativeState)

    def ingest(self, events: List[NarrativeEvent]) -> None:
        """Update narrative heat per ticker from incoming X events."""
        for ev in events:
            for tk in ev.tickers_mentioned:
                s = self.state[tk.upper()]
                s.mentions += 1
                s.heat += (1 + ev.likes / 100) * (0.5 + abs(ev.sentiment))
                # rolling avg sentiment
                s.avg_sentiment = (
                    0.7 * s.avg_sentiment + 0.3 * ev.sentiment
                )
                if ev.handle not in s.top_handles:
                    s.top_handles.append(ev.handle)

    def hot_narratives(self) -> List[Tuple[str, NarrativeState]]:
        return sorted(self.state.items(), key=lambda kv: kv[1].heat, reverse=True)

    async def maybe_post(self, signal: Signal, trade: Trade | None) -> List[dict]:
        """Post an alpha tweet for a hot narrative if cooldown elapsed."""
        if signal.side.value == "hold":
            return []
        s = self.state[signal.symbol]
        now = time.time()
        if s.heat < self.HEAT_POST_THRESHOLD:
            return []
        if now - s.last_post_ts < self.COOLDOWN_SECONDS:
            return []
        s.last_post_ts = now

        verdict = "BULLISH" if signal.side.value == "buy" else "BEARISH"
        text = (
            f"🐧 Mavis alpha\n\n"
            f"${signal.symbol} — {verdict} (conf {signal.confidence:.0%})\n\n"
            f"{signal.reasoning}\n\n"
            f"narrative heat: {s.heat:.1f} | sentiment: {s.avg_sentiment:+.2f}\n"
            f"KOLs: {', '.join('@'+h for h in s.top_handles[:3])}\n\n"
            f"#BNBHack #AITradingAgent"
        )
        result = await self.x.post_tweet(text)
        log.info("Posted alpha for $%s (heat=%.2f)", signal.symbol, s.heat)
        return [{"symbol": signal.symbol, "text": text, "result": result}]
