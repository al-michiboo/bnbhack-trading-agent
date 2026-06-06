"""
Mavis Trading Agent — configuration.

Loads from .env (via pydantic-settings) and exposes a single
`settings` object used across the codebase.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Network(str, Enum):
    TESTNET = "testnet"
    MAINNET = "mainnet"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Mode
    Mavis_mode: Mode = Mode.PAPER

    # CoinMarketCap
    CMC_API_KEY: str = ""
    CMC_BASE_URL: str = "https://pro-api.coinmarketcap.com"

    # LLM
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    Mavis_LLM_MODEL: str = "gpt-4o-mini"

    # X / Twitter
    X_BEARER_TOKEN: str = ""
    X_API_KEY: str = ""
    X_API_SECRET: str = ""
    X_ACCESS_TOKEN: str = ""
    X_ACCESS_SECRET: str = ""
    Mavis_X_WATCHLIST: str = "cz_binance,vitalikbuterin,Lookonchain"

    # BNB Chain
    BNB_NETWORK: Network = Network.TESTNET
    BNB_CHAIN_ID: int = 97
    BNB_RPC_URL: str = "https://data-seed-prebsc-1-s1.binance.org:8545"
    TW_PRIVATE_KEY: str = ""

    # Trust Wallet Agent Kit
    TW_AGENT_KIT_RPC: str = "https://api-agent-kit.trustwallet.com"
    TW_AGENT_KIT_API_KEY: str = ""

    # Risk
    MAX_POSITION_USD: float = 100.0
    MAX_DRAWDOWN_PCT: float = 10.0
    DAILY_TRADE_CAP: int = 20
    STOP_LOSS_PCT: float = 5.0
    TAKE_PROFIT_PCT: float = 12.0

    # Dashboard
    DASHBOARD_PORT: int = 8080
    LOG_LEVEL: str = "INFO"

    @field_validator("Mavis_X_WATCHLIST")
    @classmethod
    def _strip_handles(cls, v: str) -> str:
        return ",".join(h.strip().lstrip("@") for h in v.split(",") if h.strip())

    @property
    def watchlist(self) -> List[str]:
        return [h for h in self.Mavis_X_WATCHLIST.split(",") if h]

    @property
    def is_paper(self) -> bool:
        return self.Mavis_mode == Mode.PAPER

    @property
    def is_testnet(self) -> bool:
        return self.BNB_NETWORK == Network.TESTNET


settings = Settings()


def reload_settings() -> Settings:
    """Re-read .env (useful for tests / hot reload)."""
    global settings
    settings = Settings()
    return settings
