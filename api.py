from __future__ import annotations

from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


class WeComTestRequest(BaseModel):
    text: str


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


@app.get("/wecom/callback")
def wecom_callback_verify(
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
) -> Response:
    from services import wecom_service

    try:
        if not wecom_service.verify_signature(msg_signature, timestamp, nonce, echostr):
            return Response("invalid signature", status_code=403, media_type="text/plain")
        plain = wecom_service.verify_url(echostr)
        return Response(plain, media_type="text/plain")
    except Exception as exc:
        return Response(f"wecom verify failed: {exc}", status_code=500, media_type="text/plain")


@app.post("/wecom/callback")
async def wecom_callback_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
) -> Response:
    from services import wecom_service

    try:
        raw_body = await request.body()
        encrypted = wecom_service.extract_encrypt(raw_body)
        if encrypted and not wecom_service.verify_signature(msg_signature, timestamp, nonce, encrypted):
            return Response("invalid signature", status_code=403, media_type="text/plain")
        message = wecom_service.parse_callback_xml(raw_body)
        if not message.content:
            reply = wecom_service.HELP_TEXT
            return Response(wecom_service.build_passive_text_response(message, reply), media_type="application/xml")

        if wecom_service.has_group_webhook():
            background_tasks.add_task(wecom_service.build_async_and_push, message.content)
            reply = "正在分析，请稍等。"
        else:
            reply = wecom_service.build_reply_for_text(message.content)
        return Response(wecom_service.build_passive_text_response(message, reply), media_type="application/xml")
    except Exception as exc:
        fallback = f"分析失败，可能是数据源暂时不可用，请稍后再试。\n错误：{exc}"
        return Response(fallback, status_code=200, media_type="text/plain")


@app.post("/wecom/test")
def wecom_test(payload: WeComTestRequest) -> dict[str, Any]:
    from services import wecom_service

    return _safe(wecom_service.test_command, payload.text)


@app.post("/feishu/callback")
async def feishu_callback(request: Request) -> JSONResponse:
    body = await request.json()
    print("Feishu callback received:", body, flush=True)

    challenge = body.get("challenge")
    event = body.get("event")
    if not challenge and isinstance(event, dict):
        challenge = event.get("challenge")

    header = body.get("header")
    event_type = body.get("type")
    if not event_type and isinstance(header, dict):
        event_type = header.get("event_type")

    if event_type == "url_verification" or challenge:
        return JSONResponse({"challenge": challenge})

    return JSONResponse({"code": 0, "msg": "ok"})
