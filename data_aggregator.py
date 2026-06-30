from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from data.provider import DataProviderError, MarketDataProvider, normalize_symbol, symbol_to_ak, symbol_to_market


provider = MarketDataProvider()


def get_full_stock_data(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    price_data = _get_price_data(normalized)
    technical_data = _get_technical_data(normalized)
    fund_flow_data = _get_fund_flow_data(normalized)
    fundamental_data = _get_fundamental_data(normalized, price_data)
    sentiment_data = _get_sentiment_data(normalized)
    return {
        "symbol": normalized,
        "price_data": price_data,
        "technical_data": technical_data,
        "fund_flow_data": fund_flow_data,
        "fundamental_data": fundamental_data,
        "sentiment_data": sentiment_data,
    }


def _get_price_data(symbol: str) -> dict[str, Any]:
    try:
        quote = provider.get_realtime_quote(symbol)
        return {
            "status": "OK",
            "source": "Tencent real quote API",
            "symbol": symbol,
            "name": quote.get("name") or symbol,
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
            "volume": quote.get("volume"),
            "amount": quote.get("amount"),
            "market_cap": quote.get("market_cap"),
            "pe": quote.get("pe"),
            "pb": quote.get("pb"),
        }
    except Exception as exc:
        return {
            "status": "NO_DATA",
            "source": "quote",
            "symbol": symbol,
            "name": symbol,
            "price": None,
            "change_pct": None,
            "volume": None,
            "message": f"price unavailable: {exc}",
        }


def _get_akshare_daily_bars(symbol: str, days: int = 180) -> pd.DataFrame:
    if os.getenv("MARKET_ENABLE_AK_KLINE") != "1":
        raise DataProviderError("AkShare K-line disabled in current runtime; set MARKET_ENABLE_AK_KLINE=1 to force it")
    import akshare as ak

    start = (date.today() - timedelta(days=max(days * 2, 120))).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    frame = ak.stock_zh_a_hist(symbol=symbol_to_ak(symbol), period="daily", start_date=start, end_date=end, adjust="qfq")
    if frame is None or frame.empty:
        raise DataProviderError("AkShare K-line returned empty data")
    frame = frame.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "change_pct",
        }
    ).copy()
    required = ["date", "open", "close", "high", "low", "volume"]
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise DataProviderError(f"AkShare K-line missing columns: {missing}")
    if "amount" not in frame.columns:
        frame["amount"] = pd.NA
    if "change_pct" not in frame.columns:
        frame["change_pct"] = pd.NA
    frame["code"] = symbol
    for col in ["open", "close", "high", "low", "volume", "amount", "change_pct"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").tail(days).reset_index(drop=True)


def _get_technical_data(symbol: str) -> dict[str, Any]:
    source = "AkShare K-line"
    status = "OK"
    message = ""
    try:
        bars = _get_akshare_daily_bars(symbol)
    except Exception as exc:
        try:
            bars = provider.get_daily_bars(symbol, days=180)
            source = "Tencent real K-line API"
            status = "FALLBACK"
            message = f"AkShare K-line unavailable: {exc}; Tencent real K-line used"
        except Exception as fallback_exc:
            return {
                "status": "NO_DATA",
                "source": "AkShare K-line",
                "message": f"technical data unavailable: {exc}; fallback failed: {fallback_exc}",
                "bars": [],
            }

    indicators = _calculate_technical_indicators(bars)
    return {
        "status": status,
        "source": source,
        "message": message,
        "bars": _bars_to_records(bars),
        **indicators,
    }


def _calculate_technical_indicators(bars: pd.DataFrame) -> dict[str, Any]:
    frame = bars.copy().sort_values("date")
    close = frame["close"]
    frame["ma5"] = close.rolling(5).mean()
    frame["ma20"] = close.rolling(20).mean()
    frame["ma60"] = close.rolling(60).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    frame["macd_dif"] = ema12 - ema26
    frame["macd_dea"] = frame["macd_dif"].ewm(span=9, adjust=False).mean()
    frame["macd"] = (frame["macd_dif"] - frame["macd_dea"]) * 2
    frame["rsi"] = _rsi(close)
    frame["volume_change"] = frame["volume"] / frame["volume"].rolling(20).mean() - 1
    latest = frame.tail(1).iloc[0]
    trend = "UP" if latest["ma5"] > latest["ma20"] > latest["ma60"] and latest["macd"] > 0 else "DOWN" if latest["ma5"] < latest["ma20"] < latest["ma60"] and latest["macd"] < 0 else "SIDEWAYS"
    return {
        "ma5": _num(latest["ma5"]),
        "ma20": _num(latest["ma20"]),
        "ma60": _num(latest["ma60"]),
        "macd": {"dif": _num(latest["macd_dif"]), "dea": _num(latest["macd_dea"]), "hist": _num(latest["macd"])},
        "rsi": _num(latest["rsi"]),
        "volume": _num(latest["volume"]),
        "volume_change": _num(latest["volume_change"]),
        "trend": trend,
    }


def _get_fund_flow_data(symbol: str) -> dict[str, Any]:
    if os.getenv("MARKET_ENABLE_AK_FUNDS") != "1":
        return {"status": "NO_DATA", "source": "AkShare fund flow", "message": "fund flow unavailable", "main_flow": None, "large_order": None, "super_order": None}
    try:
        import akshare as ak

        frame = ak.stock_individual_fund_flow(stock=symbol_to_ak(symbol), market=symbol_to_market(symbol))
        if frame is None or frame.empty:
            raise DataProviderError("empty fund flow")
        latest = frame.tail(1).iloc[0]
        return {
            "status": "OK",
            "source": "AkShare fund flow",
            "message": "",
            "main_flow": _to_float(latest.get("主力净流入-净额")),
            "large_order": _to_float(latest.get("大单净流入-净额")),
            "super_order": _to_float(latest.get("超大单净流入-净额")),
        }
    except Exception as exc:
        return {"status": "NO_DATA", "source": "AkShare fund flow", "message": f"fund flow unavailable: {exc}", "main_flow": None, "large_order": None, "super_order": None}


def _get_fundamental_data(symbol: str, price_data: dict[str, Any]) -> dict[str, Any]:
    tushare_data = _get_tushare_fundamental(symbol)
    akshare_data = _get_akshare_fundamental(symbol)
    merged = {
        "pe": tushare_data.get("pe") if tushare_data.get("pe") is not None else akshare_data.get("pe"),
        "pb": tushare_data.get("pb") if tushare_data.get("pb") is not None else akshare_data.get("pb"),
        "roe": tushare_data.get("roe") if tushare_data.get("roe") is not None else akshare_data.get("roe"),
        "revenue_growth": tushare_data.get("revenue_growth") if tushare_data.get("revenue_growth") is not None else akshare_data.get("revenue_growth"),
    }
    if any(value is not None for value in merged.values()):
        return {"status": "OK", "source": "Tushare/AkShare financial data", "message": "", **merged}
    return {"status": "NO_DATA", "source": "Tushare/AkShare financial data", "message": "fundamental data unavailable", **merged}


def _get_tushare_fundamental(symbol: str) -> dict[str, float | None]:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        return {"pe": None, "pb": None, "roe": None, "revenue_growth": None}
    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        daily = pro.daily_basic(ts_code=normalize_symbol(symbol), limit=1, fields="ts_code,pe,pb")
        indicator = pro.fina_indicator(ts_code=normalize_symbol(symbol), limit=1, fields="ts_code,roe,or_yoy")
        result = {"pe": None, "pb": None, "roe": None, "revenue_growth": None}
        if daily is not None and not daily.empty:
            row = daily.iloc[0]
            result["pe"] = _to_float(row.get("pe"))
            result["pb"] = _to_float(row.get("pb"))
        if indicator is not None and not indicator.empty:
            row = indicator.iloc[0]
            result["roe"] = _to_float(row.get("roe"))
            result["revenue_growth"] = _to_float(row.get("or_yoy"))
        return result
    except Exception:
        return {"pe": None, "pb": None, "roe": None, "revenue_growth": None}


def _get_akshare_fundamental(symbol: str) -> dict[str, float | None]:
    if os.getenv("MARKET_ENABLE_AK_FINANCIALS") != "1":
        return {"pe": None, "pb": None, "roe": None, "revenue_growth": None}
    result = {"pe": None, "pb": None, "roe": None, "revenue_growth": None}
    try:
        import akshare as ak

        info = ak.stock_individual_info_em(symbol=symbol_to_ak(symbol))
        if info is not None and not info.empty and {"item", "value"}.issubset(info.columns):
            values = dict(zip(info["item"], info["value"]))
            result["pe"] = _to_float(values.get("市盈率-动态") or values.get("市盈率"))
            result["pb"] = _to_float(values.get("市净率"))
        abstract = ak.stock_financial_abstract_ths(symbol=symbol_to_ak(symbol), indicator="按年度")
        _merge_financial_abstract(result, abstract)
    except Exception:
        return result
    return result


def _get_sentiment_data(symbol: str) -> dict[str, Any]:
    try:
        news = provider.get_news(symbol)
    except Exception as exc:
        return {"status": "FALLBACK", "sentiment": "NEUTRAL", "confidence": 0.3, "message": f"news unavailable: {exc}", "headlines": []}
    if not news:
        return {"status": "FALLBACK", "sentiment": "NEUTRAL", "confidence": 0.3, "message": "news unavailable", "headlines": []}
    positive = ["增长", "中标", "突破", "回购", "增持", "盈利", "改善", "上调", "创新高", "政策支持"]
    negative = ["处罚", "调查", "减持", "亏损", "召回", "违约", "下滑", "风险", "问询", "退市"]
    pos = sum(any(word in item for word in positive) for item in news)
    neg = sum(any(word in item for word in negative) for item in news)
    sentiment = "POSITIVE" if pos > neg else "NEGATIVE" if neg > pos else "NEUTRAL"
    confidence = min(0.95, max(0.35, abs(pos - neg) / max(len(news), 1) + 0.35))
    return {
        "status": "OK",
        "sentiment": sentiment,
        "confidence": round(float(confidence), 2),
        "message": f"news_count={len(news)}, positive_hits={pos}, negative_hits={neg}",
        "headlines": news[:5],
    }


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _bars_to_records(bars: pd.DataFrame) -> list[dict[str, Any]]:
    frame = bars.tail(180).copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    return frame.replace({np.nan: None}).to_dict(orient="records")


def _merge_financial_abstract(result: dict[str, float | None], frame: pd.DataFrame | None) -> None:
    if frame is None or frame.empty:
        return
    text_cols = [col for col in frame.columns if str(col) in {"指标", "项目", "报告期"}]
    value_cols = [col for col in frame.columns if col not in text_cols]
    for _, row in frame.iterrows():
        label = " ".join(str(row.get(col, "")) for col in text_cols)
        latest = next((_to_float(row.get(col)) for col in value_cols if _to_float(row.get(col)) is not None), None)
        if latest is None:
            continue
        if result["roe"] is None and ("净资产收益率" in label or "ROE" in label.upper()):
            result["roe"] = latest
        if result["revenue_growth"] is None and ("营业总收入同比增长率" in label or "营业收入同比增长率" in label):
            result["revenue_growth"] = latest


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = pd.to_numeric(value, errors="coerce")
        if pd.isna(parsed):
            return None
        parsed = float(parsed)
        if parsed == -1:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    parsed = _to_float(value)
    return round(parsed, 4) if parsed is not None else None
