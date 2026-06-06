"""Smoke test — runs the agent once in paper mode and asserts the portfolio snapshot exists."""
import asyncio
import json
from pathlib import Path

import pytest

from agent.main import MavisAgent


@pytest.mark.asyncio
async def test_run_once_writes_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = MavisAgent(watchlist=["BTC", "ETH"])
    portfolio = await agent.run_once()
    assert portfolio.cash_usd >= 0
    assert (tmp_path / "state" / "portfolio.json").exists()
    data = json.loads((tmp_path / "state" / "portfolio.json").read_text())
    assert "cash_usd" in data
    assert "total_trades" in data


@pytest.mark.asyncio
async def test_paper_engine_buy_then_sell():
    from agent.execution.paper_engine import PaperEngine
    from agent.models import Quote, Side, Signal
    from datetime import datetime, timezone

    eng = PaperEngine(starting_cash_usd=10_000.0)
    sig = Signal(symbol="BTC", side=Side.BUY, confidence=0.8, reasoning="test")
    q = Quote(symbol="BTC", price=60_000.0, ts=datetime.now(timezone.utc))
    t = eng.execute(sig, q)
    assert t is not None
    assert t.side == Side.BUY
    assert "BTC" in eng.positions
    assert eng.cash < 10_000.0

    # Sell half
    sig2 = Signal(symbol="BTC", side=Side.SELL, confidence=0.8, reasoning="test2")
    t2 = eng.execute(sig2, q)
    assert t2 is not None
    assert t2.side == Side.SELL
    assert eng.total_trades == 2


@pytest.mark.asyncio
async def test_risk_manager_killswitch():
    from agent.risk.manager import RiskManager
    from agent.models import Portfolio
    r = RiskManager()
    r.trip_kill_switch()
    p = Portfolio(cash_usd=1000)
    from agent.models import Side, Signal
    sig = Signal(symbol="X", side=Side.BUY, confidence=0.9, reasoning="t")
    d = r.check(sig, p)
    assert d.approved is False
    assert "kill switch" in d.reason
