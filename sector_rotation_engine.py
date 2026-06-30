from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np


THEME_KEYWORDS = [
    ("科技", "CPO", ["光通信", "通信", "光模块", "光迅", "中际", "天孚", "新易盛"]),
    ("科技", "PCB", ["PCB", "电路", "生益", "沪电", "胜宏"]),
    ("医药", "创新药", ["药", "医", "生物", "医疗", "制药"]),
    ("消费", "白酒", ["酒", "茅台", "五粮", "泸州", "洋河"]),
    ("新能源", "光伏", ["光伏", "太阳", "硅", "隆基", "阳光"]),
    ("新能源", "锂电", ["锂", "电池", "宁德", "新能源"]),
    ("金融", "银行", ["银行", "证券", "保险"]),
    ("科技", "半导体", ["半导", "芯", "微", "晶", "集成"]),
]


def classify_sector(row: dict[str, Any]) -> dict[str, str]:
    industry = str(row.get("industry") or "")
    name = str(row.get("name") or "")
    text = industry + name
    for broad, sub, keywords in THEME_KEYWORDS:
        if any(word in text for word in keywords):
            return {"industry": broad, "sub_industry": sub}
    if industry:
        return {"industry": industry, "sub_industry": industry}
    return {"industry": "综合", "sub_industry": "综合行业"}


def sector_rankings(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sector = row.get("sector") or classify_sector(row)
        groups[sector["sub_industry"]].append(row)
    ranking: dict[str, dict[str, Any]] = {}
    for sector_name, items in groups.items():
        avg_change = float(np.mean([item.get("change_pct") or 0 for item in items]))
        total_amount = float(sum(item.get("amount") or 0 for item in items))
        ranking[sector_name] = {
            "member_count": len(items),
            "avg_change_pct": round(avg_change, 2),
            "total_amount": round(total_amount, 2),
            "heat_score": round(avg_change * 2 + np.log10(max(total_amount, 1)), 2),
        }
    return ranking
