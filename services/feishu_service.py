from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from services import conversation_memory


HELP_TEXT = """可用指令：
1. @小牛牛 德明利
2. @小牛牛 300394
3. @小牛牛 自动分析
4. @小牛牛 盘中信号
5. @小牛牛 主力异动
6. @小牛牛 天孚通信今天会涨停吗？
7. @小牛牛 贵州茅台跌到多少可以买？"""

_TOKEN_CACHE: dict[str, Any] = {"token": "", "expire_at": 0.0}


def handle_message_event(body: dict[str, Any]) -> None:
    parsed = parse_message_event(body)
    message_id = parsed.get("message_id", "")
    clean_text = parsed.get("clean_text", "")
    chat_id = parsed.get("chat_id", "")
    user_id = parsed.get("user_id", "")
    print(f"Feishu clean_text: {clean_text}", flush=True)

    if not message_id:
        print("Feishu reply failed: missing message_id", flush=True)
        return

    if clean_text in {"帮助", "菜单", "指令", "help", ""}:
        reply_feishu_message(message_id, HELP_TEXT)
        return

    reply_feishu_message(message_id, f"已收到：{clean_text}\n正在分析，请稍等。")

    try:
        from services import nlp_query_service

        context = conversation_memory.get_context(chat_id, user_id)
        result = nlp_query_service.answer_user_question(clean_text, context=context, chat_id=chat_id, user_id=user_id)
        analysis_reply = result.get("reply") if isinstance(result, dict) else ""
        if analysis_reply:
            reply_feishu_message(message_id, analysis_reply)
    except Exception as exc:
        print(f"Feishu reply failed: analysis error: {exc}", flush=True)
        reply_feishu_message(message_id, "分析失败，可能是数据源暂时不可用，请稍后再试。")


def parse_message_event(body: dict[str, Any]) -> dict[str, str]:
    event = body.get("event") if isinstance(body.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    message_id = str(message.get("message_id") or "")
    chat_id = str(message.get("chat_id") or "")
    user_id = str(sender_id.get("open_id") or sender_id.get("user_id") or "")
    text = _content_text(message.get("content"))
    for key in _mention_keys(message):
        text = text.replace(key, "")
    text = re.sub(r"^@\S+\s*", "", text).strip()
    return {"message_id": message_id, "clean_text": " ".join(text.split()).strip(), "chat_id": chat_id, "user_id": user_id}


def get_feishu_tenant_access_token() -> str | None:
    now = time.time()
    cached = str(_TOKEN_CACHE.get("token") or "")
    if cached and now < float(_TOKEN_CACHE.get("expire_at") or 0):
        print("Feishu token ok", flush=True)
        return cached

    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Feishu token failed: FEISHU_APP_ID or FEISHU_APP_SECRET is missing", flush=True)
        return None

    try:
        response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=8,
        )
        data = response.json()
        token = data.get("tenant_access_token")
        if not response.ok or not token:
            print(f"Feishu token failed: status={response.status_code}, body={_clip(str(data), 500)}", flush=True)
            return None
        expire = int(data.get("expire") or 7000)
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expire_at"] = now + max(expire - 120, 60)
        print("Feishu token ok", flush=True)
        return token
    except Exception as exc:
        print(f"Feishu token failed: {exc}", flush=True)
        return None


def reply_feishu_message(message_id: str, text: str) -> bool:
    token = get_feishu_tenant_access_token()
    if not token:
        print("Feishu reply failed: no tenant_access_token", flush=True)
        return False

    try:
        response = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"msg_type": "text", "content": json.dumps({"text": _clip(text, 3500)}, ensure_ascii=False)},
            timeout=8,
        )
        print(f"Feishu reply status: {response.status_code}", flush=True)
        print(f"Feishu reply body: {_clip(response.text, 1000)}", flush=True)
        return response.ok
    except Exception as exc:
        print(f"Feishu reply failed: {exc}", flush=True)
        return False


def _content_text(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if not isinstance(content, str):
        return ""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return str(parsed.get("text") or "")
    except json.JSONDecodeError:
        pass
    return content


def _mention_keys(message: dict[str, Any]) -> list[str]:
    mentions = message.get("mentions")
    if not isinstance(mentions, list):
        return []
    keys: list[str] = []
    for item in mentions:
        if isinstance(item, dict) and item.get("key"):
            keys.append(str(item["key"]))
    return keys


def _clip(text: str, limit: int) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[: limit - 12] + "\n...(已截断)"
