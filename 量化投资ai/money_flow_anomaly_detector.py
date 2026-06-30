from __future__ import annotations

import time
from typing import Any

import numpy as np

from data.provider import MarketDataProvider, normalize_symbol


provider = MarketDataProvider()
SNAPSHOT_CACHE: dict[str, dict[str, Any]] = {}
ANOMALY_CACHE: dict[str, Any] = {"timestamp": 0.0, "rows": []}
ANOMALY_CACHE_TTL = 60


def scan_money_flow_anomalies(watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if ANOMALY_CACHE["rows"] and time.time() - float(ANOMALY_CACHE["timestamp"]) <= ANOMALY_CACHE_TTL:
        return [dict(row) for row in ANOMALY_CACHE["rows"]]
    rows = []
    for item in watchlist:
        symbol = normalize_symbol(item.get("symbol") or item.get("code") or "")
        try:
            rows.append(detect_money_flow_anomaly(symbol))
        except Exception:
            continue
    rows.sort(key=lambda row: {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(row["intensity"], 0), reverse=True)
    ANOMALY_CACHE.update({"timestamp": time.time(), "rows": [dict(row) for row in rows]})
    return rows


def detect_money_flow_anomaly(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    quote = provider.get_realtime_quote(normalized)
    now_snapshot = _snapshot(quote)
    prev = SNAPSHOT_CACHE.get(normalized)
    SNAPSHOT_CACHE[normalized] = now_snapshot
    change = _money_flow_change(prev, now_snapshot)
    volume_spike = _volume_spike(prev, now_snapshot)
    anomaly_type, intensity, interpretation, action = _classify(prev, now_snapshot, change, volume_spike)
    return {
        "symbol": normalized,
        "anomaly_type": anomaly_type,
        "intensity": intensity,
        "money_flow_change": round(change, 2),
        "volume_spike": volume_spike,
        "interpretation": interpretation,
        "action_signal": action,
        "timeframe": "1m",
        "quote_time": int(time.time()),
    }


def _snapshot(quote: dict[str, Any]) -> dict[str, float]:
    price = _num(quote.get("price")) or 0.0
    change_pct = _num(quote.get("change_pct")) or 0.0
    volume = _num(quote.get("volume")) or 0.0
    amount = _num(quote.get("amount")) or price * volume
    direction = 1 if change_pct > 0 else -1 if change_pct < 0 else 0
    return {"price": price, "change_pct": change_pct, "volume": volume, "amount": amount, "money_flow_proxy": amount * direction, "ts": time.time()}


def _money_flow_change(prev: dict[str, float] | None, cur: dict[str, float]) -> float:
    if not prev:
        return cur["money_flow_proxy"]
    return cur["money_flow_proxy"] - prev.get("money_flow_proxy", 0.0)


def _volume_spike(prev: dict[str, float] | None, cur: dict[str, float]) -> bool:
    if not prev or prev.get("volume", 0) <= 0:
        return abs(cur["change_pct"]) >= 5
    return cur["volume"] / max(prev["volume"], 1) > 1.5


def _classify(prev: dict[str, float] | None, cur: dict[str, float], change: float, volume_spike: bool) -> tuple[str, str, str, str]:
    amount = max(cur.get("amount", 0), 1)
    ratio = change / amount
    price_change = cur["change_pct"] if not prev else (cur["price"] / max(prev["price"], 0.01) - 1) * 100
    if ratio > 0.08 and volume_spike:
        return "主力突击流入", "HIGH", "5分钟级资金代理大幅转正且成交量突然放大。", "BUY ALERT"
    if ratio < -0.08 and volume_spike:
        return "主力撤退", "HIGH", "资金代理快速转负且伴随放量，存在撤退压力。", "SELL ALERT"
    if volume_spike and abs(price_change) < 1:
        return "对倒行为", "MEDIUM", "成交量异常放大但价格不涨，疑似多空对冲或对倒。", "WATCH"
    if ratio > 0.02 and 0 <= price_change < 2 and volume_spike:
        return "拉升前兆", "MEDIUM", "小幅上行叠加资金试探流入，关注后续突破。", "BUY ALERT"
    if ratio < -0.02:
        return "资金流出", "MEDIUM", "资金代理转弱，短线需降低追高意愿。", "WATCH"
    return "正常波动", "LOW", "未发现显著主力异动，维持观察。", "WATCH"


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        if np.isnan(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None
