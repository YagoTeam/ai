from __future__ import annotations

import base64
import hashlib
import os
import struct
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

from services import engine_loader


HELP_TEXT = """可用指令：
1. 分析 德明利
2. 300394
3. 自动分析
4. 盘中信号
5. 主力异动
6. 帮助"""

FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip() or "https://ai11.onrender.com"


@dataclass
class WeComMessage:
    to_user: str
    from_user: str
    content: str
    agent_id: str = ""


def parse_wecom_command(text: str) -> dict[str, str]:
    raw = str(text or "").strip()
    normalized = raw.lower().replace(" ", "")
    if not raw:
        return {"type": "help", "keyword": ""}

    if normalized in {"帮助", "菜单", "指令", "help"}:
        return {"type": "help", "keyword": ""}
    if normalized in {"自动分析", "今日选股", "top10", "推荐股票", "推荐股"}:
        return {"type": "top10", "keyword": ""}
    if normalized in {"盘中信号", "实时信号", "盯盘"}:
        return {"type": "intraday_signals", "keyword": ""}
    if normalized in {"主力异动", "资金异动", "资金流"}:
        return {"type": "money_flow_anomalies", "keyword": ""}

    for prefix in ["分析", "查", "股票"]:
        if raw.startswith(prefix):
            keyword = raw[len(prefix) :].strip()
            return {"type": "stock_analysis", "keyword": keyword or raw}

    return {"type": "stock_analysis", "keyword": raw}


def build_reply_for_text(text: str) -> str:
    command = parse_wecom_command(text)
    command_type = command["type"]
    if command_type == "help":
        return HELP_TEXT
    if command_type == "top10":
        return build_top10_reply()
    if command_type == "intraday_signals":
        return build_intraday_reply()
    if command_type == "money_flow_anomalies":
        return build_money_flow_reply()
    return build_stock_reply(command.get("keyword", ""))


def build_stock_reply(keyword: str) -> str:
    symbol = resolve_symbol(keyword)
    if not symbol:
        return "未找到该股票，请尝试输入股票代码，例如：\n300394\n600519\n002130"

    result = engine_loader.safe_call(engine_loader.analyze_stock, symbol)
    if not result.get("success") or not isinstance(result.get("data"), dict):
        return "分析失败，可能是数据源暂时不可用，请稍后再试。"

    data = result["data"]
    name = _text(data.get("name"), "未知股票")
    symbol = _text(data.get("symbol") or symbol)
    price = _fmt_num(data.get("price"))
    score = _fmt_num(data.get("score"))
    recommendation = _recommendation_cn(data.get("recommendation"))
    sector = _sector_text(data.get("sector"))
    risk = _risk_cn(data.get("risk_level"))
    entry = data.get("entry_plan") if isinstance(data.get("entry_plan"), dict) else {}

    return f"""📌 股票分析：{name} {symbol}

| 项目 | 结果 |
|---|---|
| 当前价格 | {price} |
| 综合评分 | {score} |
| 操作建议 | {recommendation} |
| 所属板块 | {sector} |
| 风险等级 | {risk} |

【四维分析】
技术面：{_module_summary(data.get("technical_analysis"), "暂无可靠技术面解释")}
资金面：{_module_summary(data.get("fund_flow_analysis"), "暂无可靠资金面解释")}
基本面：{_module_summary(data.get("fundamental_analysis"), "暂无可靠基本面解释")}
情绪面：{_module_summary(data.get("sentiment_analysis"), "暂无可靠情绪面解释")}

【建仓参考】
第一手买入：{_fmt_num(entry.get("first_buy_price"))}
第二手买入：{_fmt_num(entry.get("second_buy_price"))}
止损价格：{_fmt_num(entry.get("stop_loss_price"))}
第一止盈：{_fmt_num(entry.get("take_profit_price_1"))}
第二止盈：{_fmt_num(entry.get("take_profit_price_2"))}
建议仓位：{_text(entry.get("position_suggestion"), "暂无可靠数据")}

【最终结论】
{_final_conclusion_text(data)}

风险提示：仅供辅助分析，不构成投资建议。"""


def build_top10_reply(limit: int = 10) -> str:
    result = engine_loader.safe_call(engine_loader.scan_top10, limit)
    rows = result.get("data") if result.get("success") else []
    if not isinstance(rows, list) or not rows:
        return "今日自动选股暂时没有可靠结果，请稍后再试。"
    lines = ["📊 今日AI自动选股Top10"]
    for idx, row in enumerate(rows[:limit], start=1):
        lines.append(
            f"{idx}. {_text(row.get('name'), '未知股票')} {_text(row.get('symbol') or row.get('code'))}"
            f" | 价格 {_fmt_num(row.get('price'))} | 评分 {_fmt_num(row.get('score'))}"
            f" | {_text(row.get('recommendation'), 'BUY')}"
        )
    lines.append(f"\n点击网站查看详情：{FRONTEND_URL}")
    return "\n".join(lines)


