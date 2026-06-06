"""
One-shot demo: run the agent once and print a clean summary.

Usage:
    python scripts/run_demo.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Make `agent` importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import MavisAgent


def pretty(p):
    return json.dumps(p.model_dump(), indent=2, default=str)


async def main() -> None:
    print("=" * 60)
    print("  Mavis — BNB Hack Demo Run")
    print("  mode:", "PAPER" if __import__("agent.config", fromlist=["settings"]).settings.is_paper else "LIVE")
    print("=" * 60)
    agent = MavisAgent(watchlist=["BTC", "ETH", "BNB", "SOL", "PEPE"])
    portfolio = await agent.run_once()
    print()
    print("Final portfolio snapshot:")
    print(pretty(portfolio))
    print()
    print("State written to ./state/")
    print("Dashboard: uvicorn api.server:app --port 8080")


if __name__ == "__main__":
    asyncio.run(main())
