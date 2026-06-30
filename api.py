from __future__ import annotations

from typing import Any, Optional

<<<<<<< HEAD
from fastapi import FastAPI, Query
from pydantic import BaseModel

from services import engine_loader
=======
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app import analyze_one, provider
from data.provider import DataProviderError, normalize_symbol
from engine_layer import backtest_engine
from full_market_scanner import scan_full_market_top10
from intraday_signal_engine import scan_intraday_signals
from market_overview_service import get_market_overview
from money_flow_anomaly_detector import scan_money_flow_anomalies
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b


app = FastAPI(title="A股AI量化分析API", version="5.0.0")


class SearchRequest(BaseModel):
    keyword: Optional[str] = None
    q: Optional[str] = None


class SymbolRequest(BaseModel):
    symbol: str


<<<<<<< HEAD
class LimitRequest(BaseModel):
    limit: int = 10


class IntradaySignalRequest(BaseModel):
    symbol: Optional[str] = None
    limit: int = 10


class MoneyFlowRequest(BaseModel):
    symbol: Optional[str] = None
    limit: int = 10


=======
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b
class BacktestRequest(BaseModel):
    symbol: str = "300394"
    short_window: int = 5
    long_window: int = 20
    days: int = 180


<<<<<<< HEAD
def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": ""}


def _safe(func: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    return engine_loader.safe_call(func, *args, **kwargs)


@app.get("/")
def root() -> dict[str, Any]:
    return _ok({"status": "ok", "service": "A股AI量化分析API", "docs": "/docs"})


@app.get("/health")
def health() -> dict[str, Any]:
    return _ok({"status": "ok"})


@app.post("/search_stock")
def search_stock(payload: SearchRequest) -> dict[str, Any]:
    return _safe(engine_loader.search_stock, payload.keyword or payload.q or "")
=======
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
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b


@app.post("/analyze_stock")
def analyze_stock(payload: SymbolRequest) -> dict[str, Any]:
<<<<<<< HEAD
    return _safe(engine_loader.analyze_stock, payload.symbol)
=======
    try:
        return analyze_one(normalize_symbol(payload.symbol))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis failed: {exc}") from exc
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b


@app.post("/analyze")
def analyze_alias(payload: SymbolRequest) -> dict[str, Any]:
    return analyze_stock(payload)


@app.post("/screen_stocks")
<<<<<<< HEAD
def screen_stocks(payload: Optional[LimitRequest] = None) -> dict[str, Any]:
    limit = payload.limit if payload else 10
    return _safe(engine_loader.scan_top10, limit)


@app.post("/top10")
def top10_alias(payload: Optional[LimitRequest] = None) -> dict[str, Any]:
    return screen_stocks(payload)


@app.get("/scan/top10")
def scan_top10(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    return _safe(engine_loader.scan_top10, limit)
=======
def screen_stocks() -> list[dict[str, Any]]:
    return scan_full_market_top10(limit=10)


@app.post("/top10")
def top10_alias() -> list[dict[str, Any]]:
    return screen_stocks()
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b


@app.get("/stock_detail")
def stock_detail(symbol: str = Query(...)) -> dict[str, Any]:
<<<<<<< HEAD
    return _safe(engine_loader.stock_detail, symbol)
=======
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
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b


@app.post("/market_overview")
def market_overview() -> dict[str, Any]:
<<<<<<< HEAD
    return _safe(engine_loader.market_overview)


@app.post("/intraday/signal")
def intraday_signal(payload: Optional[IntradaySignalRequest] = None) -> dict[str, Any]:
    payload = payload or IntradaySignalRequest()
    return _safe(engine_loader.intraday_signal, payload.symbol, payload.limit)


@app.post("/intraday_signals")
def intraday_signals(payload: Optional[IntradaySignalRequest] = None) -> dict[str, Any]:
    return intraday_signal(payload)


@app.post("/moneyflow/anomaly")
def moneyflow_anomaly(payload: Optional[MoneyFlowRequest] = None) -> dict[str, Any]:
    payload = payload or MoneyFlowRequest()
    return _safe(engine_loader.moneyflow_anomaly, payload.symbol, payload.limit)


@app.post("/money_flow_anomalies")
def money_flow_anomalies(payload: Optional[MoneyFlowRequest] = None) -> dict[str, Any]:
    return moneyflow_anomaly(payload)
=======
    return get_market_overview()


@app.post("/intraday_signals")
def intraday_signals() -> dict[str, Any]:
    watchlist = scan_full_market_top10(limit=10)
    return {"signals": scan_intraday_signals(watchlist), "cache_ttl": 60, "watchlist_size": len(watchlist)}


@app.post("/money_flow_anomalies")
def money_flow_anomalies() -> dict[str, Any]:
    watchlist = scan_full_market_top10(limit=10)
    return {"anomalies": scan_money_flow_anomalies(watchlist), "cache_ttl": 60, "watchlist_size": len(watchlist)}
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b


@app.post("/backtest_strategy")
def backtest_strategy(payload: BacktestRequest) -> dict[str, Any]:
<<<<<<< HEAD
    return _safe(
        engine_loader.backtest_strategy,
        payload.symbol,
        payload.short_window,
        payload.long_window,
        payload.days,
    )
=======
    try:
        return backtest_engine.run_backtest(
            normalize_symbol(payload.symbol),
            short_window=payload.short_window,
            long_window=payload.long_window,
            days=payload.days,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"backtest_strategy failed: {exc}") from exc
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b
