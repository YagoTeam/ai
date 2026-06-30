from __future__ import annotations

from typing import Any

from engine_layer.utils import bounded_score, num


def score(funds: dict[str, Any]) -> float | None:
    if funds.get("status") not in {"OK", "COMPLETED"}:
        return None
    result = 50.0
    for key, weight in [("main_flow", 18), ("super_order", 10), ("large_order", 8)]:
        value = num(funds.get(key))
        if value is None:
            continue
        result += weight if value > 0 else -weight if value < 0 else 0
    return bounded_score(result)


def reasons(funds: dict[str, Any]) -> list[str]:
    main_flow = num(funds.get("main_flow"))
    data_source = funds.get("data_source", "ESTIMATED")
    if main_flow is None:
        return ["资金流数据不可用"]
    direction = "流入" if main_flow > 0 else "流出" if main_flow < 0 else "均衡"
    return [f"主力资金{direction}", f"资金来源标记为{data_source}"]

