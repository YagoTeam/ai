from __future__ import annotations

from typing import Any


def assess_risk(row: dict[str, Any]) -> dict[str, Any]:
    change_pct = abs(row.get("change_pct") or 0.0)
    amount = row.get("amount") or 0.0
    risk_points = 0
    reasons: list[str] = []
    if change_pct >= 9:
        risk_points += 2
        reasons.append("单日波动接近或超过涨跌停区间")
    elif change_pct >= 5:
        risk_points += 1
        reasons.append("单日波动超过5%")
    if amount <= 0:
        risk_points += 1
        reasons.append("成交额缺失或过低")
    if row.get("score", 0) < 45:
        risk_points += 1
        reasons.append("机构评分不足")
    level = "HIGH" if risk_points >= 2 else "MEDIUM" if risk_points == 1 else "LOW"
    return {"risk_level": level, "risk_reasons": reasons}


def filter_high_risk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("risk_level") != "HIGH"]
