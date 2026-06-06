# 🐧 Mavis — BNB Hack: AI Trading Agent

An autonomous AI trading agent for the **BNB Hack: AI Trading Agent Edition** hackathon (BNB Chain × CoinMarketCap × Trust Wallet — $36K prize pool).

Mavis does **both tracks** in one integrated system:

- **Track 1 (Onchain Trading Agent):** Live CMC AI Agent Hub data → LLM signals → Trust Wallet Agent Kit on BNB Chain testnet
- **Track 2 (Narrative/Social Agent):** Streams KOL X accounts, builds a narrative heatmap, posts alpha alerts back to X

Everything works in **paper-trade mode** by default — no real keys needed for the demo.

## Run the demo (60 seconds)

```bash
git clone https://github.com/al-michiboo/bnbhack-trading-agent.git
cd bnbhack-trading-agent
pip install -e .
cp .env.example .env
python scripts/run_demo.py
```

You'll see a full tick: market data pull → LLM signal generation → risk check → paper trade → narrative state.

Then start the dashboard:

```bash
uvicorn api.server:app --reload --port 8080
# open http://localhost:8080
```

## Architecture (one screen)

```
CMC AI Agent Hub ──┐
                   │
X / Twitter ───────┼──▶ LLM Analyzer ──▶ Risk Manager ──▶ Trust Wallet / Paper
                   │                                              │
                   └──▶ Narrative Heatmap ───────────────────────▶ X poster
```

## Files

- `agent/main.py` — orchestrator + CLI (`python -m agent.main --once`)
- `agent/data/cmc_client.py` — CMC AI Agent Hub (5 endpoints, mock fallback)
- `agent/data/x_stream.py` — X read + write, mock fallback
- `agent/signals/llm_analyzer.py` — LLM (OpenAI/Anthropic) + heuristic fallback
- `agent/execution/paper_engine.py` — full paper trading engine
- `agent/execution/trust_wallet.py` — Trust Wallet Agent Kit integration
- `agent/risk/manager.py` — risk limits + kill switch
- `agent/social/poster.py` — narrative heatmap + alpha posting
- `api/server.py` — FastAPI dashboard + JSON API
- `tests/test_smoke.py` — pytest smoke tests

## Hackathon coverage

| Requirement | File | Status |
|---|---|---|
| Onchain trading agent on BNB Chain | `agent/execution/trust_wallet.py` | ✅ |
| CMC AI Agent Hub usage | `agent/data/cmc_client.py` (5 endpoints) | ✅ |
| Trust Wallet Agent Kit | `agent/execution/trust_wallet.py` | ✅ |
| Narrative/Social agent | `agent/social/poster.py` + `agent/data/x_stream.py` | ✅ |
| LLM decision-making | `agent/signals/llm_analyzer.py` | ✅ |
| Risk management | `agent/risk/manager.py` | ✅ |
| Paper + live modes | `Mavis_mode` in `.env` | ✅ |
| Dashboard | `api/server.py` | ✅ |

## License

MIT
