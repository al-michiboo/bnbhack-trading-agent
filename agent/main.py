"""
Mavis — main orchestrator.

The agent loop:
  1. Pull market data from CMC AI Agent Hub
  2. Pull narrative stream from X watchlist
  3. Update narrative heatmap (social agent)
  4. For each watched symbol: produce an LLM signal
  5. Risk-check each signal
  6. Execute (paper or live) approved signals
  7. Maybe post alpha to X
  8. Mark-to-market + persist state
  9. Sleep until next tick
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import click
import structlog

from agent.config import settings, reload_settings
from agent.data.cmc_client import CMCClient
from agent.data.x_stream import XClient
from agent.execution.paper_engine import PaperEngine
from agent.execution.trust_wallet import TrustWalletExecutor
from agent.models import Portfolio, Quote, Trade
from agent.risk.manager import RiskManager
from agent.signals.llm_analyzer import LLMAnalyzer
from agent.social.poster import NarrativeAgent

# Default watchlist — diversified across majors + memetic names
DEFAULT_WATCHLIST = ["BTC", "ETH", "BNB", "SOL", "DOGE", "PEPE", "AVAX", "LINK"]

# Default tick interval
TICK_SECONDS = 60

log = structlog.get_logger("Mavis")

STATE_DIR = Path("state")
STATE_DIR.mkdir(exist_ok=True)


def _save_json(name: str, payload: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / name).write_text(json.dumps(payload, indent=2, default=str))


def _structlog_setup() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


class MavisAgent:
    def __init__(
        self,
        watchlist: List[str] | None = None,
        tick_seconds: int = TICK_SECONDS,
    ):
        self.watchlist = watchlist or DEFAULT_WATCHLIST
        self.tick_seconds = tick_seconds
        self.risk = RiskManager()
        self.paper = PaperEngine(starting_cash_usd=10_000.0)
        self.analyzer = LLMAnalyzer()
        self.running = False
        self.last_trades: List[Trade] = []
        self.last_signals: list = []

    async def run_once(self) -> Portfolio:
        """One full agent cycle. Returns the latest portfolio snapshot."""
        log.info("agent.tick.start", symbols=self.watchlist, mode=settings.Mavis_mode.value)
        async with CMCClient() as cmc, XClient() as x, TrustWalletExecutor() as tw:
            # 1) market data
            quotes = await cmc.get_quotes(self.watchlist)
            quote_map = {q.symbol: q for q in quotes}

            # 2) X stream
            events = await x.stream_watchlist(settings.watchlist, limit_per=3)

            # 3) narrative aggregation
            narr_agent = NarrativeAgent(x)
            narr_agent.ingest(events)
            self.last_narrative_state = narr_agent.state  # type: ignore[attr-defined]

            # 4) wallet info (only meaningful in live mode)
            wallet = await tw.get_wallet_info()
            log.info("agent.wallet", **wallet)

            # 5) per-symbol signal + execution
            for symbol in self.watchlist:
                quote = quote_map.get(symbol)
                if not quote:
                    continue
                intel = await cmc.market_intelligence(symbol)
                sentiment = await cmc.sentiment(symbol)
                relevant = [e for e in events if symbol in e.tickers_mentioned]

                signal = await self.analyzer.analyze(symbol, quote, relevant, intel, sentiment)
                self.last_signals.append(signal)

                portfolio = self.paper.mark_to_market(quote_map)
                decision = self.risk.check(signal, portfolio)
                if not decision.approved:
                    log.info("agent.signal.denied", symbol=symbol, reason=decision.reason)
                    continue

                # Execute
                if settings.is_paper:
                    trade = self.paper.execute(signal, quote)
                else:
                    qty = decision.adjusted_size_usd / quote.price
                    trade = await tw.execute_trade(signal, qty, quote.price)

                if trade:
                    self.last_trades.append(trade)
                    log.info(
                        "agent.trade",
                        symbol=symbol, side=trade.side.value,
                        qty=round(trade.quantity, 6),
                        px=round(trade.price, 4),
                        notional=round(trade.notional_usd, 2),
                        mode=trade.mode,
                        tx=trade.tx_hash or "-",
                    )
                    # Social posting
                    await narr_agent.maybe_post(signal, trade)

            # 6) snapshot
            portfolio = self.paper.mark_to_market(quote_map)
            self._persist(quotes, portfolio, wallet, narr_agent)
            log.info(
                "agent.tick.end",
                equity=round(portfolio.equity, 2),
                realized=round(portfolio.realized_pnl, 2),
                trades=portfolio.total_trades,
            )
            return portfolio

    async def run_forever(self) -> None:
        self.running = True
        while self.running:
            try:
                await self.run_once()
            except Exception as e:
                log.error("agent.tick.error", error=str(e))
            await asyncio.sleep(self.tick_seconds)

    def stop(self) -> None:
        self.running = False

    # ----------------------------------------------------------- persistence
    def _persist(self, quotes, portfolio, wallet, narr_agent):
        _save_json("portfolio.json", portfolio.model_dump())
        _save_json("last_quotes.json", {q.symbol: q.model_dump() for q in quotes})
        _save_json("wallet.json", wallet)
        _save_json(
            "trades.json",
            {"trades": [t.model_dump() for t in self.last_trades[-200:]]},
        )
        _save_json(
            "signals.json",
            {"signals": [s.model_dump() for s in self.last_signals[-200:]]},
        )
        _save_json(
            "narratives.json",
            {sym: {
                "heat": s.heat, "mentions": s.mentions,
                "avg_sentiment": s.avg_sentiment, "top_handles": s.top_handles,
            } for sym, s in narr_agent.state.items()},
        )


# =============================================================== CLI entry
@click.command()
@click.option("--once", is_flag=True, help="Run a single tick and exit (good for cron/demo).")
@click.option("--symbols", default=",".join(DEFAULT_WATCHLIST),
              help="Comma-separated symbols to watch.")
@click.option("--interval", default=TICK_SECONDS, type=int, help="Seconds between ticks.")
def cli(once: bool, symbols: str, interval: int) -> None:
    """Mavis — BNB Hack AI Trading Agent."""
    _structlog_setup()
    reload_settings()
    watchlist = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    agent = MavisAgent(watchlist=watchlist, tick_seconds=interval)

    def _handle_sigterm(*_a):
        log.info("agent.shutdown.requested")
        agent.stop()
    signal.signal(signal.SIGINT, lambda *_: _handle_sigterm())
    signal.signal(signal.SIGTERM, lambda *_: _handle_sigterm())

    if once:
        asyncio.run(agent.run_once())
    else:
        asyncio.run(agent.run_forever())


if __name__ == "__main__":
    cli()
