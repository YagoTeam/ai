from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

from services import engine_loader


CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "a_stock_list_cache.json"
CACHE_TTL = 24 * 60 * 60

TYPO_REPLACEMENTS = {
    "通讯": "通信",
    "德明力": "德明利",
    "茅台酒": "茅台",
}


def resolve_stock(query: str) -> dict[str, Any]:
    text = _normalize_query(query)
    if not text:
        return _unmatched("empty", [])

    stocks = _load_stock_dictionary()
    if not stocks:
        return _unmatched("stock dictionary unavailable", [])

    code = _extract_code(text)
    if code:
        for stock in stocks:
            if stock["code"] == code:
                return _matched(stock, 1.0, "code", [])

    normalized_text = _apply_typos(text)
    compact_text = _compact(normalized_text)

    exact = _exact_match(compact_text, stocks)
    if exact:
        return exact

    candidates = _rank_candidates(compact_text, stocks)
    if not candidates:
        return _unmatched("not_found", [])

    best = candidates[0]
    if best["score"] >= 0.78 and (len(candidates) == 1 or best["score"] - candidates[1]["score"] >= 0.06):
        stock = {"symbol": best["symbol"], "code": best["code"], "name": best["name"]}
        return _matched(stock, best["score"], best["match_type"], candidates[:5])

    return _unmatched("ambiguous", candidates[:5])


def _load_stock_dictionary() -> list[dict[str, Any]]:
    cached = _read_cache()
    if cached:
        return cached
    if not _refresh_on_request():
        return _seed_rows()
    rows = _fetch_stock_rows()
    if rows:
        _write_cache(rows)
        return rows
    return _read_cache(ignore_ttl=True) or _seed_rows()


def _fetch_stock_rows() -> list[dict[str, Any]]:
    records = _fetch_eastmoney_stock_list()
    if records:
        return _build_rows(records)
    if not _allow_slow_stock_master():
        return []
    try:
        frame = engine_loader.get_provider().stock_master()
        records = frame.to_dict(orient="records")
    except Exception:
        records = []
    return _build_rows(records)


def _fetch_eastmoney_stock_list() -> list[dict[str, str]]:
    try:
        response = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1,
                "pz": 10000,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14",
            },
            timeout=8,
        )
        data = response.json()
        diff = data.get("data", {}).get("diff", [])
        rows = []
        for item in diff:
            code = str(item.get("f12") or "").strip()
            name = str(item.get("f14") or "").strip()
            if code and name:
                rows.append({"code": code, "name": name})
        return rows
    except Exception:
        return []


def _allow_slow_stock_master() -> bool:
    import os

    return os.getenv("STOCK_RESOLVER_ALLOW_SLOW_AKSHARE") == "1"


def _refresh_on_request() -> bool:
    import os

    return os.getenv("STOCK_RESOLVER_REFRESH_ON_REQUEST") == "1"


def _build_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in records:
        symbol = str(row.get("code") or row.get("symbol") or "").strip()
        name = str(row.get("name") or "").strip()
        if not symbol or not name:
            continue
        try:
            normalized = engine_loader.normalize_symbol(symbol)
        except Exception:
            normalized = symbol
        code, exchange = normalized.split(".", 1) if "." in normalized else (normalized[-6:], "")
        pinyin, initials = _pinyin(name)
        aliases = _aliases(name)
        rows.append(
            {
                "symbol": normalized,
                "code": code,
                "name": name,
                "exchange": exchange,
                "pinyin": pinyin,
                "pinyin_initial": initials,
                "common_alias": aliases,
            }
        )
    return rows


def _seed_rows() -> list[dict[str, Any]]:
    records = [
        {"code": "300394", "name": "天孚通信"},
        {"code": "001309", "name": "德明利"},
        {"code": "600519", "name": "贵州茅台"},
        {"code": "300750", "name": "宁德时代"},
    ]
    return _build_rows(records)


