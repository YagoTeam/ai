from __future__ import annotations

from typing import Any

from services import agent_router, engine_loader, response_composer
from services.conversation_memory import update_context
from services.stock_resolver import resolve_stock


HELP_TEXT = """可用指令：
1. @小牛牛 德明利
2. @小牛牛 300394
3. @小牛牛 自动分析
4. @小牛牛 盘中信号
5. @小牛牛 主力异动
6. @小牛牛 天孚通信今天会涨停吗？
7. @小牛牛 贵州茅台跌到多少可以买？"""


def answer_user_question(text: str, context: dict[str, Any] | None = None, chat_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    route = agent_router.route_user_message(text, context)
    intent = route["intent"]
    stock_payload: dict[str, Any] | None = None

    try:
        if intent == "help":
            reply = HELP_TEXT
        elif intent == "top10":
            rows = engine_loader.safe_call(engine_loader.scan_top10, 10).get("data")
            reply = response_composer.compose_top10(rows if isinstance(rows, list) else [])
        elif intent == "money_flow":
            data = engine_loader.safe_call(engine_loader.moneyflow_anomaly, None, 10).get("data")
            reply = response_composer.compose_money_flow(data if isinstance(data, dict) else {})
        elif intent == "intraday":
            data = engine_loader.safe_call(engine_loader.intraday_signal, None, 10).get("data")
            reply = response_composer.compose_intraday(data if isinstance(data, dict) else {})
        elif intent == "market":
            data = engine_loader.safe_call(engine_loader.market_overview).get("data")
            reply = response_composer.compose_market(data if isinstance(data, dict) else {})
        elif route.get("requires_stock"):
            stock = resolve_stock(route.get("stock_query") or text)
            if not stock.get("matched"):
                reply = response_composer.compose_unresolved(stock)
                return {"route": route, "stock": None, "reply": reply, "resolver": stock}
            stock_payload = _stock_payload(stock)
            symbol = str(stock["symbol"])
            route["symbols"] = [symbol]
            if intent == "limit_up_probability":
                data = analyze_limit_up_probability(symbol)
                reply = response_composer.compose_limit_up(data)
            elif intent == "portfolio":
                portfolio = route.get("portfolio") if isinstance(route.get("portfolio"), dict) else {}
                cost = float(portfolio.get("cost") or 0)
                shares = int(portfolio.get("shares") or 0)
                if cost <= 0 or shares <= 0:
                    reply = "我识别到你在问持仓，但还缺成本价或股数。你可以这样问：我300394成本330，100股，现在怎么办？"
                else:
                    data = engine_loader.safe_call(
                        engine_loader.portfolio_analyze,
                        symbol,
                        cost,
                        shares,
                        float(portfolio.get("available_cash") or 0),
                        0.3,
                        portfolio.get("risk_preference") or "稳健",
                    ).get("data")
                    reply = response_composer.compose_portfolio(data if isinstance(data, dict) else {})
            else:
                data = _analysis(symbol)
                if not data:
                    reply = "我识别到了你的问题，但行情数据源暂时不稳定，本次无法完成完整分析。你可以稍后再试。"
                else:
                    reply = response_composer.compose_stock_analysis(data, route)
        else:
            reply = response_composer.compose_unknown()
    except Exception:
        reply = "我识别到了你的问题，但行情数据源暂时不稳定，本次无法完成完整分析。你可以稍后再试。"

    if stock_payload:
        update_context(
            chat_id,
            user_id,
            last_stock=stock_payload,
            last_intent=intent,
            last_question=text,
            last_result_summary=reply[:300],
        )
    return {"route": route, "stock": stock_payload, "reply": reply}


def analyze_limit_up_probability(symbol: str) -> dict[str, Any]:
    data = _analysis(symbol)
    if not data:
        return {
            "symbol": symbol,
            "name": symbol,
            "current_price": 0,
            "limit_up_price": 0,
            "distance_to_limit_up_pct": 0,
            "limit_up_probability_score": 0,
            "probability_level": "较低",
            "key_positive_factors": [],
            "key_negative_factors": ["行情数据源暂时不可用"],
            "conclusion": "已识别到股票，但行情数据源暂时不可用，请稍后再试。",
            "trade_plan": {},
        }

    price = _num(data.get("price")) or 0.0
    change_pct = _num(data.get("change_pct")) or 0.0
    score = _num(data.get("score")) or 50.0
    limit_up_price = round(price * (1 + max(10 - change_pct, 0) / 100), 2) if price else 0.0
    distance = round(max(10 - change_pct, 0), 2)
    entry = data.get("entry_plan") if isinstance(data.get("entry_plan"), dict) else {}
    technical = data.get("technical") if isinstance(data.get("technical"), dict) else {}
    fund = data.get("fund_flow") if isinstance(data.get("fund_flow"), dict) else {}

    positives: list[str] = []
    negatives: list[str] = []
    if change_pct >= 5:
        positives.append("当前涨幅较强，短线资金关注度较高。")
    elif change_pct <= 0:
        negatives.append("当前涨幅不强，距离冲板需要更多资金推动。")
    if score >= 75:
        positives.append("综合评分较高，技术、资金或基本面至少有一项形成支撑。")
    elif score < 60:
        negatives.append("综合评分一般，短线冲板确定性不足。")
    if _num(fund.get("main_flow")) and (_num(fund.get("main_flow")) or 0) > 0:
        positives.append("主力资金呈净流入迹象。")
    else:
        negatives.append("未看到明确的主力持续净流入信号。")
    ma20 = _num(technical.get("ma20"))
    if ma20 and price > ma20:
        positives.append("当前价格站在 MA20 上方，趋势结构相对更强。")
    elif ma20:
        negatives.append("当前价格仍未有效站上 MA20，短线压力需要观察。")

    raw_score = score * 0.55 + max(min(change_pct, 10), -5) * 3 + (8 if positives else 0) - (6 if len(negatives) >= 2 else 0)
    probability_score = round(max(0, min(raw_score, 100)), 2)
    if probability_score >= 75:
        level = "偏高"
    elif probability_score >= 58:
        level = "中等"
    else:
        level = "较低"

    return {
        "symbol": data.get("symbol") or symbol,
        "name": data.get("name") or symbol,
        "current_price": price,
        "limit_up_price": limit_up_price,
        "distance_to_limit_up_pct": distance,
        "limit_up_probability_score": probability_score,
        "probability_level": level,
        "score": score,
        "breakout_price": round(price * 1.03, 2) if price else 0,
        "hold_price": round(price * 0.98, 2) if price else 0,
        "key_positive_factors": positives or ["暂未看到特别强的确定性利好，需看盘中资金。"],
        "key_negative_factors": negatives or ["如果冲高缩量或资金转弱，冲板难度会明显上升。"],
        "conclusion": "今天是否涨停不能确定，应重点观察成交量和主力资金持续性。",
        "trade_plan": {
            "first_buy_price": entry.get("first_buy_price") or round(price * 0.98, 2),
            "second_buy_price": entry.get("second_buy_price") or round(price * 0.95, 2),
            "stop_loss_price": entry.get("stop_loss_price") or round(price * 0.92, 2),
            "do_not_chase_above": round(price * 1.05, 2) if price else 0,
            "take_profit_price_1": entry.get("take_profit_price_1") or round(price * 1.08, 2),
        },
    }


def _analysis(symbol: str) -> dict[str, Any]:
    result = engine_loader.safe_call(engine_loader.analyze_stock, symbol)
    data = result.get("data") if result.get("success") else {}
    return data if isinstance(data, dict) else {}


def _limit_up_reply(data: dict[str, Any]) -> str:
    plan = data.get("trade_plan") if isinstance(data.get("trade_plan"), dict) else {}
    positives = data.get("key_positive_factors") or []
    negatives = data.get("key_negative_factors") or []
    return f"""📌 {data.get('name')} {data.get('symbol')} 涨停概率分析

当前价格：{_fmt(data.get('current_price'))}
距离涨停价：约 {_fmt(data.get('distance_to_limit_up_pct'))}%
涨停概率：{data.get('probability_level')}（评分 {_fmt(data.get('limit_up_probability_score'))}）
综合评分：{_fmt(data.get('score'))}

【有利因素】
{_numbered(positives)}

【不利因素】
{_numbered(negatives)}

【盘中关键观察】
1. 是否放量突破 {_fmt(data.get('breakout_price'))} 元
2. 主力资金是否继续流入
3. 是否站稳 {_fmt(data.get('hold_price'))} 元
4. 如果冲高回落，需要注意风险

【操作参考】
第一观察买点：{_fmt(plan.get('first_buy_price'))}
第二低吸买点：{_fmt(plan.get('second_buy_price'))}
不建议追高区：{_fmt(plan.get('do_not_chase_above'))} 元以上
止损参考：{_fmt(plan.get('stop_loss_price'))}

【最终结论】
今天是否涨停不能确定，但从技术面、资金面和市场情绪看，当前属于：“{data.get('probability_level')}”。
如果后续放量突破 {_fmt(data.get('breakout_price'))} 元且主力资金继续流入，冲板概率会提高；如果跌破 {_fmt(data.get('hold_price'))} 元，则短线走弱。

风险提示：仅供辅助分析，不构成投资建议。"""


def _operation_reply(data: dict[str, Any], intent: str, parsed: dict[str, Any]) -> str:
    entry = data.get("entry_plan") if isinstance(data.get("entry_plan"), dict) else {}
    conclusion = data.get("final_conclusion") if isinstance(data.get("final_conclusion"), dict) else {}
    advice = _operation_advice(data, intent)
    return f"""📌 {data.get('name')} {data.get('symbol')} 操作分析

当前价格：{_fmt(data.get('price'))}
综合评分：{_fmt(data.get('score'))}
建议：{advice}

【现在能不能买】
结论：{_buy_sentence(data, intent)}

【建仓参考】
第一手买入：{_fmt(entry.get('first_buy_price'))}
第二手买入：{_fmt(entry.get('second_buy_price'))}
止损价格：{_fmt(entry.get('stop_loss_price'))}
压力位：{_fmt(entry.get('take_profit_price_1'))}
目标位：{_fmt(entry.get('take_profit_price_2'))}

【为什么】
技术面：{_module_summary(data.get('technical_analysis'), '技术面暂时没有明显优势，先观察关键位置。')}
资金面：{_module_summary(data.get('fund_flow_analysis'), '资金面没有明确持续流入信号。')}
基本面：{_module_summary(data.get('fundamental_analysis'), '基本面以可取得的真实字段为准，不强行编造。')}
情绪面：{_module_summary(data.get('sentiment_analysis'), '消息面暂按中性处理。')}

【最终通俗结论】
{conclusion.get('summary') or data.get('final_reason') or '这只股票现在更适合按计划观察，不要因为短线波动一次性重仓。'}

风险提示：仅供辅助分析，不构成投资建议。"""


def _top10_reply() -> str:
    rows = engine_loader.safe_call(engine_loader.scan_top10, 10).get("data")
    if not isinstance(rows, list) or not rows:
        return "今日自动选股暂时没有可靠结果，请稍后再试。"
    lines = ["📊 今日AI自动选股 Top10"]
    for idx, row in enumerate(rows[:10], 1):
        lines.append(f"{idx}. {row.get('name') or '未知股票'} {row.get('symbol') or row.get('code')} | 价格 {_fmt(row.get('price'))} | 评分 {_fmt(row.get('score'))} | {row.get('recommendation') or 'BUY'}")
    return "\n".join(lines)


def _intraday_reply() -> str:
    data = engine_loader.safe_call(engine_loader.intraday_signal, None, 10).get("data")
    rows = data.get("signals") if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return "⚡ 盘中信号暂时没有可靠结果，请稍后再试。"
    lines = ["⚡ 盘中信号"]
    for row in rows[:10]:
        lines.append(f"- {row.get('name') or '未知股票'} {row.get('symbol') or row.get('code')} | 信号 {row.get('signal_type')} | 强度 {_fmt(row.get('signal_strength') or row.get('final_strength'))} | {row.get('reason') or '保持观察'}")
    return "\n".join(lines)


def _money_flow_reply() -> str:
    data = engine_loader.safe_call(engine_loader.moneyflow_anomaly, None, 10).get("data")
    rows = data.get("abnormal_stocks") or data.get("anomalies") if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return "💰 主力异动暂时没有可靠结果，请稍后再试。"
    lines = ["💰 主力异动监控"]
    for row in rows[:10]:
        lines.append(f"- {row.get('name') or '未知股票'} {row.get('symbol') or row.get('code')} | {row.get('anomaly_type')} | 强度 {row.get('intensity')} | {row.get('interpretation') or '暂无可靠说明'}")
    return "\n".join(lines)


def _market_overview_reply() -> str:
    data = engine_loader.safe_call(engine_loader.market_overview).get("data")
    if not isinstance(data, dict) or not data:
        return "大盘分析暂时没有可靠结果，请稍后再试。"
    hot = data.get("hot_sectors") or []
    if isinstance(hot, list):
        hot_text = "、".join(str(item.get("name") if isinstance(item, dict) else item) for item in hot[:6]) or "暂无可靠数据"
    else:
        hot_text = str(hot)
    return f"""📈 大盘分析

市场情绪：{data.get('market_sentiment') or '暂无可靠数据'}
风险偏好：{data.get('risk_appetite') or '暂无可靠数据'}
指数趋势：{data.get('index_trend') or '暂无可靠数据'}
热门板块：{hot_text}

通俗结论：如果市场情绪偏弱，短线不要追高；如果指数趋势和热门板块共振，再优先关注资金强、趋势强的标的。"""


def _unresolved_reply(stock: dict[str, Any]) -> str:
    candidates = stock.get("candidates") if isinstance(stock, dict) else []
    names = []
    if isinstance(candidates, list):
        names = [f"{item.get('name')}({item.get('symbol')})" for item in candidates[:3] if isinstance(item, dict)]
    suffix = "、".join(names) if names else "300394、600519、002130"
    return f"我没有准确识别到股票，你可以输入股票代码，例如 300394。你是不是想查：{suffix}？"


def _stock_payload(stock: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": stock.get("symbol"), "code": stock.get("code"), "name": stock.get("name")}


def _operation_advice(data: dict[str, Any], intent: str) -> str:
    score = _num(data.get("score")) or 50
    rec = str(data.get("recommendation") or "HOLD")
    if intent == "sell_or_hold" and rec == "SELL":
        return "减仓 / 止损"
    if intent == "add_position" and score >= 70:
        return "等回调分批加仓"
    if rec == "BUY" and score >= 75:
        return "分批建仓"
    if rec == "SELL" or score < 55:
        return "谨慎追高 / 控制风险"
    return "观察"


def _buy_sentence(data: dict[str, Any], intent: str) -> str:
    score = _num(data.get("score")) or 50
    if intent == "target_price":
        return "不要只看一个价格，优先等回踩到第一/第二买点附近，并确认资金没有明显流出。"
    if intent == "add_position":
        return "可以把加仓拆成小笔，只有站稳关键位且资金继续增强时再加，不适合一次性补满。"
    if score >= 75:
        return "可以关注，但更适合分批，不建议追高一把梭。"
    if score >= 60:
        return "可以观察，等回调到计划买点附近再考虑。"
    return "暂时不适合急着买，先等趋势和资金更明确。"


def _module_summary(value: Any, fallback: str) -> str:
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


def _numbered(items: list[Any]) -> str:
    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, 1))


def _fmt(value: Any) -> str:
    try:
        if value is None or value == "":
            return "暂无可靠数据"
        number = float(value)
        return f"{number:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value) if value else "暂无可靠数据"


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
