from __future__ import annotations

from typing import Any

import pandas as pd


def metric(value: Any, source: str, confidence: float, timeframe: str = "daily", valid: bool | None = None) -> dict[str, Any]:
    parsed_valid = _is_valid(value) if valid is None else bool(valid)
    return {
        "value": value if parsed_valid else None,
        "source": source,
        "confidence": round(float(max(0, min(confidence, 1))), 2),
        "timeframe": timeframe,
        "valid": parsed_valid,
    }


def metric_value(item: Any) -> Any:
    if isinstance(item, dict) and {"value", "source", "confidence", "timeframe", "valid"}.issubset(item.keys()):
        return item.get("value")
    return item


def metric_valid(item: Any) -> bool:
    if isinstance(item, dict) and {"value", "source", "confidence", "timeframe", "valid"}.issubset(item.keys()):
        return bool(item.get("valid"))
    return _is_valid(item)


def _is_valid(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True
