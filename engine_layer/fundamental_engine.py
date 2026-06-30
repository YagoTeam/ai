from __future__ import annotations

from typing import Any

import numpy as np

from engine_layer.utils import bounded_score, num, percent_to_ratio


def score(fundamental: dict[str, Any]) -> float | None:
    if fundamental.get("status") not in {"OK", "COMPLETED"}:
        return None
    result = 50.0
    estimated = fundamental.get("estimated") or {}
    pe = num(fundamental.get("pe")) if num(fundamental.get("pe")) is not None else num(estimated.get("pe"))
    pb = num(fundamental.get("pb")) if num(fundamental.get("pb")) is not None else num(estimated.get("pb"))
    roe = percent_to_ratio(fundamental.get("roe")) if num(fundamental.get("roe")) is not None else percent_to_ratio(estimated.get("roe"))
    growth = percent_to_ratio(fundamental.get("revenue_growth")) if num(fundamental.get("revenue_growth")) is not None else percent_to_ratio(estimated.get("revenue_growth"))
    if pe is not None:
        result += 12 if 0 < pe <= 35 else -8 if pe > 80 or pe <= 0 else 2
    if pb is not None:
        result += 8 if 0 < pb <= 4 else -6 if pb > 8 or pb <= 0 else 1
    if roe is not None:
        result += float(np.clip(roe * 120, -12, 18))
    if growth is not None:
        result += float(np.clip(growth * 80, -10, 16))
    return bounded_score(result)


def reasons(fundamental: dict[str, Any]) -> list[str]:
    pe = num(fundamental.get("pe"))
    pb = num(fundamental.get("pb"))
    estimated = fundamental.get("estimated") or {}
    items: list[str] = []
    if pe is not None:
        items.append("PE来自真实行情估值")
    elif estimated.get("pe") is not None:
        items.append("PE使用估算值并已标记")
    if pb is not None:
        items.append("PB来自真实行情估值")
    elif estimated.get("pb") is not None:
        items.append("PB使用估算值并已标记")
    return items or ["基本面数据有限"]