def build_intraday_reply(limit: int = 10) -> str:
    result = engine_loader.safe_call(engine_loader.intraday_signal, None, limit)
    data = result.get("data") if result.get("success") else {}
    rows = data.get("signals") if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return "⚡ 盘中信号暂时没有可靠结果，请稍后再试。"
    lines = ["⚡ 盘中信号"]
    for row in rows[:limit]:
        lines.append(
            f"- {_text(row.get('name'), '未知股票')} {_text(row.get('symbol') or row.get('code'))}"
            f" | 信号 {_signal_cn(row.get('signal_type') or row.get('raw_signal_type'))}"
            f" | 强度 {_fmt_num(row.get('signal_strength') or row.get('final_strength'))}"
            f" | 原因 {_text(row.get('reason'), '保持观察')}"
        )
    return "\n".join(lines)


def build_money_flow_reply(limit: int = 10) -> str:
    result = engine_loader.safe_call(engine_loader.moneyflow_anomaly, None, limit)
    data = result.get("data") if result.get("success") else {}
    rows = data.get("abnormal_stocks") or data.get("anomalies") if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return "💰 主力异动暂时没有可靠结果，请稍后再试。"
    lines = ["💰 主力异动监控"]
    for row in rows[:limit]:
        lines.append(
            f"- {_text(row.get('name'), '未知股票')} {_text(row.get('symbol') or row.get('code'))}"
            f" | {_anomaly_cn(row.get('anomaly_type'))}"
            f" | 强度 {_text(row.get('intensity'), 'LOW')}"
            f" | 资金变化 {_fmt_num(row.get('money_flow_change'))}"
            f" | {_text(row.get('interpretation'), '暂无可靠说明')}"
        )
    return "\n".join(lines)


def resolve_symbol(keyword: str) -> str | None:
    from services.stock_resolver import resolve_stock

    result = resolve_stock(keyword)
    return result.get("symbol") if result.get("matched") else None


def parse_callback_xml(raw_body: bytes) -> WeComMessage:
    root = ET.fromstring(raw_body)
    encrypted = _find_text(root, "Encrypt")
    if encrypted:
        plain = decrypt_message(encrypted)
        root = ET.fromstring(plain)
    return WeComMessage(
        to_user=_find_text(root, "ToUserName"),
        from_user=_find_text(root, "FromUserName"),
        content=_find_text(root, "Content"),
        agent_id=_find_text(root, "AgentID"),
    )


def extract_encrypt(raw_body: bytes) -> str:
    root = ET.fromstring(raw_body)
    return _find_text(root, "Encrypt")


def verify_url(echostr: str) -> str:
    if not echostr:
        return ""
    return decrypt_message(echostr)


def verify_signature(msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
    expected = _signature(timestamp, nonce, encrypted)
    return bool(msg_signature) and expected == msg_signature


def build_passive_text_response(message: WeComMessage, content: str, encrypt: bool = True) -> str:
    now = int(time.time())
    plain = (
        "<xml>"
        f"<ToUserName><![CDATA[{message.from_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{message.to_user}]]></FromUserName>"
        f"<CreateTime>{now}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{_clip(content, 1800)}]]></Content>"
        "</xml>"
    )
    if encrypt and _aes_key():
        encrypted = encrypt_message(plain)
        nonce = str(now)
        sign = _signature(str(now), nonce, encrypted)
        return (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypted}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{sign}]]></MsgSignature>"
            f"<TimeStamp>{now}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )
    return plain


def push_group_markdown(content: str) -> bool:
    webhook = os.getenv("WECOM_GROUP_WEBHOOK", "").strip()
    if not webhook:
        return False
    try:
        response = requests.post(
            webhook,
            json={"msgtype": "markdown", "markdown": {"content": _clip(content, 3900)}},
            timeout=8,
        )
        return response.ok
    except Exception:
        return False


def has_group_webhook() -> bool:
    return bool(os.getenv("WECOM_GROUP_WEBHOOK", "").strip())


def build_async_and_push(text: str) -> None:
    reply = build_reply_for_text(text)
    push_group_markdown(reply)


def test_command(text: str) -> dict[str, str]:
    command = parse_wecom_command(text)
    return {
        "command_type": command["type"],
        "keyword": command.get("keyword", ""),
        "reply_preview": build_reply_for_text(text),
    }


