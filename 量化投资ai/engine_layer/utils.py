from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from data_schema import metric_value


def num(value: Any) -> float | None:
    value = metric_value(value)
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def percent_to_ratio(value: Any) -> float | None:
    parsed = num(value)
    if parsed is None:
        return None
    return parsed / 100 if abs(parsed) > 1 else parsed


def bounded_score(value: float) -> float:
    return round(float(np.clip(value, 0, 100)), 2)

