from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app import analyze_one, provider
from data.provider import DataProviderError, normalize_symbol
from engine_layer import backtest_engine
from full_market_scanner import scan_full_market_top10
from intraday_signal_engine import scan_intraday_signals
from market_overview_service import get_market_overview
from money_flow_anomaly_detector import scan_money_flow_anomalies


app = FastAPI(title="A股AI量化分析API", version="5.0.0")


class SearchRequest(BaseModel):
    keyword: Optional[str] = None
    q: Optional[str] = None


class SymbolRequest(BaseModel):
    symbol: str


class BacktestRequest(BaseModel):
    symbol: str = "300394"
    short_window: int = 5
    long_window: int = 20
    days: int = 180


@app.get("/")
def root() -> dict[str, Any]:
    return {"status": "ok", "service": "A股AI量化分析API", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/search_stock")
def search_stock(payload: SearchRequest) -> list[dict[str, str]]:
    try:
        return provider.search_stock(payload.keyword or payload.q or "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/analyze_stock")
def analyze_stock(payload: SymbolRequest) -> dict[str, Any]:
    try:
        return analyze_one(normalize_symbol(payload.symbol))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis failed: {exc}") from exc


@app.post("/analyze")
def analyze_alias(payload: SymbolRequest) -> dict[str, Any]:
    return analyze_stock(payload)


@app.post("/screen_stocks")
def screen_stocks() -> list[dict[str, Any]]:
    return scan_full_market_top10(limit=10)


@app.post("/top10")
def top10_alias() -> list[dict[str, Any]]:
    return screen_stocks()


@app.get("/stock_detail")
def stock_detail(symbol: str = Query(...)) -> dict[str, Any]:
    result = analyze_stock(SymbolRequest(symbol=symbol))
    return {
        "symbol": result["symbol"],
        "name": result["name"],
        "price": result["price"],
        "technical_analysis": result["technical_analysis"],
        "fund_flow_analysis": result["fund_flow_analysis"],
        "fundamental_analysis": result["fundamental_analysis"],
        "sentiment_analysis": result["sentiment_analysis"],
        "final_reason": result["final_reason"],
    }


@app.post("/market_overview")
def market_overview() -> dict[str, Any]:
    return get_market_overview()


@app.post("/intraday_signals")
def intraday_signals() -> dict[str, Any]:
    watchlist = scan_full_market_top10(limit=10)
    return {"signals": scan_intraday_signals(watchlist), "cache_ttl": 60, "watchlist_size": len(watchlist)}


@app.post("/money_flow_anomalies")
def money_flow_anomalies() -> dict[str, Any]:
    watchlist = scan_full_market_top10(limit=10)
    return {"anomalies": scan_money_flow_anomalies(watchlist), "cache_ttl": 60, "watchlist_size": len(watchlist)}


@app.post("/backtest_strategy")
def backtest_strategy(payload: BacktestRequest) -> dict[str, Any]:
    try:
        return backtest_engine.run_backtest(
            normalize_symbol(payload.symbol),
            short_window=payload.short_window,
            long_window=payload.long_window,
            days=payload.days,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"backtest_strategy failed: {exc}") from exc
