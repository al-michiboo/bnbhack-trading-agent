# 🐧 Mavis — Quick Start

## TL;DR
```bash
pip install -e .
cp .env.example .env
python scripts/run_demo.py            # single tick, no keys needed
uvicorn api.server:app --port 8080    # dashboard
```

## What you'll see

1. The demo prints a full agent cycle: market pull → LLM signal → risk check → paper trade.
2. State is persisted to `state/portfolio.json` (and 4 other files).
3. The dashboard reads these files and renders PnL, positions, signals, trades, narratives.

## What if I add my own keys?

Edit `.env`:

- **`CMC_API_KEY`** — get from https://pro.coinmarketcap.com → real AI Agent Hub data instead of mocks.
- **`OPENAI_API_KEY`** — get from https://platform.openai.com → LLM-driven signals (else heuristic).
- **`X_BEARER_TOKEN`** — get from https://developer.twitter.com → real X stream + posting.
- **`TW_PRIVATE_KEY`** — a **testnet** BNB wallet key → real on-chain trades (use a throwaway wallet!).
- **`Mavis_MODE=live`** — flip to live mode to actually broadcast transactions.
- **`BNB_NETWORK=mainnet`** — for production deployment (careful!).

## Risk knobs

In `.env`:
```
MAX_POSITION_USD=100     # max per trade
MAX_DRAWDOWN_PCT=10      # circuit breaker
DAILY_TRADE_CAP=20       # max trades per UTC day
STOP_LOSS_PCT=5
TAKE_PROFIT_PCT=12
```

## Test

```bash
pytest -v
```