def decrypt_message(encrypted: str) -> str:
    key = _aes_key()
    if not key:
        raise ValueError("WECOM_AES_KEY is not configured")
    cipher = _new_cipher(key)
    plain = cipher.decrypt(base64.b64decode(encrypted))
    plain = _pkcs7_unpad(plain)
    msg_len = struct.unpack(">I", plain[16:20])[0]
    message = plain[20 : 20 + msg_len].decode("utf-8")
    corp_id = plain[20 + msg_len :].decode("utf-8")
    expected = os.getenv("WECOM_CORP_ID", "").strip()
    if expected and corp_id != expected:
        raise ValueError("WECOM_CORP_ID does not match decrypted message")
    return message


def encrypt_message(message: str) -> str:
    key = _aes_key()
    if not key:
        raise ValueError("WECOM_AES_KEY is not configured")
    corp_id = os.getenv("WECOM_CORP_ID", "").strip()
    raw = os.urandom(16) + struct.pack(">I", len(message.encode("utf-8"))) + message.encode("utf-8") + corp_id.encode("utf-8")
    cipher = _new_cipher(key)
    return base64.b64encode(cipher.encrypt(_pkcs7_pad(raw))).decode("utf-8")


def _signature(timestamp: str, nonce: str, encrypted: str) -> str:
    token = os.getenv("WECOM_TOKEN", "").strip()
    parts = sorted([token, str(timestamp or ""), str(nonce or ""), str(encrypted or "")])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


def _aes_key() -> bytes | None:
    raw = os.getenv("WECOM_AES_KEY", "").strip()
    if not raw:
        return None
    return base64.b64decode(raw + "=")


def _new_cipher(key: bytes) -> Any:
    from Crypto.Cipher import AES

    return AES.new(key, AES.MODE_CBC, key[:16])


def _pkcs7_pad(data: bytes) -> bytes:
    block_size = 32
    amount = block_size - (len(data) % block_size)
    return data + bytes([amount]) * amount


def _pkcs7_unpad(data: bytes) -> bytes:
    amount = data[-1]
    if amount < 1 or amount > 32:
        raise ValueError("invalid pkcs7 padding")
    return data[:-amount]


def _find_text(root: ET.Element, tag: str) -> str:
    node = root.find(tag)
    return node.text if node is not None and node.text is not None else ""


def _module_summary(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        for key in ["explanation", "trend_judgement", "long_short_balance", "valuation_summary", "market_impact", "summary"]:
            if value.get(key):
                return _text(value.get(key), fallback)
        for item in value.values():
            if isinstance(item, str) and item:
                return item
    if isinstance(value, str) and value:
        return value
    return fallback


def _final_conclusion_text(data: dict[str, Any]) -> str:
    conclusion = data.get("final_conclusion")
    if isinstance(conclusion, dict):
        return _text(conclusion.get("summary") or conclusion.get("judgement"), _text(data.get("final_reason"), "暂无可靠结论"))
    return _text(data.get("final_reason"), "暂无可靠结论")


def _sector_text(value: Any) -> str:
    if isinstance(value, dict):
        industry = value.get("industry") or value.get("sector")
        sub = value.get("sub_industry") or value.get("concept")
        return " / ".join(str(item) for item in [industry, sub] if item) or "暂无可靠数据"
    return _text(value, "暂无可靠数据")


def _recommendation_cn(value: Any) -> str:
    mapping = {"BUY": "买入观察", "HOLD": "继续观察", "SELL": "减仓规避"}
    return mapping.get(str(value or "").upper(), _text(value, "继续观察"))


def _risk_cn(value: Any) -> str:
    mapping = {"LOW": "低风险", "MEDIUM": "中等风险", "HIGH": "高风险"}
    return mapping.get(str(value or "").upper(), _text(value, "暂无可靠数据"))


def _signal_cn(value: Any) -> str:
    mapping = {"BUY": "买入观察", "SELL": "卖出预警", "HOLD": "继续观察", "BREAKOUT": "突破", "ACCUMULATION": "吸筹", "DISTRIBUTION": "派发", "PANIC SELL": "恐慌抛售"}
    return mapping.get(str(value or "").upper(), _text(value, "继续观察"))


def _anomaly_cn(value: Any) -> str:
    mapping = {
        "SURGE_INFLOW": "主力突击流入",
        "EXIT": "主力撤退",
        "WASH_TRADING": "疑似对倒",
        "PRE_BREAKOUT": "拉升前兆",
        "NORMAL": "暂无明显异动",
    }
    return mapping.get(str(value or "").upper(), _text(value, "资金异动"))


def _fmt_num(value: Any) -> str:
    try:
        if value is None or value == "":
            return "暂无可靠数据"
        number = float(value)
        return f"{number:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _text(value, "暂无可靠数据")


def _text(value: Any, fallback: str = "暂无可靠数据") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _clip(text: str, limit: int) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[: limit - 12] + "\n...(已截断)"
