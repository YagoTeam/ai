from __future__ import annotations

from typing import Any

import numpy as np


WEIGHTS = {
    "fund_momentum": 0.40,
    "technical_trend": 0.25,
    "fundamental_quality": 0.20,
    "sentiment_event": 0.15,
}


def score_stock(row: dict[str, Any], sector_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fund_momentum = _fund_momentum(row)
    technical_trend = _technical_trend(row)
    fundamental_quality = _fundamental_quality(row)
    sentiment_event = _sentiment_event(row, sector_stats)
    total = round(
        fund_momentum * WEIGHTS["fund_momentum"]
        + technical_trend * WEIGHTS["technical_trend"]
        + fundamental_quality * WEIGHTS["fundamental_quality"]
        + sentiment_event * WEIGHTS["sentiment_event"],
        2,
    )
    return {
        "score": total,
        "factor_scores": {
            "fund_momentum": round(fund_momentum, 2),
            "technical_trend": round(technical_trend, 2),
            "fundamental_quality": round(fundamental_quality, 2),
            "sentiment_event": round(sentiment_event, 2),
            "weights": WEIGHTS,
        },
        "recommendation": "BUY" if total >= 45 else "SELL",
    }


def _fund_momentum(row: dict[str, Any]) -> float:
    amount = row.get("amount") or 0.0
    volume = row.get("volume") or 0.0
    change_pct = row.get("change_pct") or 0.0
    activity = np.log10(max(amount, volume, 1))
    direction_bonus = np.clip(change_pct * 2.5, -18, 20)
    turnover_bonus = np.clip(activity * 4.5, 0, 42)
    return float(np.clip(35 + turnover_bonus + direction_bonus, 0, 100))


def _technical_trend(row: dict[str, Any]) -> float:
    change_pct = row.get("change_pct") or 0.0
    return float(np.clip(50 + change_pct * 4, 0, 100))


def _fundamental_quality(row: dict[str, Any]) -> float:
    score = 50.0
    pe = row.get("pe")
    pb = row.get("pb")
    if pe is not None:
        score += 12 if 0 < pe <= 35 else -8 if pe > 80 or pe <= 0 else 2
    if pb is not None:
        score += 8 if 0 < pb <= 4 else -6 if pb > 8 or pb <= 0 else 1
    return float(np.clip(score, 0, 100))


def _sentiment_event(row: dict[str, Any], sector_stats: dict[str, dict[str, Any]]) -> float:
    sector = row.get("sector", {}).get("sub_industry", "")
    heat = (sector_stats.get(sector) or {}).get("heat_score", 0)
    return float(np.clip(50 + heat * 2, 0, 100))

