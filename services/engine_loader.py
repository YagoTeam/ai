from __future__ import annotations

from functools import lru_cache
from importlib import import_module
import time
from typing import Any, Callable


ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}
ANALYSIS_CACHE_TTL = 60


def safe_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return {"success": True, "data": func(*args, **kwargs), "error": ""}
    except Exception as exc:
        return {"success": False, "data": {}, "error": str(exc)}


@lru_cache(maxsize=1)
def _provider_module() -> Any:
    return import_module("data.provider")


@lru_cache(maxsize=1)
def get_provider() -> Any:
    return _provider_module().MarketDataProvider()


@lru_cache(maxsize=1)
def get_app_logic() -> Any:
    return import_module("app")


@lru_cache(maxsize=1)
def get_scanner_engine() -> Any:
    return import_module("full_market_scanner")


@lru_cache(maxsize=1)
def get_intraday_engine() -> Any:
    return import_module("intraday_signal_engine")


@lru_cache(maxsize=1)
def get_money_flow_engine() -> Any:
    return import_module("money_flow_anomaly_detector")


@lru_cache(maxsize=1)
def get_market_service() -> Any:
    return import_module("market_overview_service")


@lru_cache(maxsize=1)
def get_backtest_engine() -> Any:
    return import_module("engine_layer.backtest_engine")


def normalize_symbol(symbol: str) -> str:
    return _provider_module().normalize_symbol(symbol)


def search_stock(keyword: str) -> list[dict[str, str]]:
    return get_provider().search_stock(keyword or "")


