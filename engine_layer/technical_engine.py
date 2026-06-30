from __future__ import annotations

from typing import Any

import numpy as np

from data_schema import metric_value
from engine_layer.utils import bounded_score, num


def score(technical: dict[str, Any]) -> float | None:
    if technical.get("status") == "NO_DATA":
        return None
    result = 50.0
    trend = metric_value(technical.get("trend"))
    result += 18 if trend == "UP" else -15 if trend == "DOWN" else 0
    rsi_value = num(technical.get("rsi"))
    if rsi_value is not None:
        result += float(np.clip((rsi_value - 50) * 0.35, -12, 12))
    volume_change = num(technical.get("volume_change"))
    if volume_change is not None:
        result += float(np.clip(volume_change * 20, -10, 12))
    macd_hist = num((technical.get("macd") or {}).get("hist"))
    if macd_hist is not None:
        result += 6 if macd_hist > 0 else -6
    return bounded_score(result)


def reasons(technical: dict[str, Any]) -> list[str]:
    trend = metric_value(technical.get("trend"))
    rsi_value = num(technical.get("rsi"))
    macd_hist = num((technical.get("macd") or {}).get("hist"))
    items: list[str] = []
    if trend == "UP":
        items.append("技术趋势偏多")
    elif trend == "DOWN":
        items.append("技术趋势偏空")
    else:
        items.append("技术趋势震荡")
    if macd_hist is not None:
        items.append("MACD动能为正" if macd_hist > 0 else "MACD动能为负")
    if rsi_value is not None:
        if rsi_value >= 70:
            items.append("RSI处于超买区")
        elif rsi_value <= 30:
            items.append("RSI接近超卖区")
        else:
            items.append("RSI处于正常区间")
    return items

