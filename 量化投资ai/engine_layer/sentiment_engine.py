from __future__ import annotations

from typing import Any

import numpy as np

from data_schema import metric_value


def score(sentiment: dict[str, Any]) -> float | None:
    if sentiment.get("status") not in {"OK", "COMPLETED"}:
        return None
    label = metric_value(sentiment.get("sentiment")) or "NEUTRAL"
    confidence = float(metric_value(sentiment.get("confidence")) or 0)
    if label == "POSITIVE":
        return round(float(np.clip(50 + confidence * 35, 0, 100)), 2)
    if label == "NEGATIVE":
        return round(float(np.clip(50 - confidence * 35, 0, 100)), 2)
    return 50.0


def reasons(sentiment: dict[str, Any]) -> list[str]:
    label = metric_value(sentiment.get("sentiment")) or "NEUTRAL"
    confidence = metric_value(sentiment.get("confidence"))
    return [f"新闻情绪为{label}", f"情绪置信度为{confidence}"]

