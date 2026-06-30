from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from data.provider import MarketDataProvider, normalize_symbol


_PROVIDER: MarketDataProvider | None = None
SIGNAL_CACHE: dict[str, Any] = {"timestamp": 0.0, "rows": []}
SIGNAL_CACHE_TTL = 60


def _provider() -> MarketDataProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = MarketDataProvider()
    return _PROVIDER


def scan_intraday_signals(watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if SIGNAL_CACHE["rows"] and time.time() - float(SIGNAL_CACHE["timestamp"]) <= SIGNAL_CACHE_TTL:
        return [dict(row) for row in SIGNAL_CACHE["rows"]]
    rows = []
    for item in watchlist:
        symbol = normalize_symbol(item.get("symbol") or item.get("code") or "")
        try:
            rows.append(generate_intraday_signal(symbol, float(item.get("score") or 50), item.get("risk_level", "MEDIUM")))
        except Exception:
            continue
    rows.sort(key=lambda row: row["signal_strength"], reverse=True)
    SIGNAL_CACHE.update({"timestamp": time.time(), "rows": [dict(row) for row in rows]})
    return rows


def generate_intraday_signal(symbol: str, v4_score: float = 50.0, base_risk: str = "MEDIUM") -> dict[str, Any]:
    provider = _provider()
    quote = provider.get_realtime_quote(symbol)
    bars = provider.get_daily_bars(symbol, days=60)
    features = _features(quote, bars)
    signal_type, strength, reasons = _classify(features)
    intraday_score = round(float(strength), 2)
    final_strength = round(float(np.clip(v4_score * 0.7 + intraday_score * 0.3, 0, 100)), 2)
    confidence = round(float(np.clip(0.45 + len(reasons) * 0.12 + abs(features["change_pct"]) / 100, 0.45, 0.95)), 2)
    risk_level = _risk_level(base_risk, features, signal_type)
    return {
        "symbol": normalize_symbol(symbol),
        "signal_type": signal_type,
        "signal_strength": final_strength,
        "v4_score": round(float(v4_score), 2),
        "intraday_score": intraday_score,
        "final_score": final_strength,
        "confidence": confidence,
        "trigger_reason": reasons,
        "timeframe": "5m",
        "risk_level": risk_level,
        "quote_time": int(time.time()),
    }


def _features(quote: dict[str, Any], bars: pd.DataFrame) -> dict[str, float]:
    close = bars["close"].astype(float)
    volume = bars["volume"].astype(float)
    price = _num(quote.get("price")) or float(close.iloc[-1])
    change_pct = _num(quote.get("change_pct")) or 0.0
    current_volume = _num(quote.get("volume")) or float(volume.iloc[-1])
    current_amount = _num(quote.get("amount")) or price * current_volume
    ma20 = float(close.rolling(20).mean().iloc[-1])
    prev_high = float(close.tail(20).max())
    avg_volume = float(volume.tail(20).mean())
    rsi = _rsi(close).iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    amount_direction = 1 if change_pct > 0 else -1 if change_pct < 0 else 0
    money_flow_proxy = current_amount * amount_direction
    volatility = float(close.pct_change().tail(10).std() or 0)
    return {
        "price": price,
        "change_pct": change_pct,
        "volume_ratio": volume_ratio,
        "money_flow_proxy": money_flow_proxy,
        "ma20": ma20,
        "prev_high": prev_high,
        "rsi": float(rsi),
        "volatility": volatility,
    }


def _classify(f: dict[str, float]) -> tuple[str, float, list[str]]:
    reasons: list[str] = []
    if f["price"] > f["ma20"] and f["price"] >= f["prev_high"] * 0.995 and f["volume_ratio"] > 1.5 and f["money_flow_proxy"] > 0:
        reasons.extend(["价格突破MA20或前高", "成交量放大超过1.5倍均值", "资金流向为净流入代理"])
        return "BREAKOUT", 88.0, reasons
    if abs(f["change_pct"]) < 1.5 and f["volume_ratio"] < 0.9 and f["money_flow_proxy"] > 0 and f["volatility"] < 0.035:
        reasons.extend(["横盘缩量", "资金小幅流入代理", "短期波动率下降"])
        return "ACCUMULATION", 72.0, reasons
    if f["volume_ratio"] > 1.3 and abs(f["change_pct"]) < 1.2 and f["money_flow_proxy"] < 0 and f["rsi"] > 70:
        reasons.extend(["高位放量滞涨", "资金流向为流出代理", "RSI超过70"])
        return "DISTRIBUTION", 78.0, reasons
    if f["change_pct"] < -5 and f["volume_ratio"] > 1.5 and f["money_flow_proxy"] < 0:
        reasons.extend(["急跌超过5%", "成交量暴增", "超大单流出代理为负"])
        return "PANIC SELL", 90.0, reasons
    reasons.append("未触发强盘中模式，保持观察")
    return "WATCH", 50.0, reasons


def _risk_level(base: str, f: dict[str, float], signal_type: str) -> str:
    if signal_type in {"PANIC SELL", "DISTRIBUTION"} or abs(f["change_pct"]) >= 7:
        return "HIGH"
    if base == "LOW" and signal_type in {"BREAKOUT", "ACCUMULATION"}:
        return "LOW"
    return "MEDIUM"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