def _read_cache(ignore_ttl: bool = False) -> list[dict[str, Any]]:
    try:
        if not CACHE_PATH.exists():
            return []
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not ignore_ttl and time.time() - float(payload.get("updated_at") or 0) > CACHE_TTL:
            return []
        rows = payload.get("stocks")
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _write_cache(rows: list[dict[str, Any]]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"updated_at": time.time(), "stocks": rows}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _exact_match(text: str, stocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for stock in stocks:
        if text == stock["code"] or text == _compact(stock["symbol"]):
            return _matched(stock, 1.0, "code", [])
        if text == _compact(stock["name"]):
            return _matched(stock, 1.0, "name", [])
        if text in {_compact(alias) for alias in stock.get("common_alias", [])}:
            return _matched(stock, 0.96, "exact", [])
    for stock in stocks:
        name = _compact(stock["name"])
        if name and name in text:
            return _matched(stock, 0.94, "context", [])
    return None


def _rank_candidates(text: str, stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    tokens = _tokens(text)
    for stock in stocks:
        name = _compact(stock["name"])
        aliases = [_compact(alias) for alias in stock.get("common_alias", []) if alias]
        pinyin = str(stock.get("pinyin") or "")
        initials = str(stock.get("pinyin_initial") or "")
        best_score = 0.0
        match_type = "fuzzy"

        search_terms = [text, *tokens]
        for term in search_terms:
            if not term:
                continue
            if term in name or name in term:
                score = min(0.92, 0.62 + min(len(term), len(name)) / max(len(name), 1) * 0.3)
                if score > best_score:
                    best_score, match_type = score, "context"
            for alias in aliases:
                if alias and (term in alias or alias in term):
                    score = min(0.9, 0.58 + min(len(term), len(alias)) / max(len(alias), 1) * 0.28)
                    if score > best_score:
                        best_score, match_type = score, "fuzzy"
            ratio = SequenceMatcher(None, term, name).ratio()
            if ratio > best_score:
                best_score, match_type = ratio, "fuzzy"
            if term.isascii() and (term == initials or term == pinyin or initials.startswith(term) or pinyin.startswith(term)):
                score = 0.88 if term == initials else 0.76
                if score > best_score:
                    best_score, match_type = score, "pinyin"

        if best_score >= 0.55:
            candidates.append(
                {
                    "symbol": stock["symbol"],
                    "code": stock["code"],
                    "name": stock["name"],
                    "score": round(best_score, 4),
                    "match_type": match_type,
                }
            )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def _matched(stock: dict[str, Any], score: float, match_type: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "matched": True,
        "symbol": stock.get("symbol") or stock.get("code"),
        "code": stock.get("code") or str(stock.get("symbol", ""))[:6],
        "name": stock.get("name", ""),
        "match_score": round(score, 4),
        "match_type": match_type,
        "candidates": candidates,
    }


def _unmatched(reason: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"matched": False, "reason": reason, "candidates": candidates}


def _normalize_query(query: str) -> str:
    return str(query or "").strip().upper().replace("。", "").replace("？", "").replace("?", "")


def _apply_typos(text: str) -> str:
    value = text
    for src, dst in TYPO_REPLACEMENTS.items():
        value = value.replace(src, dst)
    return value


def _compact(text: str) -> str:
    return re.sub(r"[\s,，。！？?、:：;；()（）【】\[\]{}<>《》\"'“”‘’]", "", str(text or "").upper())


def _extract_code(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{6})(?:\.(?:SZ|SH))?(?!\d)", text.upper())
    return match.group(1) if match else None


def _tokens(text: str) -> list[str]:
    raw = _compact(text)
    chunks = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Z]{2,10}|\d{6}", raw)
    noise = {"今天", "现在", "还能", "可以买", "适合", "加仓", "怎么看", "会涨停吗", "涨停", "目标价", "支撑位", "压力位"}
    return [chunk for chunk in chunks if chunk and chunk not in noise]


def _aliases(name: str) -> list[str]:
    aliases = {name}
    for suffix in ["股份", "科技", "集团", "控股", "通信", "电子", "生物", "能源"]:
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            aliases.add(name[: -len(suffix)])
    aliases.add(name.replace("通信", "通讯"))
    aliases.add(name.replace("利", "力"))
    aliases.add(name.replace("茅台", "茅台酒"))
    return sorted(alias for alias in aliases if alias)


def _pinyin(name: str) -> tuple[str, str]:
    try:
        from pypinyin import Style, lazy_pinyin

        full = "".join(lazy_pinyin(name, errors="ignore"))
        initials = "".join(lazy_pinyin(name, style=Style.FIRST_LETTER, errors="ignore"))
        return full.upper(), initials.upper()
    except Exception:
        return "", ""
