from __future__ import annotations

import re
from typing import Any


INTENT_PATTERNS = [
    ("help", ["帮助", "菜单", "指令", "怎么用", "help"]),
    ("top10", ["自动分析", "今日选股", "今天有什么票", "有什么票", "推荐股票", "TOP10", "值得关注"]),
    ("intraday_signals", ["盘中信号", "实时信号", "盯盘"]),
    ("money_flow_anomalies", ["主力异动", "资金异动", "主力资金", "资金流"]),
    ("market_overview", ["大盘怎么看", "大盘", "市场怎么样", "创业板怎么看", "上证", "指数"]),
    ("limit_up_probability", ["涨停吗", "会不会涨停", "能涨停", "涨停机会", "冲板", "封板"]),
    ("add_position", ["加仓", "补仓", "还能补", "成本"]),
    ("sell_or_hold", ["要不要卖", "卖出", "还能拿", "持有", "止损", "割肉"]),
    ("target_price", ["跌到多少", "目标价", "支撑位", "压力位", "多少可以买", "买点"]),
    ("buy_or_not", ["还能买吗", "可以买", "买入", "建仓", "适合买吗"]),
]


def parse_user_question(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    compact = _compact(raw)
    intent = "stock_analysis"
    for name, keywords in INTENT_PATTERNS:
        if any(_compact(keyword) in compact for keyword in keywords):
            intent = name
            break

    stock_query = _extract_stock_query(raw, intent)
    return {
        "intent": intent,
        "stock_query": stock_query,
        "question": _question_part(raw, stock_query),
        "time_horizon": _time_horizon(raw, intent),
        "risk_preference": _risk_preference(raw),
    }


def _extract_stock_query(text: str, intent: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^(@\S+\s*)+", "", cleaned).strip()
    for prefix in ["分析", "查一下", "查", "股票"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    if intent in {"top10", "intraday_signals", "money_flow_anomalies", "market_overview", "help"}:
        return ""

    code = re.search(r"(?<!\d)(\d{6})(?:\.(?:SZ|SH))?(?!\d)", cleaned.upper())
    if code:
        return code.group(0)

    stop_words = [
        "今天会涨停吗",
        "会不会涨停",
        "能涨停吗",
        "有没有涨停机会",
        "今天怎么看",
        "怎么看",
        "还能买吗",
        "现在可以买入吗",
        "适合建仓吗",
        "现在适合加仓吗",
        "还能补吗",
        "要不要卖",
        "还能拿吗",
        "要不要止损",
        "跌到多少可以买",
        "目标价多少",
        "支撑位多少",
        "压力位多少",
        "可以买",
        "买入",
        "建仓",
        "加仓",
        "补仓",
        "目标价",
        "支撑位",
        "压力位",
        "吗",
        "？",
        "?",
    ]
    query = cleaned
    for word in stop_words:
        query = query.replace(word, "")
    query = re.sub(r"成本\s*\d+(\.\d+)?", "", query)
    query = re.sub(r"\d+(\.\d+)?\s*元?", "", query)
    return query.strip() or cleaned


def _question_part(text: str, stock_query: str) -> str:
    value = str(text or "")
    if stock_query:
        value = value.replace(stock_query, "")
    return value.strip(" ，。！？?")


def _time_horizon(text: str, intent: str) -> str:
    if any(word in text for word in ["今天", "盘中", "现在", "实时"]):
        return "intraday"
    if intent in {"limit_up_probability", "intraday_signals"}:
        return "intraday"
    return "swing"


def _risk_preference(text: str) -> str | None:
    if "保守" in text:
        return "保守"
    if "激进" in text:
        return "激进"
    if "稳健" in text:
        return "稳健"
    return None


def _compact(text: str) -> str:
    return re.sub(r"[\s,，。！？?、:：;；()（）【】\[\]{}<>《》\"'“”‘’]", "", str(text or "").upper())
