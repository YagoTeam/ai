from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests

from data.provider import DataProviderError


MARKET_CACHE: dict[str, Any] = {"timestamp": 0.0, "data": None}
MARKET_CACHE_TTL = 300
INDEXES = {"上证指数": "1.000001", "创业板指": "0.399006"}


def get_market_overview() -> dict[str, Any]:
    cached = _cached()
    if cached:
        cached["status"] = "CACHE"
        return cached
    errors: list[str] = []
    try:
        indexes = [_index_trend(name, secid) for name, secid in INDEXES.items()]
        sectors = _hot_sectors()
        result = _build_response(indexes, sectors, "REAL", errors)
        _set_cache(result)
        return result
    except Exception as exc:
        errors.append(str(exc))

    result = _build_response(_fallback_indexes(), [], "FALLBACK", errors)
    _set_cache(result)
    return result


def _cached() -> dict[str, Any] | None:
    data = MARKET_CACHE.get("data")
    if data and time.time() - float(MARKET_CACHE.get("timestamp", 0)) < MARKET_CACHE_TTL:
        return dict(data)
    return None


def _set_cache(data: dict[str, Any]) -> None:
    MARKET_CACHE["timestamp"] = time.time()
    MARKET_CACHE["data"] = dict(data)


def _index_trend(name: str, secid: str) -> dict[str, Any]:
    bars = _eastmoney_index_daily(secid)
    return _trend_from_bars(name, bars)


def _eastmoney_index_daily(secid: str, days: int = 80) -> pd.DataFrame:
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=days * 2)).strftime("%Y%m%d")
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59",
        "klt": "101",
        "fqt": "1",
        "beg": start,
        "end": end,
    }
    last_exc: Exception | None = None
    for _ in range(1):
        try:
            response = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get", params=params, timeout=3)
            response.raise_for_status()
            klines = (response.json().get("data") or {}).get("klines") or []
            return _klines_to_frame(klines, days)
        except Exception as exc:
            last_exc = exc
            time.sleep(0.2)
    raise DataProviderError(f"Eastmoney index failed: {last_exc}")


def _klines_to_frame(klines: list[str], days: int) -> pd.DataFrame:
    rows = []
    for item in klines:
        parts = item.split(",")
        if len(parts) >= 9:
            rows.append({"date": parts[0], "open": parts[1], "close": parts[2], "high": parts[3], "low": parts[4], "volume": parts[5], "amount": parts[6], "change_pct": parts[8]})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise DataProviderError("index bars empty")
    for col in ["open", "close", "high", "low", "volume", "amount", "change_pct"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").tail(days).reset_index(drop=True)


def _akshare_index_trend(name: str) -> dict[str, Any]:
    import akshare as ak

    symbol = "sh000001" if name == "上证指数" else "sz399006"
    frame = ak.stock_zh_index_daily(symbol=symbol)
    if frame is None or frame.empty:
        raise DataProviderError(f"AkShare index empty: {name}")
    frame = frame.rename(columns={"日期": "date", "收盘": "close", "涨跌幅": "change_pct"}).copy()
    if "date" not in frame.columns:
        frame["date"] = pd.to_datetime(frame.index)
    if "change_pct" not in frame.columns:
        frame["change_pct"] = pd.to_numeric(frame["close"], errors="coerce").pct_change() * 100
    frame["date"] = pd.to_datetime(frame["date"])
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["change_pct"] = pd.to_numeric(frame["change_pct"], errors="coerce")
    return _trend_from_bars(name, frame.tail(80).reset_index(drop=True))


def _trend_from_bars(name: str, bars: pd.DataFrame) -> dict[str, Any]:
    latest = bars.tail(1).iloc[0]
    close = bars["close"].astype(float)
    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    trend = "UP" if ma5 > ma20 else "DOWN" if ma5 < ma20 else "SIDEWAYS"
    return {
        "name": name,
        "close": round(float(latest["close"]), 2),
        "change_pct": round(float(latest["change_pct"]), 2),
        "ma5": round(float(ma5), 2),
        "ma20": round(float(ma20), 2),
        "trend": trend,
        "date": latest["date"].strftime("%Y-%m-%d"),
    }


def _hot_sectors(limit: int = 10) -> list[dict[str, Any]]:
    params = {
        "pn": 1,
        "pz": max(limit, 10),
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:90+t:2",
        "fields": "f12,f14,f3,f62",
    }
    for _ in range(1):
        try:
            response = requests.get("https://push2.eastmoney.com/api/qt/clist/get", params=params, timeout=3)
            response.raise_for_status()
            rows = (response.json().get("data") or {}).get("diff") or []
            return [
                {
                    "code": str(row.get("f12") or ""),
                    "name": str(row.get("f14") or ""),
                    "change_pct": _num(row.get("f3")),
                    "main_flow": _num(row.get("f62")),
                }
                for row in rows[:limit]
                if row.get("f14")
            ]
        except Exception:
            time.sleep(0.2)
    return []


def _build_response(indexes: list[dict[str, Any]], hot_sectors: list[dict[str, Any]], status: str, errors: list[str]) -> dict[str, Any]:
    avg_change = float(np.mean([item.get("change_pct") or 0 for item in indexes])) if indexes else 0.0
    up_count = sum(item.get("trend") == "UP" for item in indexes)
    sentiment_score = round(float(np.clip(50 + avg_change * 5 + (up_count - 1) * 10, 0, 100)), 2)
    market_sentiment = "BULLISH" if sentiment_score >= 60 else "BEARISH" if sentiment_score < 45 else "NEUTRAL"
    risk_appetite = "Risk On" if sentiment_score >= 60 else "Risk Off" if sentiment_score < 45 else "Neutral"
    index_trend = " / ".join(f"{item['name']}:{item['trend']}" for item in indexes) or "UNKNOWN"
    return {
        "market_sentiment": market_sentiment,
        "market_sentiment_index": sentiment_score,
        "risk_appetite": risk_appetite,
        "risk_preference": risk_appetite,
        "index_trend": index_trend,
        "indexes": indexes,
        "hot_sectors": hot_sectors,
        "sector_rotation": {"hot_sectors": hot_sectors},
        "status": status,
        "errors": errors,
    }


def _fallback_indexes() -> list[dict[str, Any]]:
    return [
        {"name": "上证指数", "close": None, "change_pct": 0.0, "ma5": None, "ma20": None, "trend": "SIDEWAYS", "date": date.today().strftime("%Y-%m-%d")},
        {"name": "创业板指", "close": None, "change_pct": 0.0, "ma5": None, "ma20": None, "trend": "SIDEWAYS", "date": date.today().strftime("%Y-%m-%d")},
    ]


def _num(value: Any) -> float | None:
    try:
        if pd.isna(value) or value in {"-", ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
