from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from services.nlp_intent import parse_user_question
from services.stock_resolver import resolve_stock


SYSTEM_PROMPT = """你是一个 A股量化分析机器人的意图识别器。
你的任务不是回答股票问题，而是把用户自然语言解析成结构化 JSON。
不能编造行情数据。
不能做确定性投资承诺。
如果用户问题需要股票但没有股票，requires_stock=true 且 stock_query=null。
如果用户是在问自动选股、主力动向、大盘、盘中信号，不需要股票。
只输出 JSON，不要输出解释。

支持 intent：
help
top10
money_flow
intraday
market
stock_analysis
limit_up_probability
buy_or_not
add_position
sell_or_hold
target_price
portfolio
compare
explain
general
unknown
"""


def route_user_message(text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    raw = str(text or "").strip()
    llm_route = _route_with_llm(raw, context)
    route = _normalize_route(llm_route) if llm_route else _rule_route(raw, context)
    if route.get("requires_stock") and not route.get("stock_query") and _has_context_reference(raw, context):
        last_stock = context.get("last_stock") if isinstance(context.get("last_stock"), dict) else {}
        route["stock_query"] = last_stock.get("symbol") or last_stock.get("name")
        route["use_context_stock"] = True
    route["tool_plan"] = _tool_plan(route)
    return route


def _rule_route(text: str, context: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_user_question(text)
    compact = _compact(text)
    intent = _map_intent(parsed["intent"])

    if any(word in compact for word in ["推荐", "选股", "可以买的股票", "短线强势股", "值得关注"]):
        intent = "top10"
    elif any(word in compact for word in ["主力动向", "主力今天", "主力在买", "主力异动", "资金异动", "资金流"]):
        intent = "money_flow"
    elif any(word in compact for word in ["盘中信号", "实时信号", "盯盘"]):
        intent = "intraday"
    elif any(word in compact for word in ["大盘", "市场怎么样", "创业板", "上证", "指数"]):
        intent = "market"
    portfolio = _portfolio_values(text)
    if portfolio.get("cost") is not None or portfolio.get("shares") is not None:
        intent = "portfolio"

    requires_stock = intent in {
        "stock_analysis",
        "limit_up_probability",
        "buy_or_not",
        "add_position",
        "sell_or_hold",
        "target_price",
        "portfolio",
        "compare",
        "explain",
    }
    if intent in {"top10", "money_flow", "intraday", "market", "help", "general"}:
        requires_stock = False

    stock_query = parsed.get("stock_query") or None
    if stock_query in {"那", "它", "这只", "这个", "刚才"}:
        stock_query = None
    used_context_stock = False
    if requires_stock and not stock_query and _has_context_reference(text, context):
        last_stock = context.get("last_stock") if isinstance(context.get("last_stock"), dict) else {}
        stock_query = last_stock.get("symbol") or last_stock.get("name")
        used_context_stock = bool(stock_query)
    if not requires_stock:
        stock_query = None

    return {
        "intent": intent,
        "requires_stock": requires_stock,
        "stock_query": stock_query,
        "symbols": [],
        "user_question": parsed.get("question") or text,
        "portfolio": portfolio,
        "confidence": 0.9 if stock_query or not requires_stock else 0.72,
        "clarify_question": None,
        "use_context_stock": used_context_stock,
    }


def _route_with_llm(text: str, context: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "").strip() or "gpt-4o-mini"
    if not api_key or not base_url:
        return None
    try:
        response = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"text": text, "context": context}, ensure_ascii=False)},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=8,
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _normalize_route(route: dict[str, Any]) -> dict[str, Any]:
    intent = _map_intent(str(route.get("intent") or "unknown"))
    requires_stock = bool(route.get("requires_stock"))
    if intent in {"top10", "money_flow", "intraday", "market", "help", "general"}:
        requires_stock = False
    return {
        "intent": intent,
        "requires_stock": requires_stock,
        "stock_query": route.get("stock_query"),
        "symbols": route.get("symbols") if isinstance(route.get("symbols"), list) else [],
        "user_question": route.get("user_question") or "",
        "portfolio": route.get("portfolio") if isinstance(route.get("portfolio"), dict) else {},
        "confidence": float(route.get("confidence") or 0.75),
        "clarify_question": route.get("clarify_question"),
    }


def _tool_plan(route: dict[str, Any]) -> list[str]:
    intent = route.get("intent")
    if intent == "top10":
        return ["scan_full_market_top10"]
    if intent == "money_flow":
        return ["scan_money_flow_anomalies"]
    if intent == "intraday":
        return ["scan_intraday_signals"]
    if intent == "market":
        return ["get_market_overview"]
    if intent == "portfolio":
        return ["resolve_stock", "portfolio_analyze"]
    if intent == "limit_up_probability":
        return ["resolve_stock", "analyze_limit_up_probability"]
    if route.get("requires_stock"):
        return ["resolve_stock", "analyze_stock"]
    return ["reply_general_finance_answer"]


def _map_intent(intent: str) -> str:
    mapping = {
        "intraday_signals": "intraday",
        "money_flow_anomalies": "money_flow",
        "market_overview": "market",
    }
    return mapping.get(intent, intent)


def _portfolio_values(text: str) -> dict[str, Any]:
    cost = _first_number_after(text, ["成本", "本"])
    match = re.search(r"(\d+)\s*股", text)
    shares = float(match.group(1)) if match else None
    return {
        "cost": cost,
        "shares": int(shares) if shares is not None else None,
        "available_cash": None,
        "risk_preference": _risk_preference(text),
    }


def _first_number_after(text: str, markers: list[str]) -> float | None:
    for marker in markers:
        match = re.search(re.escape(marker) + r"\s*(\d+(?:\.\d+)?)", text)
        if match:
            return float(match.group(1))
    return None


def _risk_preference(text: str) -> str | None:
    if "保守" in text:
        return "保守"
    if "激进" in text:
        return "激进"
    if "稳健" in text:
        return "稳健"
    return None


def _has_context_reference(text: str, context: dict[str, Any]) -> bool:
    if not context.get("last_stock"):
        return False
    return any(word in text for word in ["那", "刚才", "这只", "它", "该股", "这个"])


def _compact(text: str) -> str:
    return re.sub(r"[\s,，。！？?、:：;；()（）【】\[\]{}<>《》\"'“”‘’]", "", str(text or "").upper())
