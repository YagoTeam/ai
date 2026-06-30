from __future__ import annotations

from typing import Any

from data_schema import metric_value
from engine_layer import fund_flow_engine, fundamental_engine, sentiment_engine, technical_engine


WEIGHTS = {
    "technical": 0.30,
    "fund_flow": 0.30,
    "fundamental": 0.20,
    "sentiment": 0.20,
}


def weighted_score(parts: list[tuple[float | None, float]]) -> float:
    valid = [(score, weight) for score, weight in parts if score is not None]
    if not valid:
        raise ValueError("no scored module is available")
    total_weight = sum(weight for _, weight in valid)
    return round(sum(float(score) * weight for score, weight in valid) / total_weight, 2)


def recommendation(total_score: float) -> str:
    return "BUY" if total_score >= 45 else "SELL"


def realtime_signals(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    rec = analysis.get("recommendation")
    score = analysis.get("score")
    change_pct = analysis.get("change_pct")
    if rec == "BUY":
        signals.append({"type": "BUY", "level": "INFO", "message": "综合评分达到买入区间", "score": score})
    elif rec == "SELL":
        signals.append({"type": "SELL", "level": "WARNING", "message": "综合评分落入卖出/规避区间", "score": score})
    if change_pct is not None and abs(float(change_pct)) >= 5:
        signals.append({"type": "RISK", "level": "WARNING", "message": "单日波动超过5%，需控制仓位", "change_pct": change_pct})
    trend = metric_value((analysis.get("technical_data") or {}).get("trend"))
    if trend == "DOWN":
        signals.append({"type": "RISK", "level": "WARNING", "message": "技术趋势偏空", "trend": trend})
    return signals


def stock_reasons(data: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    reasons.extend(technical_engine.reasons(data.get("technical_data", {})))
    reasons.extend(fund_flow_engine.reasons(data.get("fund_flow_data", {})))
    reasons.extend(fundamental_engine.reasons(data.get("fundamental_data", {})))
    reasons.extend(sentiment_engine.reasons(data.get("sentiment_data", {})))
    return reasons[:8]
