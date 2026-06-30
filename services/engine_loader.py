from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from typing import Any, Callable


def safe_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return {"success": True, "data": func(*args, **kwargs), "error": ""}
    except Exception as exc:
        return {"success": False, "data": {}, "error": str(exc)}


@lru_cache(maxsize=1)
def _provider_module() -> Any:
    return import_module("data.provider")


@lru_cache(maxsize=1)
def get_provider() -> Any:
    return _provider_module().MarketDataProvider()


@lru_cache(maxsize=1)
def get_app_logic() -> Any:
    return import_module("app")


@lru_cache(maxsize=1)
def get_scanner_engine() -> Any:
    return import_module("full_market_scanner")


@lru_cache(maxsize=1)
def get_intraday_engine() -> Any:
    return import_module("intraday_signal_engine")


@lru_cache(maxsize=1)
def get_money_flow_engine() -> Any:
    return import_module("money_flow_anomaly_detector")


@lru_cache(maxsize=1)
def get_market_service() -> Any:
    return import_module("market_overview_service")


@lru_cache(maxsize=1)
def get_backtest_engine() -> Any:
    return import_module("engine_layer.backtest_engine")


def normalize_symbol(symbol: str) -> str:
    return _provider_module().normalize_symbol(symbol)


def search_stock(keyword: str) -> list[dict[str, str]]:
    return get_provider().search_stock(keyword or "")


def analyze_stock(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    return get_app_logic().analyze_one(normalized)


def stock_detail(symbol: str) -> dict[str, Any]:
    result = analyze_stock(symbol)
    return {
        "symbol": result.get("symbol"),
        "name": result.get("name"),
        "price": result.get("price"),
        "technical_analysis": result.get("technical_analysis", {}),
        "fund_flow_analysis": result.get("fund_flow_analysis", {}),
        "fundamental_analysis": result.get("fundamental_analysis", {}),
        "sentiment_analysis": result.get("sentiment_analysis", {}),
        "final_reason": result.get("final_reason", ""),
    }


def scan_top10(limit: int = 10) -> list[dict[str, Any]]:
    return get_scanner_engine().scan_full_market_top10(limit=max(1, min(int(limit or 10), 50)))


def market_overview() -> dict[str, Any]:
    return get_market_service().get_market_overview()


def intraday_signal(symbol: str | None = None, limit: int = 10) -> dict[str, Any]:
    engine = get_intraday_engine()
    if symbol:
        row = engine.generate_intraday_signal(normalize_symbol(symbol))
        return {"signals": [_normalize_signal(row)], "cache_ttl": 60, "watchlist_size": 1}

    watchlist = scan_top10(limit=limit)
    rows = engine.scan_intraday_signals(watchlist)
    return {"signals": [_normalize_signal(row) for row in rows], "cache_ttl": 60, "watchlist_size": len(watchlist)}


def moneyflow_anomaly(symbol: str | None = None, limit: int = 10) -> dict[str, Any]:
    engine = get_money_flow_engine()
    if symbol:
        rows = [engine.detect_money_flow_anomaly(normalize_symbol(symbol))]
        watchlist_size = 1
    else:
        watchlist = scan_top10(limit=limit)
        rows = engine.scan_money_flow_anomalies(watchlist)
        watchlist_size = len(watchlist)

    abnormal_rows = [dict(row) for row in rows if row.get("intensity") in {"HIGH", "MEDIUM"} or row.get("action_signal") != "WATCH"]
    inflow = sorted(rows, key=lambda row: float(row.get("money_flow_change") or 0), reverse=True)[:10]
    outflow = sorted(rows, key=lambda row: float(row.get("money_flow_change") or 0))[:10]
    detection_score = _detection_score(rows)
    return {
        "abnormal_stocks": abnormal_rows,
        "anomalies": rows,
        "inflow_ranking": inflow,
        "outflow_ranking": outflow,
        "detection_score": detection_score,
        "cache_ttl": 60,
        "watchlist_size": watchlist_size,
    }


def backtest_strategy(symbol: str, short_window: int = 5, long_window: int = 20, days: int = 180) -> dict[str, Any]:
    return get_backtest_engine().run_backtest(
        normalize_symbol(symbol),
        short_window=short_window,
        long_window=long_window,
        days=days,
    )


def _normalize_signal(row: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(row.get("signal_type") or "WATCH")
    action_type = "BUY" if raw_type in {"BREAKOUT", "ACCUMULATION"} else "SELL" if raw_type in {"DISTRIBUTION", "PANIC SELL"} else "HOLD"
    reasons = row.get("trigger_reason") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    return {
        **row,
        "raw_signal_type": raw_type,
        "signal_type": action_type,
        "reason": "；".join(str(item) for item in reasons) or "未触发强盘中模式，保持观察",
        "timestamp": row.get("quote_time"),
    }


def _detection_score(rows: list[dict[str, Any]]) -> float:
    weights = {"HIGH": 90.0, "MEDIUM": 65.0, "LOW": 35.0}
    if not rows:
        return 0.0
    return round(max(weights.get(str(row.get("intensity")), 0.0) for row in rows), 2)
