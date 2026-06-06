"""FastAPI dashboard + JSON API for Mavis.

Endpoints:
  GET /                      - HTML dashboard (single page)
  GET /api/portfolio         - latest portfolio snapshot
  GET /api/quotes            - latest market quotes
  GET /api/signals           - last 200 signals
  GET /api/trades            - last 200 trades
  GET /api/narratives        - narrative heatmap state
  GET /api/wallet            - Trust Wallet agent wallet info
  GET /api/health            - liveness check
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent.config import settings

log = logging.getLogger(__name__)

STATE_DIR = Path("state")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Mavis Trading Agent",
    description="BNB Hack: AI Trading Agent Edition — dashboard",
    version="0.1.0",
)


def _read_state(name: str) -> Any:
    path = STATE_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        log.warning("Failed to read %s: %s", name, e)
        return None


# ----------------------------------------------------------------- API
@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "mode": settings.Mavis_mode.value,
        "network": settings.BNB_NETWORK.value,
        "ts": _now_iso(),
    }


@app.get("/api/portfolio")
def portfolio() -> Any:
    p = _read_state("portfolio.json")
    if not p:
        raise HTTPException(404, "no portfolio state yet — run the agent first")
    return p


@app.get("/api/quotes")
def quotes() -> Any:
    return _read_state("last_quotes.json") or {}


@app.get("/api/signals")
def signals() -> Any:
    s = _read_state("signals.json") or {}
    return s.get("signals", [])


@app.get("/api/trades")
def trades() -> Any:
    t = _read_state("trades.json") or {}
    return t.get("trades", [])


@app.get("/api/narratives")
def narratives() -> Any:
    return _read_state("narratives.json") or {}


@app.get("/api/wallet")
def wallet() -> Any:
    return _read_state("wallet.json") or {}


# ----------------------------------------------------------- Dashboard UI
_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mavis — AI Trading Agent</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { --bg:#0b0d10; --fg:#e6e6e6; --muted:#8a8f98; --accent:#f3ba2f; --green:#3ecf8e; --red:#ef4444; --card:#14181d; --border:#222831; }
    * { box-sizing: border-box; }
    body { font-family: ui-monospace, Menlo, Consolas, monospace; background: var(--bg); color: var(--fg); margin: 0; padding: 24px; }
    h1 { color: var(--accent); margin: 0 0 4px; font-size: 22px; }
    h1::before { content: "🐧 "; }
    .sub { color: var(--muted); margin-bottom: 24px; font-size: 13px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
    .card h2 { font-size: 11px; text-transform: uppercase; color: var(--muted); margin: 0 0 8px; letter-spacing: 0.1em; }
    .big { font-size: 26px; font-weight: bold; }
    .green { color: var(--green); }
    .red { color: var(--red); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: normal; text-transform: uppercase; font-size: 10px; letter-spacing: 0.1em; }
    .section { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    .section h3 { margin: 0 0 12px; font-size: 13px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.1em; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: bold; text-transform: uppercase; }
    .pill.buy { background: rgba(62,207,142,0.15); color: var(--green); }
    .pill.sell { background: rgba(239,68,68,0.15); color: var(--red); }
    .pill.hold { background: rgba(138,143,152,0.15); color: var(--muted); }
    .heat-bar { display: inline-block; height: 6px; background: var(--accent); border-radius: 3px; vertical-align: middle; }
    .footer { text-align: center; color: var(--muted); font-size: 11px; margin-top: 32px; }
    .blink { animation: blink 2s infinite; }
    @keyframes blink { 50% { opacity: 0.4; } }
  </style>
</head>
<body>
  <h1>Mavis</h1>
  <div class="sub">BNB Hack · AI Trading Agent · <span id="mode"></span> · <span id="net"></span> · <span class="blink">●</span> live</div>

  <div class="grid" id="top"></div>

  <div class="section">
    <h3>Live positions</h3>
    <table id="positions">
      <thead><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Current</th><th>PnL</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="section">
    <h3>Recent signals</h3>
    <table id="signals">
      <thead><tr><th>Symbol</th><th>Side</th><th>Conf</th><th>Reasoning</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="section">
    <h3>Recent trades</h3>
    <table id="trades">
      <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Notional</th><th>Tx</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="section">
    <h3>Narrative heatmap</h3>
    <table id="narratives">
      <thead><tr><th>Symbol</th><th>Heat</th><th>Mentions</th><th>Sentiment</th><th>Top KOLs</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="footer">Mavis v0.1.0 · auto-refresh 5s · runs on BNB Smart Chain</div>

  <script>
    async function get(path) {
      const r = await fetch(path);
      if (!r.ok) return null;
      return r.json();
    }
    function fmt(n, d=2) { return n==null ? "—" : Number(n).toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d}); }
    function ts(s) { return s ? new Date(s).toLocaleTimeString() : "—"; }
    function shortAddr(a, n=6) { return a ? a.slice(0, n+2) + "…" + a.slice(-4) : "—"; }

    async function refresh() {
      const h = await get("/api/health");
      if (h) {
        document.getElementById("mode").textContent = "mode: " + h.mode;
        document.getElementById("net").textContent = "net: " + h.network;
      }
      const p = await get("/api/portfolio");
      const w = await get("/api/wallet");
      const sigs = await get("/api/signals");
      const trs = await get("/api/trades");
      const narr = await get("/api/narratives");
      const qs = await get("/api/quotes");

      // Top KPIs
      const equity = p ? (p.cash_usd + Object.values(p.positions||{}).reduce((s,pos)=>s + pos.quantity*pos.current_price, 0)) : 0;
      const realized = p ? p.realized_pnl : 0;
      const unreal = p ? p.unrealized_pnl : 0;
      const dd = p ? p.max_drawdown_pct : 0;
      const bal = w && w.balance_bnb != null ? w.balance_bnb : 0;
      const winrate = p && (p.winning_trades+p.losing_trades) > 0 ? (p.winning_trades/(p.winning_trades+p.losing_trades)*100) : 0;

      document.getElementById("top").innerHTML = `
        <div class="card"><h2>Equity</h2><div class="big">$${fmt(equity)}</div></div>
        <div class="card"><h2>Realized PnL</h2><div class="big ${realized>=0?'green':'red'}">$${fmt(realized)}</div></div>
        <div class="card"><h2>Unrealized PnL</h2><div class="big ${unreal>=0?'green':'red'}">$${fmt(unreal)}</div></div>
        <div class="card"><h2>Max Drawdown</h2><div class="big ${dd>5?'red':''}">${fmt(dd)}%</div></div>
        <div class="card"><h2>Win rate</h2><div class="big">${fmt(winrate,1)}%</div></div>
        <div class="card"><h2>Wallet</h2><div class="big">${fmt(bal,4)} BNB</div><div style="color:var(--muted);font-size:11px;margin-top:4px;">${shortAddr(w&&w.address)}</div></div>
      `;

      // Positions
      const posBody = document.querySelector("#positions tbody");
      posBody.innerHTML = "";
      if (p && p.positions) {
        for (const [sym, pos] of Object.entries(p.positions)) {
          const pnl = pos.unrealized_pnl || 0;
          posBody.innerHTML += `<tr>
            <td>${sym}</td>
            <td>${fmt(pos.quantity,6)}</td>
            <td>$${fmt(pos.entry_price,4)}</td>
            <td>$${fmt(pos.current_price,4)}</td>
            <td class="${pnl>=0?'green':'red'}">$${fmt(pnl)}</td>
          </tr>`;
        }
        if (Object.keys(p.positions).length === 0) {
          posBody.innerHTML = `<tr><td colspan="5" style="color:var(--muted);text-align:center;">no open positions</td></tr>`;
        }
      }

      // Signals
      const sigBody = document.querySelector("#signals tbody");
      sigBody.innerHTML = "";
      (sigs||[]).slice(-15).reverse().forEach(s => {
        sigBody.innerHTML += `<tr>
          <td><b>${s.symbol}</b></td>
          <td><span class="pill ${s.side}">${s.side}</span></td>
          <td>${(s.confidence*100).toFixed(0)}%</td>
          <td>${s.reasoning||""}</td>
        </tr>`;
      });
      if (!sigs || sigs.length===0) sigBody.innerHTML = `<tr><td colspan="4" style="color:var(--muted);text-align:center;">no signals yet</td></tr>`;

      // Trades
      const trBody = document.querySelector("#trades tbody");
      trBody.innerHTML = "";
      (trs||[]).slice(-15).reverse().forEach(t => {
        trBody.innerHTML += `<tr>
          <td>${ts(t.ts)}</td>
          <td><b>${t.symbol}</b></td>
          <td><span class="pill ${t.side}">${t.side}</span></td>
          <td>${fmt(t.quantity,6)}</td>
          <td>$${fmt(t.price,4)}</td>
          <td>$${fmt(t.notional_usd,2)}</td>
          <td style="color:var(--muted);font-size:10px;">${shortAddr(t.tx_hash,8)}</td>
        </tr>`;
      });
      if (!trs || trs.length===0) trBody.innerHTML = `<tr><td colspan="7" style="color:var(--muted);text-align:center;">no trades yet</td></tr>`;

      // Narratives
      const narrBody = document.querySelector("#narratives tbody");
      narrBody.innerHTML = "";
      const narrArr = Object.entries(narr||{}).sort((a,b)=>b[1].heat - a[1].heat);
      narrArr.slice(0,12).forEach(([sym, s]) => {
        const w = Math.min(s.heat*20, 200);
        narrBody.innerHTML += `<tr>
          <td><b>${sym}</b></td>
          <td><span class="heat-bar" style="width:${w}px"></span> ${fmt(s.heat,2)}</td>
          <td>${s.mentions}</td>
          <td class="${s.avg_sentiment>=0?'green':'red'}">${(s.avg_sentiment>=0?'+':'')}${fmt(s.avg_sentiment,2)}</td>
          <td style="color:var(--muted);">${(s.top_handles||[]).slice(0,3).map(h=>'@'+h).join(' ')}</td>
        </tr>`;
      });
      if (narrArr.length===0) narrBody.innerHTML = `<tr><td colspan="5" style="color:var(--muted);text-align:center;">no narratives yet</td></tr>`;
    }
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