def analyze_stock(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    cached = ANALYSIS_CACHE.get(normalized)
    if cached and time.time() - float(cached.get("timestamp", 0)) <= ANALYSIS_CACHE_TTL:
        return dict(cached["data"])
    result = get_app_logic().analyze_one(normalized)
    result = enrich_analysis_result(result)
    ANALYSIS_CACHE[normalized] = {"timestamp": time.time(), "data": dict(result)}
    return result


def stock_detail(symbol: str) -> dict[str, Any]:
    result = analyze_stock(symbol)
    return {
        "symbol": result.get("symbol"),
        "name": result.get("name"),
        "price": result.get("price"),
        "technical_analysis": result.get("technical_analysis", {}),
        "fund_flow_analysis": result.get("fund_flow_analysis", {}),
        "fundamental_analysis": result.get("fundamental_analysis", {}),
        "sentiment_analysis": result.get("sentiment_analysis", {}),
        "final_reason": result.get("final_reason", ""),
        "final_conclusion": result.get("final_conclusion", {}),
        "entry_plan": result.get("entry_plan", {}),
        "score": result.get("score"),
        "recommendation": result.get("recommendation"),
        "sector": result.get("sector", {}),
    }


def scan_top10(limit: int = 10) -> list[dict[str, Any]]:
    return get_scanner_engine().scan_full_market_top10(limit=max(1, min(int(limit or 10), 50)))


def market_overview() -> dict[str, Any]:
    return get_market_service().get_market_overview()


def intraday_signal(symbol: str | None = None, limit: int = 10) -> dict[str, Any]:
    engine = get_intraday_engine()
    if symbol:
        normalized = normalize_symbol(symbol)
        row = engine.generate_intraday_signal(normalized)
        row = _enrich_market_row(row)
        return {"signals": [_normalize_signal(row)], "cache_ttl": 60, "watchlist_size": 1}

    watchlist = scan_top10(limit=limit)
    rows = engine.scan_intraday_signals(watchlist)
    lookup = {item.get("symbol") or item.get("code"): item for item in watchlist}
    return {"signals": [_normalize_signal(_merge_market_row(row, lookup)) for row in rows], "cache_ttl": 60, "watchlist_size": len(watchlist)}


def moneyflow_anomaly(symbol: str | None = None, limit: int = 10) -> dict[str, Any]:
    engine = get_money_flow_engine()
    if symbol:
        rows = [_enrich_market_row(engine.detect_money_flow_anomaly(normalize_symbol(symbol)))]
        watchlist_size = 1
    else:
        watchlist = scan_top10(limit=limit)
        rows = engine.scan_money_flow_anomalies(watchlist)
        lookup = {item.get("symbol") or item.get("code"): item for item in watchlist}
        rows = [_merge_market_row(row, lookup) for row in rows]
        watchlist_size = len(watchlist)

    abnormal_rows = [dict(row) for row in rows if row.get("intensity") in {"HIGH", "MEDIUM"} or row.get("action_signal") != "WATCH"]
    inflow = sorted(rows, key=lambda row: float(row.get("money_flow_change") or 0), reverse=True)[:10]
    outflow = sorted(rows, key=lambda row: float(row.get("money_flow_change") or 0))[:10]
    detection_score = _detection_score(rows)
    return {
        "abnormal_stocks": abnormal_rows,
        "anomalies": rows,
        "inflow_ranking": inflow,
        "outflow_ranking": outflow,
        "detection_score": detection_score,
        "cache_ttl": 60,
        "watchlist_size": watchlist_size,
    }


def backtest_strategy(symbol: str, short_window: int = 5, long_window: int = 20, days: int = 180) -> dict[str, Any]:
    return get_backtest_engine().run_backtest(
        normalize_symbol(symbol),
        short_window=short_window,
        long_window=long_window,
        days=days,
    )


def portfolio_analyze(
    symbol: str,
    cost_price: float,
    shares: int,
    available_cash: float,
    max_position_ratio: float,
    risk_preference: str,
) -> dict[str, Any]:
    analysis = analyze_stock(symbol)
    price = _num(analysis.get("price")) or 0.0
    cost = max(float(cost_price or 0), 0.01)
    shares = int(shares or 0)
    market_value = round(price * shares, 2)
    cost_amount = round(cost * shares, 2)
    floating_profit = round(market_value - cost_amount, 2)
    floating_profit_ratio = round((price / cost - 1) * 100, 2) if cost > 0 else 0.0
    entry = analysis.get("entry_plan", {})
    stop_loss = _num(entry.get("stop_loss_price")) or round(cost * 0.92, 2)
    add_price = _num(entry.get("second_buy_price")) or round(price * 0.95, 2)
    reduce_price = _num(entry.get("take_profit_price_1")) or round(max(price, cost) * 1.08, 2)
    score = _num(analysis.get("score")) or 50
    recommendation = analysis.get("recommendation") or "HOLD"

    if price <= stop_loss:
        advice = "跌破止损"
        next_action = f"如果价格已经跌破 {stop_loss:.2f} 元，说明原判断失败，应优先控制亏损。"
    elif floating_profit_ratio >= 12 and price >= reduce_price * 0.98:
        advice = "分批止盈"
        next_action = f"已有较明显浮盈，接近 {reduce_price:.2f} 元可考虑先落袋一部分。"
    elif price < cost and score >= 65 and available_cash > 0:
        advice = "等回调加仓"
        next_action = f"不要盲目补仓，等价格企稳并接近 {add_price:.2f} 元附近再考虑第二笔。"
    elif recommendation == "BUY" and score >= 70:
        advice = "继续持有"
        next_action = f"趋势和综合评分尚可，跌破 {stop_loss:.2f} 元前可继续观察持有。"
    else:
        advice = "谨慎持有"
        next_action = f"当前胜率不算突出，若不能放量突破 {reduce_price:.2f} 元，可考虑降低仓位。"

    if risk_preference == "保守" and floating_profit_ratio > 6:
        advice = "分批止盈"
    if risk_preference == "激进" and recommendation == "BUY" and score >= 75:
        next_action += " 激进型可保留底仓，但不建议一次性满仓。"

    return {
        "symbol": analysis.get("symbol"),
        "name": analysis.get("name"),
        "current_price": price,
        "market_value": market_value,
        "cost_amount": cost_amount,
        "floating_profit": floating_profit,
        "floating_profit_ratio": floating_profit_ratio,
        "position_advice": advice,
        "add_position_price": round(add_price, 2),
        "reduce_position_price": round(reduce_price, 2),
        "stop_loss_price": round(stop_loss, 2),
        "reason": _portfolio_reason(analysis, floating_profit_ratio, risk_preference),
        "next_action": next_action,
        "analysis": analysis,
    }


def enrich_analysis_result(result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(result)
    enriched["fundamental_analysis"] = _standardize_fundamental(enriched)
    enriched["entry_plan"] = build_entry_plan(enriched)
    enriched["final_conclusion"] = build_final_conclusion(enriched)
    if not enriched.get("final_reason"):
        enriched["final_reason"] = enriched["final_conclusion"].get("summary", "")
    return enriched


def build_entry_plan(result: dict[str, Any]) -> dict[str, Any]:
    price = _num(result.get("price")) or 0.0
    score = _num(result.get("score")) or 50.0
    risk = str(result.get("risk_level") or (result.get("signals") or {}).get("risk_level") or "MEDIUM")
    technical = result.get("technical") or result.get("technical_data", {}).get("value") or {}
    ma20 = _num(technical.get("ma20"))
    ma60 = _num(technical.get("ma60"))
    first = price * (0.985 if score >= 75 else 0.97 if score >= 65 else 0.94)
    if ma20:
        first = min(first, ma20 * 1.02)
    second = first * (0.95 if score >= 65 else 0.92)
    if ma60:
        second = min(second, ma60 * 1.03)
    stop = min(second * 0.95, first * 0.92)
    take1 = price * (1.08 if score >= 70 else 1.05)
    take2 = price * (1.16 if score >= 70 else 1.10)
    if "HIGH" in risk:
        position = "暂不建仓"
    elif score >= 80 and "LOW" in risk:
        position = "中等仓位"
    elif score >= 65:
        position = "轻仓"
    else:
        position = "暂不建仓"
    return {
        "first_buy_price": round(first, 2),
        "second_buy_price": round(second, 2),
        "stop_loss_price": round(stop, 2),
        "take_profit_price_1": round(take1, 2),
        "take_profit_price_2": round(take2, 2),
        "position_suggestion": position,
        "entry_reason": "结合当前价格、均线支撑、综合评分和风险等级生成。趋势强时只给小幅回踩位，趋势弱时等待更低支撑位。",
        "risk_reward_ratio": f"约 1:{round((take1 - first) / max(first - stop, 0.01), 1)}",
        "disclaimer": "仅为辅助分析，不构成投资建议。",
    }


def build_final_conclusion(result: dict[str, Any]) -> dict[str, Any]:
    name = result.get("name") or result.get("symbol") or "-"
    score = _num(result.get("score")) or 50
    recommendation = result.get("recommendation") or "HOLD"
    entry = result.get("entry_plan") or build_entry_plan(result)
    if recommendation == "BUY" and score >= 80:
        judgement = "可分批建仓"
    elif recommendation == "BUY":
        judgement = "可轻仓试探"
    elif recommendation == "SELL":
        judgement = "应该减仓"
    elif score < 60:
        judgement = "暂不建议买入"
    else:
        judgement = "适合观察"
    technical = _plain_module_reason(result.get("technical_analysis"), "技术面暂时没有明显优势，先观察价格能否站稳关键位置。")
    funds = _plain_module_reason(result.get("fund_flow_analysis"), "资金面没有看到很强的持续流入信号，追高要谨慎。")
    fundamental = _plain_module_reason(result.get("fundamental_analysis"), "基本面数据需要结合估值和盈利质量一起看，缺失字段不强行编造。")
    sentiment = _plain_module_reason(result.get("sentiment_analysis"), "消息面目前按中性处理，不把短期情绪当成唯一依据。")
    return {
        "stock": name,
        "judgement": judgement,
        "core_reasons": {
            "technical": technical,
            "fund_flow": funds,
            "fundamental": fundamental,
            "sentiment": sentiment,
        },
        "actions": {
            "aggressive": f"激进型只考虑轻仓试探，第一笔参考 {entry.get('first_buy_price')} 元附近。",
            "balanced": f"稳健型等待回踩确认，第二笔参考 {entry.get('second_buy_price')} 元附近。",
            "conservative": "保守型等趋势和资金都更明确后再行动，宁愿错过也不追高。",
        },
        "risk_warning": f"最大风险是跌破关键支撑。若跌破 {entry.get('stop_loss_price')} 元，需要重新判断。",
        "summary": f"{name} 当前综合判断为“{judgement}”。第一笔可参考 {entry.get('first_buy_price')} 元，跌破 {entry.get('stop_loss_price')} 元要控制风险。",
    }


def _standardize_fundamental(result: dict[str, Any]) -> dict[str, Any]:
    raw = result.get("fundamental") or result.get("fundamental_data", {}).get("value") or {}
    old = result.get("fundamental_analysis") or {}
    fields = {
        "pe": _num(raw.get("pe")),
        "pb": _num(raw.get("pb")),
        "roe": _num(raw.get("roe")),
        "revenue_growth": _num(raw.get("revenue_growth")),
        "net_profit_growth": _num(raw.get("net_profit_growth")),
        "gross_margin": _num(raw.get("gross_margin")),
        "net_margin": _num(raw.get("net_margin")),
        "debt_ratio": _num(raw.get("debt_ratio")),
    }
    real_count = sum(value is not None for value in fields.values())
    source = raw.get("data_source") or result.get("data_source", {}).get("fundamental") or "ESTIMATED"
    if real_count >= 5 and source == "REAL":
        quality = "HIGH"
        source_text = "真实财务数据"
    elif real_count >= 2:
        quality = "MEDIUM"
        source_text = "真实财务数据不足，部分字段缺失"
    elif source == "ESTIMATED":
        quality = "LOW"
        source_text = "行业均值估算，置信度较低"
    else:
        quality = "LOW"
        source_text = "暂无可靠数据"
    explanation = old.get("valuation_summary") or old.get("explanation") or "基本面以真实可取字段为准，未获取到的字段不参与核心判断。"
    return {
        "score": _num(raw.get("score")) or _num(old.get("score")),
        **fields,
        "data_quality": quality,
        "data_source_text": source_text,
        "explanation": explanation,
    }


def _merge_market_row(row: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    symbol = row.get("symbol") or row.get("code")
    source = lookup.get(symbol) or {}
    merged = {**source, **row}
    if not merged.get("name") or not merged.get("price"):
        merged = _enrich_market_row(merged)
    return merged


def _enrich_market_row(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    symbol = merged.get("symbol") or merged.get("code")
    if not symbol:
        return merged
    try:
        quote = get_provider().get_realtime_quote(symbol)
        merged.setdefault("name", quote.get("name"))
        merged.setdefault("price", quote.get("price"))
    except Exception:
        pass
    try:
        scanner = get_scanner_engine()
        merged.setdefault("sector", scanner.classify_sector(merged) if hasattr(scanner, "classify_sector") else {})
    except Exception:
        merged.setdefault("sector", {})
    return merged


def _normalize_signal(row: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(row.get("signal_type") or "WATCH")
    action_type = "BUY" if raw_type in {"BREAKOUT", "ACCUMULATION"} else "SELL" if raw_type in {"DISTRIBUTION", "PANIC SELL"} else "HOLD"
    reasons = row.get("trigger_reason") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    return {
        **row,
        "raw_signal_type": raw_type,
        "signal_type": action_type,
        "reason": "；".join(str(item) for item in reasons) or "未触发强盘中模式，保持观察",
        "timestamp": row.get("quote_time"),
    }


def _detection_score(rows: list[dict[str, Any]]) -> float:
    weights = {"HIGH": 90.0, "MEDIUM": 65.0, "LOW": 35.0}
    if not rows:
        return 0.0
    return round(max(weights.get(str(row.get("intensity")), 0.0) for row in rows), 2)


def _plain_module_reason(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        for key in ["explanation", "trend_judgement", "long_short_balance", "valuation_summary", "market_impact", "summary"]:
            if value.get(key):
                return str(value[key])
        for item in value.values():
            if isinstance(item, str) and item:
                return item
    if isinstance(value, str) and value:
        return value
    return fallback


def _portfolio_reason(analysis: dict[str, Any], floating_profit_ratio: float, risk_preference: str) -> str:
    score = _num(analysis.get("score")) or 50
    recommendation = analysis.get("recommendation") or "HOLD"
    profit_text = "已有浮盈" if floating_profit_ratio > 0 else "目前浮亏"
    return f"{profit_text} {abs(floating_profit_ratio):.2f}%，综合评分 {score:.2f}，系统建议 {recommendation}，风险偏好为{risk_preference}。操作重点是按止损位和分批价格执行，不要情绪化补仓。"


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
