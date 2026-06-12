"""
Mavis live-trading cron tick.

Runs one full agent cycle, then sends a short PnL report to Micky
via WeChat. Designed to be invoked every 4h during the official Track 1
live-trading window (Jun 22 12:00 UTC -> Jun 28 12:00 UTC).

Usage:
    python scripts/mavis_tick_report.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make `agent` importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Also add the hermes site-packages so we can import `gateway.platforms.weixin`
# (the WeChat sender lives in the hermes install, not the project venv)
HERMES_SITE = "/usr/local/lib/python3.11/site-packages"
if HERMES_SITE not in sys.path:
    sys.path.insert(0, HERMES_SITE)

# Load /root/.hermes/.env first (canonical WeChat credentials)
hermes_env = Path("/root/.hermes/.env")
if hermes_env.exists():
    for line in hermes_env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

# Then load repo .env (CMC key, LLM key, etc.)
ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from agent.main import MavisAgent  # noqa: E402

WECHAT_CHAT_ID = "o9cq804_kypg8_o-nLR6Mu7MoUUk@im.wechat"


def fmt_pct(x: float) -> str:
    return f"{x:+.2f}%" if x else "0.00%"


async def run() -> None:
    agent = MavisAgent(
        watchlist=["BTC", "ETH", "BNB", "SOL", "DOGE", "PEPE", "AVAX", "LINK"],
        tick_seconds=60,
    )
    try:
        # Bound the whole tick to 110s — under the cron's 120s script
        # timeout so the scheduler doesn't kill us mid-WeChat-send.
        # Last full run on 2026-06-12 took ~95s for 8 symbols.
        portfolio = await asyncio.wait_for(agent.run_once(), timeout=110.0)
    except asyncio.TimeoutError:
        sent = await send_wechat("🐧 Mavis tick TIMED OUT (110s)")
        print(f"[wechat-on-timeout] sent={sent}")
        return
    except Exception as e:
        # Always send a report — even on failure — so silence doesn't equal success
        sent = await send_wechat(f"🐧 Mavis tick FAILED\n{type(e).__name__}: {e}")
        print(f"[wechat-on-fail] sent={sent}")
        raise

    # Build compact report
    starting_cash = 10_000.0
    equity = float(getattr(portfolio, "equity", 0.0))
    pnl = equity - starting_cash
    pnl_pct = (pnl / starting_cash) * 100.0 if starting_cash else 0.0
    realized = float(getattr(portfolio, "realized_pnl", 0.0))
    total_trades = int(getattr(portfolio, "total_trades", 0))

    # Last few trades (most recent 3)
    last_trades = agent.last_trades[-3:] if agent.last_trades else []
    trade_lines = []
    for t in last_trades:
        side = t.side.value if hasattr(t.side, "value") else str(t.side)
        trade_lines.append(
            f"  {side.upper()} {t.symbol} qty={round(float(t.quantity), 4)} @ {round(float(t.price), 4)}"
        )
    trades_block = "\n".join(trade_lines) if trade_lines else "  (none this tick)"

    msg = (
        f"🐧 Mavis live-tick\n"
        f"equity: ${equity:,.2f}  pnl: ${pnl:,.2f} ({fmt_pct(pnl_pct)})\n"
        f"realized: ${realized:,.2f}   trades: {total_trades}\n"
        f"recent:\n{trades_block}"
    )
    sent = await send_wechat(msg)
    print(f"[wechat] sent={sent}")
    print(msg)


def send_wechat(msg: str) -> bool:
    """Send message to Micky via WeChat. Returns True on success.

    Canonical pattern: inline send_weixin_direct call (no bridge).
    Token is loaded from WEIXIN_TOKEN env var.

    Returns an awaitable so callers in async context can `await` it.
    To call from sync context, use `asyncio.run(send_wechat(msg))`.
    """
    async def _send() -> bool:
        try:
            from gateway.platforms.weixin import send_weixin_direct
        except Exception as e:
            print(f"[warn] wechat import failed: {e}", file=sys.stderr)
            return False

        token = os.environ.get("WEIXIN_TOKEN")
        if not token:
            print("[warn] WEIXIN_TOKEN not set in env", file=sys.stderr)
            return False

        try:
            # Use env vars for base_url/cdn_base_url/account_id so we don't hardcode
            extra = {"account_id": os.environ.get("WEIXIN_ACCOUNT_ID", "767876f95ef4@im.bot")}
            result = await send_weixin_direct(
                extra=extra,
                token=token,
                chat_id=WECHAT_CHAT_ID,
                message=msg,
            )
            success = bool(result and result.get("success"))
            print(f"[wechat] result: {result}")
            return success
        except Exception as e:
            print(f"[warn] wechat send failed: {e}", file=sys.stderr)
            return False

    return _send()


if __name__ == "__main__":
    asyncio.run(run())
