from __future__ import annotations

from typing import Any


def compose_stock_analysis(data: dict[str, Any], route: dict[str, Any]) -> str:
    entry = data.get("entry_plan") if isinstance(data.get("entry_plan"), dict) else {}
    conclusion = data.get("final_conclusion") if isinstance(data.get("final_conclusion"), dict) else {}
    return f"""📌 {data.get('name') or data.get('symbol')} {data.get('symbol')} 分析

【一句话结论】
{conclusion.get('summary') or data.get('final_reason') or _judgement(data)}

【当前情况】
现价：{_fmt(data.get('price'))}
综合评分：{_fmt(data.get('score'))}
风险等级：{data.get('risk_level') or '暂无可靠数据'}
趋势状态：{_module_summary(data.get('technical_analysis'), '趋势需要继续观察。')}

【关键原因】
1. 技术面：{_module_summary(data.get('technical_analysis'), '技术面暂时没有明显优势。')}
2. 资金面：{_module_summary(data.get('fund_flow_analysis'), '资金面未看到强持续流入信号。')}
3. 基本面：{_module_summary(data.get('fundamental_analysis'), '基本面以可取得真实字段为准。')}
4. 情绪面：{_module_summary(data.get('sentiment_analysis'), '消息面暂按中性处理。')}

【操作参考】
第一买点：{_fmt(entry.get('first_buy_price'))}
第二买点：{_fmt(entry.get('second_buy_price'))}
止损位：{_fmt(entry.get('stop_loss_price'))}
压力位：{_fmt(entry.get('take_profit_price_1'))}
目标位：{_fmt(entry.get('take_profit_price_2'))}

【我的判断】
这只股票不要只看一根K线。更稳的做法是看价格是否站稳关键买点，同时确认资金没有明显转弱；如果跌破止损位，要优先控制风险。

风险提示：仅供辅助分析，不构成投资建议。"""


def compose_limit_up(data: dict[str, Any]) -> str:
    plan = data.get("trade_plan") if isinstance(data.get("trade_plan"), dict) else {}
    return f"""📌 {data.get('name')} {data.get('symbol')} 涨停概率分析

当前价格：{_fmt(data.get('current_price'))}
距离涨停价：约 {_fmt(data.get('distance_to_limit_up_pct'))}%
涨停概率：{data.get('probability_level')}（评分 {_fmt(data.get('limit_up_probability_score'))}）
综合评分：{_fmt(data.get('score'))}

【有利因素】
{_numbered(data.get('key_positive_factors') or [])}

【不利因素】
{_numbered(data.get('key_negative_factors') or [])}

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
今天是否涨停不能确定。当前更适合理解为“{data.get('probability_level')}机会”，真正能不能冲板，要看盘中资金是否持续、成交量是否放大、冲高后能不能守住关键价位。

风险提示：仅供辅助分析，不构成投资建议。"""


