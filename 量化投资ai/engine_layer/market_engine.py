from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests

from data.provider import DataProviderError, MarketDataProvider


provider = MarketDataProvider()


INDEXES = {
    "上证指数": "1.000001",
    "创业板指": "0.399006",
}


def market_overview() -> dict[str, Any]:
    indexes = []
    errors = []
    for name, secid in INDEXES.items():
        try:
            indexes.append(_index_trend(name, secid))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    if not indexes:
        raise DataProviderError("; ".join(errors) or "market index data unavailable")
    avg_change = float(np.mean([item["change_pct"] for item in indexes if item.get("change_pct") is not None]))
    trend_score = float(np.mean([item["trend_score"] for item in indexes]))
    sentiment_index = round(float(np.clip(50 + avg_change * 5 + (trend_score - 50) * 0.4, 0, 100)), 2)
    risk_preference = "Risk On" if sentiment_index >= 60 else "Risk Off" if sentiment_index < 45 else "Neutral"
    sectors = _sector_rotation()
    return {
        "indexes": indexes,
        "market_sentiment_index": sentiment_index,
        "risk_preference": risk_preference,
        "sector_rotation": sectors,
        "errors": errors,
        "data_source": "REAL_INDEX_KLINE",
    }


def _index_trend(name: str, secid: str) -> dict[str, Any]:
    bars = _eastmoney_index_daily(secid)
    latest = bars.tail(1).iloc[0]
    close = bars["close"]
    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    trend = "UP" if ma5 > ma20 else "DOWN" if ma5 < ma20 else "SIDEWAYS"
    trend_score = 65 if trend == "UP" else 35 if trend == "DOWN" else 50
    return {
        "name": name,
        "close": round(float(latest["close"]), 2),
        "change_pct": round(float(latest["change_pct"]), 2),
        "ma5": round(float(ma5), 2),
        "ma20": round(float(ma20), 2),
        "trend": trend,
        "trend_score": trend_score,
        "date": latest["date"].strftime("%Y-%m-%d"),
    }


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
    response = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get", params=params, timeout=provider.timeout)
    response.raise_for_status()
    klines = (response.json().get("data") or {}).get("klines") or []
    rows = []
    for item in klines:
        parts = item.split(",")
        if len(parts) >= 9:
            rows.append({"date": parts[0], "open": parts[1], "close": parts[2], "high": parts[3], "low": parts[4], "volume": parts[5], "amount": parts[6], "change_pct": parts[8]})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise DataProviderError(f"index bars empty: {secid}")
    for col in ["open", "close", "high", "low", "volume", "amount", "change_pct"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").tail(days).reset_index(drop=True)


def _sector_rotation(limit: int = 10) -> dict[str, Any]:
    try:
        import akshare as ak

        frame = ak.stock_board_industry_name_em()
        if frame is None or frame.empty:
            raise DataProviderError("sector board data empty")
        name_col = "板块名称" if "板块名称" in frame.columns else "名称"
        change_col = "涨跌幅" if "涨跌幅" in frame.columns else None
        flow_col = "主力净流入" if "主力净流入" in frame.columns else None
        if not name_col or not change_col:
            raise DataProviderError(f"unsupported sector schema: {list(frame.columns)}")
        frame = frame.copy()
        frame[change_col] = pd.to_numeric(frame[change_col], errors="coerce")
        if flow_col:
            frame[flow_col] = pd.to_numeric(frame[flow_col], errors="coerce")
        rows = []
        for _, row in frame.sort_values(change_col, ascending=False).head(limit).iterrows():
            rows.append({"name": str(row.get(name_col)), "change_pct": row.get(change_col), "main_flow": row.get(flow_col) if flow_col else None})
        return {"hot_sectors": rows, "data_source": "AKSHARE_INDUSTRY_BOARD"}
    except Exception as exc:
        return {"hot_sectors": [], "error": f"sector rotation unavailable: {exc}", "data_source": "AKSHARE_INDUSTRY_BOARD"}
