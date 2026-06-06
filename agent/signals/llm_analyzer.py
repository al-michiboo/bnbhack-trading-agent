"""
LLM-powered signal analyzer.

Takes the current market state + recent narrative events and asks the LLM
to produce a structured `Signal` (buy / sell / hold + confidence + reasoning).

Supports OpenAI by default; Anthropic supported if `ANTHROPIC_API_KEY` is set.
Falls back to a heuristic analyzer if no key is present (so demo works).
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from agent.config import settings
from agent.data.cmc_client import CMCClient
from agent.data.x_stream import XClient
from agent.models import NarrativeEvent, Quote, Side, Signal

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Mavis, an autonomous crypto trading agent on BNB Chain.
You receive real-time market data from CoinMarketCap's AI Agent Hub and narrative
signals from X. Produce a single JSON signal.

Decision rules:
- Be CONSERVATIVE. Only signal with confidence > 0.6.
- HOLD if no edge is clear.
- Match direction to narrative: positive social + inflows = BUY; opposite = SELL.
- Size risk by confidence: low confidence -> tighter stop loss.

Return STRICT JSON:
{
  "side": "buy" | "sell" | "hold",
  "confidence": 0.0..1.0,
  "reasoning": "one or two sentences",
  "target_price": number | null,
  "stop_loss": number | null,
  "take_profit": number | null,
  "supporting_narratives": ["..."]
}
"""


class LLMAnalyzer:
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.Mavis_LLM_MODEL
        self._openai = None
        self._anthropic = None
        if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-your"):
            try:
                from openai import AsyncOpenAI
                self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            except Exception as e:
                log.warning("OpenAI init failed: %s", e)
        if settings.ANTHROPIC_API_KEY:
            try:
                from anthropic import AsyncAnthropic
                self._anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            except Exception as e:
                log.warning("Anthropic init failed: %s", e)

    @property
    def has_llm(self) -> bool:
        return self._openai is not None or self._anthropic is not None

    async def analyze(
        self,
        symbol: str,
        quote: Quote,
        narratives: List[NarrativeEvent],
        intelligence: dict,
        sentiment: float,
    ) -> Signal:
        if not self.has_llm:
            return self._heuristic(symbol, quote, narratives, intelligence, sentiment)

        prompt = self._build_user_prompt(symbol, quote, narratives, intelligence, sentiment)
        try:
            if self._openai:
                return await self._openai_call(prompt, symbol)
            if self._anthropic:
                return await self._anthropic_call(prompt, symbol)
        except Exception as e:
            log.warning("LLM call failed, using heuristic: %s", e)
        return self._heuristic(symbol, quote, narratives, intelligence, sentiment)

    def _build_user_prompt(self, symbol, quote, narratives, intel, sentiment) -> str:
        narr_text = "\n".join(
            f"  - @{n.handle}: \"{n.text}\" (tickers={n.tickers_mentioned}, sent={n.sentiment:+.2f}, likes={n.likes})"
            for n in narratives[:8]
        ) or "  (no recent narratives)"
        return f"""Symbol: {symbol}
Quote: price=${quote.price:,.4f}  1h={quote.pct_change_1h:+.2f}%  24h={quote.pct_change_24h:+.2f}%  7d={quote.pct_change_7d:+.2f}%
24h volume: ${quote.volume_24h:,.0f}   Market cap: ${quote.market_cap:,.0f}   CMC rank: {quote.cmc_rank}
Agent hub sentiment: {sentiment:+.3f}  Smart money flow: {intel.get('smart_money_flow')}  Net whale USD: {intel.get('net_whale_usd'):+,.0f}

Recent X narratives:
{narr_text}

Output JSON only."""

    async def _openai_call(self, prompt: str, symbol: str) -> Signal:
        resp = await self._openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return self._parse(symbol, resp.choices[0].message.content)

    async def _anthropic_call(self, prompt: str, symbol: str) -> Signal:
        resp = await self._anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        return self._parse(symbol, text)

    def _parse(self, symbol: str, raw: str) -> Signal:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in LLM output: {raw[:200]}")
        data = json.loads(m.group(0))
        side_str = str(data.get("side", "hold")).lower()
        side = Side(side_str) if side_str in {s.value for s in Side} else Side.HOLD
        return Signal(
            symbol=symbol,
            side=side,
            confidence=float(data.get("confidence", 0.0)),
            reasoning=str(data.get("reasoning", "")),
            target_price=_opt_float(data.get("target_price")),
            stop_loss=_opt_float(data.get("stop_loss")),
            take_profit=_opt_float(data.get("take_profit")),
            supporting_narratives=list(data.get("supporting_narratives", [])),
        )

    # ---------------------------------------------------------- heuristic
    def _heuristic(
        self, symbol, quote, narratives, intel, sentiment
    ) -> Signal:
        """Rule-based fallback when no LLM key is present."""
        score = 0.0
        reasons: list[str] = []

        if quote.pct_change_24h > 5:
            score += 0.3
            reasons.append("24h momentum positive")
        elif quote.pct_change_24h < -5:
            score -= 0.3
            reasons.append("24h momentum negative")

        if intel.get("smart_money_flow") == "inflow":
            score += 0.3
            reasons.append("whale inflow")
        elif intel.get("smart_money_flow") == "outflow":
            score -= 0.3
            reasons.append("whale outflow")

        score += sentiment * 0.4
        if abs(sentiment) > 0.2:
            reasons.append(f"social sentiment {sentiment:+.2f}")

        # Cross-check with narratives
        if narratives:
            avg = sum(n.sentiment for n in narratives) / len(narratives)
            score += avg * 0.2
            if any(symbol.upper() in n.tickers_mentioned for n in narratives):
                reasons.append(f"mentioned by KOLs: {', '.join('@'+n.handle for n in narratives[:3] if symbol.upper() in n.tickers_mentioned)}")

        # Decide
        if score > 0.25:
            side = Side.BUY
            conf = min(0.95, 0.5 + abs(score) * 0.4)
        elif score < -0.25:
            side = Side.SELL
            conf = min(0.95, 0.5 + abs(score) * 0.4)
        else:
            side = Side.HOLD
            conf = 0.4

        return Signal(
            symbol=symbol,
            side=side,
            confidence=round(conf, 3),
            reasoning="; ".join(reasons) or "no clear edge, holding",
            target_price=quote.price * (1.05 if side == Side.BUY else 0.95) if side != Side.HOLD else None,
            stop_loss=quote.price * (1 - settings.STOP_LOSS_PCT / 100) if side == Side.BUY else None,
            take_profit=quote.price * (1 + settings.TAKE_PROFIT_PCT / 100) if side == Side.BUY else None,
            supporting_narratives=[n.text[:80] for n in narratives[:3]],
        )


def _opt_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