def compose_top10(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "今日自动选股暂时没有可靠结果，请稍后再试。"
    lines = ["📊 今日AI自动选股 Top10"]
    for idx, row in enumerate(rows[:10], 1):
        reasons = row.get("reasons")
        reason = "；".join(str(item) for item in reasons[:2]) if isinstance(reasons, list) else row.get("final_reason") or "综合评分靠前，需结合风险位观察。"
        lines.append(
            f"\n{idx}. {row.get('name') or '未知股票'} {row.get('symbol') or row.get('code')}\n"
            f"现价：{_fmt(row.get('price'))}\n评分：{_fmt(row.get('score'))}\n建议：{row.get('recommendation') or 'BUY'}\n理由：{reason}"
        )
    return "\n".join(lines)


def compose_money_flow(data: dict[str, Any]) -> str:
    rows = data.get("abnormal_stocks") or data.get("anomalies") or []
    if not isinstance(rows, list) or not rows:
        return "💰 主力动向暂时没有可靠结果，请稍后再试。"
    lines = ["💰 主力动向"]
    for idx, row in enumerate(rows[:10], 1):
        direction = "主力流入" if (_num(row.get("money_flow_change")) or 0) > 0 else "主力流出/观望"
        lines.append(
            f"\n{idx}. {row.get('name') or '未知股票'} {row.get('symbol') or row.get('code')}\n"
            f"方向：{direction}\n强度：{row.get('intensity') or '暂无可靠数据'}\n原因：{row.get('interpretation') or row.get('action_signal') or '暂无可靠说明'}"
        )
    return "\n".join(lines)


def compose_intraday(data: dict[str, Any]) -> str:
    rows = data.get("signals") if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return "⚡ 盘中信号暂时没有可靠结果，请稍后再试。"
    lines = ["⚡ 盘中信号"]
    for idx, row in enumerate(rows[:10], 1):
        lines.append(
            f"\n{idx}. {row.get('name') or '未知股票'} {row.get('symbol') or row.get('code')}\n"
            f"信号：{row.get('signal_type') or row.get('raw_signal_type')}\n强度：{_fmt(row.get('signal_strength') or row.get('final_strength'))}\n原因：{row.get('reason') or '保持观察'}"
        )
    return "\n".join(lines)


def compose_market(data: dict[str, Any]) -> str:
    hot = data.get("hot_sectors") or []
    if isinstance(hot, list):
        hot_text = "、".join(str(item.get("name") if isinstance(item, dict) else item) for item in hot[:6]) or "暂无可靠数据"
    else:
        hot_text = str(hot)
    return f"""📈 大盘分析

市场情绪：{data.get('market_sentiment') or '暂无可靠数据'}
风险偏好：{data.get('risk_appetite') or '暂无可靠数据'}
热点方向：{hot_text}
指数趋势：{data.get('index_trend') or '暂无可靠数据'}

操作建议：市场强时优先看资金流入和趋势共振的方向；市场弱时不要追高，仓位要轻，先守风险位。"""


def compose_portfolio(data: dict[str, Any]) -> str:
    return f"""📌 {data.get('name') or data.get('symbol')} {data.get('symbol')} 持仓分析

当前价格：{_fmt(data.get('current_price'))}
成本价：{_fmt(data.get('cost_price'))}
持仓数量：{data.get('shares') or '暂无可靠数据'}
浮动盈亏：{_fmt(data.get('floating_profit'))}
盈亏比例：{_fmt(data.get('floating_profit_ratio'))}%

【操作建议】
{data.get('position_advice') or '继续观察'}

【关键价位】
补仓参考：{_fmt(data.get('add_position_price'))}
减仓参考：{_fmt(data.get('reduce_position_price'))}
止损参考：{_fmt(data.get('stop_loss_price'))}

【原因】
{data.get('reason') or '暂无可靠说明'}

【下一步】
{data.get('next_action') or '先观察价格是否站稳关键位，不要情绪化加仓。'}

风险提示：仅供辅助分析，不构成投资建议。"""


def compose_unresolved(resolver: dict[str, Any]) -> str:
    candidates = resolver.get("candidates") if isinstance(resolver, dict) else []
    if isinstance(candidates, list) and candidates:
        lines = ["我没有准确识别到股票。你是不是想查："]
        for idx, item in enumerate(candidates[:5], 1):
            lines.append(f"{idx}. {item.get('name')} {item.get('symbol')}")
        return "\n".join(lines)
    return "我没有准确识别到股票。你可以输入股票代码，例如 300394。"


def compose_unknown() -> str:
    return "我理解你是在问股票相关问题，但还差一个关键信息。你可以这样问：天孚通信今天会涨停吗？或者：推荐10个可以买的股票。"


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


def _judgement(data: dict[str, Any]) -> str:
    rec = data.get("recommendation") or "HOLD"
    score = _num(data.get("score")) or 50
    if rec == "BUY" and score >= 70:
        return "可以关注，但适合分批，不建议追高。"
    if rec == "SELL":
        return "风险偏高，优先控制仓位。"
    return "当前更适合观察，等趋势和资金更明确。"


def _numbered(items: list[Any]) -> str:
    if not items:
        return "1. 暂无特别明确的因素，需等待更多数据确认。"
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
