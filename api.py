from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services import engine_loader


app = FastAPI(title="A股AI量化分析API", version="5.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    keyword: Optional[str] = None
    q: Optional[str] = None


class SymbolRequest(BaseModel):
    symbol: str


class LimitRequest(BaseModel):
    limit: int = 10


class IntradaySignalRequest(BaseModel):
    symbol: Optional[str] = None
    limit: int = 10


class MoneyFlowRequest(BaseModel):
    symbol: Optional[str] = None
    limit: int = 10


class BacktestRequest(BaseModel):
    symbol: str = "300394"
    short_window: int = 5
    long_window: int = 20
    days: int = 180


class PortfolioAnalyzeRequest(BaseModel):
    symbol: str
    cost_price: float
    shares: int
    available_cash: float = 0
    max_position_ratio: float = 0.3
    risk_preference: str = "稳健"


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


@app.post("/analyze_stock")
def analyze_stock(payload: SymbolRequest) -> dict[str, Any]:
    return _safe(engine_loader.analyze_stock, payload.symbol)


@app.post("/analyze")
def analyze_alias(payload: SymbolRequest) -> dict[str, Any]:
    return analyze_stock(payload)


@app.post("/screen_stocks")
def screen_stocks(payload: Optional[LimitRequest] = None) -> dict[str, Any]:
    limit = payload.limit if payload else 10
    return _safe(engine_loader.scan_top10, limit)


@app.post("/top10")
def top10_alias(payload: Optional[LimitRequest] = None) -> dict[str, Any]:
    return screen_stocks(payload)


@app.get("/scan/top10")
def scan_top10(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    return _safe(engine_loader.scan_top10, limit)


@app.get("/stock_detail")
def stock_detail(symbol: str = Query(...)) -> dict[str, Any]:
    return _safe(engine_loader.stock_detail, symbol)


@app.post("/market_overview")
def market_overview() -> dict[str, Any]:
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


@app.post("/backtest_strategy")
def backtest_strategy(payload: BacktestRequest) -> dict[str, Any]:
    return _safe(
        engine_loader.backtest_strategy,
        payload.symbol,
        payload.short_window,
        payload.long_window,
        payload.days,
    )


@app.post("/portfolio/analyze")
def portfolio_analyze(payload: PortfolioAnalyzeRequest) -> dict[str, Any]:
    return _safe(
        engine_loader.portfolio_analyze,
        payload.symbol,
        payload.cost_price,
        payload.shares,
        payload.available_cash,
        payload.max_position_ratio,
        payload.risk_preference,
    )
