from __future__ import annotations

import time
from datetime import datetime
from typing import Any


_MEMORY: dict[str, dict[str, Any]] = {}
_TTL_SECONDS = 6 * 60 * 60


def memory_key(chat_id: str | None, user_id: str | None) -> str:
    return f"{chat_id or 'default_chat'}:{user_id or 'default_user'}"


def get_context(chat_id: str | None, user_id: str | None) -> dict[str, Any]:
    key = memory_key(chat_id, user_id)
    ctx = _MEMORY.get(key)
    if not ctx:
        return {}
    if time.time() - float(ctx.get("_ts") or 0) > _TTL_SECONDS:
        _MEMORY.pop(key, None)
        return {}
    return dict(ctx)


def update_context(
    chat_id: str | None,
    user_id: str | None,
    *,
    last_stock: dict[str, Any] | None = None,
    last_intent: str | None = None,
    last_question: str | None = None,
    last_result_summary: str | None = None,
) -> dict[str, Any]:
    key = memory_key(chat_id, user_id)
    ctx = _MEMORY.get(key, {}).copy()
    if last_stock:
        ctx["last_stock"] = {
            "symbol": last_stock.get("symbol"),
            "name": last_stock.get("name"),
            "code": last_stock.get("code"),
        }
    if last_intent:
        ctx["last_intent"] = last_intent
    if last_question:
        ctx["last_question"] = last_question
    if last_result_summary:
        ctx["last_result_summary"] = last_result_summary[:500]
    ctx["updated_at"] = datetime.utcnow().isoformat() + "Z"
    ctx["_ts"] = time.time()
    _MEMORY[key] = ctx
    return dict(ctx)
