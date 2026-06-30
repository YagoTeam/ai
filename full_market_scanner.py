from __future__ import annotations

import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd
import requests

from data.provider import MarketDataProvider, normalize_symbol
from institutional_scoring_engine import score_stock
from market_scanning_engine import generated_a_share_codes, is_a_share_code
from risk_control_engine import assess_risk, filter_high_risk
from sector_rotation_engine import classify_sector, sector_rankings


<<<<<<< HEAD
_PROVIDER: MarketDataProvider | None = None
=======
provider = MarketDataProvider()
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b
SCAN_CACHE: dict[str, Any] = {"timestamp": 0.0, "rows": [], "universe_size": 0, "status": ""}
SCAN_CACHE_TTL = 300
PREFIXES = ("000", "002", "300", "600", "601", "603", "688")


<<<<<<< HEAD
def _provider() -> MarketDataProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = MarketDataProvider()
    return _PROVIDER


=======
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b
def scan_full_market_top10(limit: int = 10) -> list[dict[str, Any]]:
    if SCAN_CACHE["rows"] and time.time() - float(SCAN_CACHE["timestamp"]) < SCAN_CACHE_TTL:
        return [dict(row) for row in SCAN_CACHE["rows"][:limit]]

    rows = _fetch_eastmoney_full_market()
    status = "REAL"
    if not rows and SCAN_CACHE["rows"]:
        rows = [dict(row) for row in SCAN_CACHE["rows"]]
        status = "CACHE"
    if not rows:
        rows = _fetch_tencent_full_market()
        status = "REAL_TENCENT"
    if not rows:
        rows = _fetch_akshare_spot()
        status = "REAL_AKSHARE"
    if not rows and SCAN_CACHE["rows"]:
        rows = [dict(row) for row in SCAN_CACHE["rows"]]
        status = "CACHE"
    if not rows:
        return []

    rows = _prepare_v4_rows(rows)
    sector_stats = sector_rankings(rows)
    scored = [_score_snapshot(row, sector_stats) for row in rows]
    scored = [row for row in scored if row["recommendation"] == "BUY"]
    scored = filter_high_risk(scored)
    _mark_leaders(scored)
    scored.sort(key=lambda item: item["score"], reverse=True)
    top_rows = scored[:limit]
    for row in top_rows:
        row["scan_status"] = status
        row["universe_size"] = len(rows)
    SCAN_CACHE.update({"timestamp": time.time(), "rows": [dict(row) for row in top_rows], "universe_size": len(rows), "status": status})
    return top_rows


def _fetch_eastmoney_full_market() -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    page = 1
    page_size = 500
    while True:
        payload = _request_eastmoney_page(page, page_size)
        rows = ((payload.get("data") or {}).get("diff") or []) if payload else []
        if not rows:
            break
        all_rows.extend(_normalize_eastmoney_rows(rows))
        total = int((payload.get("data") or {}).get("total") or 0)
        if page * page_size >= total or page >= 20:
            break
        page += 1
    return all_rows


def _request_eastmoney_page(page: int, page_size: int) -> dict[str, Any] | None:
    params = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f2,f3,f5,f6,f9,f23,f100",
    }
    for _ in range(1):
        try:
            response = requests.get("https://push2.eastmoney.com/api/qt/clist/get", params=params, timeout=3)
            response.raise_for_status()
            return response.json()
        except Exception:
            time.sleep(0.2)
    return None


def _normalize_eastmoney_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows = []
    for row in rows:
        code = str(row.get("f12") or "").strip()
        if not is_a_share_code(code):
            continue
        price = _num(row.get("f2"))
        if price is None or price <= 0:
            continue
        normalized_rows.append(
            {
                "symbol": normalize_symbol(code),
                "name": str(row.get("f14") or ""),
                "price": price,
                "change_pct": _num(row.get("f3")),
                "volume": _num(row.get("f5")),
                "amount": _num(row.get("f6")),
                "pe": _num(row.get("f9")),
                "pb": _num(row.get("f23")),
                "industry": str(row.get("f100") or ""),
            }
        )
    return normalized_rows


def _fetch_akshare_spot() -> list[dict[str, Any]]:
    if os.getenv("MARKET_ENABLE_AK_FULL_SCAN") != "1":
        return []
    try:
<<<<<<< HEAD
        frame = _provider().stock_spot()
=======
        frame = provider.stock_spot()
>>>>>>> 2004d99fcefc2dc48ac49478e3bc432e5b7a1c6b
    except Exception:
        return []
    rows = []
    for _, row in frame.iterrows():
        symbol = str(row.get("code") or "")
        code = symbol.split(".")[0]
        if not is_a_share_code(code):
            continue
        price = _num(row.get("price"))
        if price is None or price <= 0:
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": str(row.get("name") or ""),
                "price": price,
                "change_pct": _num(row.get("change_pct")),
                "volume": _num(row.get("volume")),
                "amount": _num(row.get("amount")),
                "pe": None,
                "pb": None,
                "industry": "",
            }
        )
    return rows


def _fetch_tencent_full_market() -> list[dict[str, Any]]:
    codes = generated_a_share_codes()
    batches = [codes[index : index + 80] for index in range(0, len(codes), 80)]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(_fetch_tencent_batch, batch) for batch in batches]
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                continue
    return rows


def _fetch_tencent_batch(batch: list[str]) -> list[dict[str, Any]]:
    try:
        response = requests.get("https://web.sqt.gtimg.cn/q=" + ",".join(batch), timeout=3)
        response.raise_for_status()
        text = response.content.decode("gbk", errors="ignore")
    except Exception:
        return []
    rows = []
    for item in text.split(";"):
        if '="' not in item:
            continue
        payload = item.split('="', 1)[1].rsplit('"', 1)[0]
        fields = payload.split("~")
        if len(fields) < 39 or not fields[1] or not fields[2]:
            continue
        price = _num(fields[3])
        if price is None or price <= 0:
            continue
        rows.append(
            {
                "symbol": normalize_symbol(fields[2]),
                "name": fields[1],
                "price": price,
                "change_pct": _num(fields[32] if len(fields) > 32 else None),
                "volume": _num(fields[36] if len(fields) > 36 else None),
                "amount": _num(fields[37] if len(fields) > 37 else None),
                "pe": _num(fields[39] if len(fields) > 39 else None),
                "pb": _num(fields[46] if len(fields) > 46 else None),
                "industry": "",
            }
        )
    return rows


def _prepare_v4_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for row in rows:
        item = dict(row)
        item["sector"] = classify_sector(item)
        prepared.append(item)
    return prepared


def _score_snapshot(row: dict[str, Any], sector_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scoring = score_stock(row, sector_stats)
    risk = assess_risk({**row, **scoring})
    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "price": row["price"],
        "score": scoring["score"],
        "recommendation": scoring["recommendation"],
        "sector": row["sector"],
        "is_leader": False,
        "risk_level": risk["risk_level"],
        "risk_reasons": risk["risk_reasons"],
        "factor_scores": scoring["factor_scores"],
    }


def _mark_leaders(rows: list[dict[str, Any]]) -> None:
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sector = row.get("sector", {}).get("sub_industry") or "未分类"
        by_sector.setdefault(sector, []).append(row)
    for sector_rows in by_sector.values():
        sector_rows.sort(key=lambda item: item.get("score", 0), reverse=True)
        for row in sector_rows[:3]:
            row["is_leader"] = True


def _technical_score(row: dict[str, Any]) -> float:
    change_pct = _num(row.get("change_pct")) or 0.0
    return float(np.clip(50 + change_pct * 3, 0, 100))


def _fund_score(row: dict[str, Any]) -> float:
    amount = _num(row.get("amount")) or 0.0
    volume = _num(row.get("volume")) or 0.0
    activity = np.log10(max(amount, volume, 1))
    return float(np.clip(35 + activity * 5, 0, 100))


def _fundamental_score(row: dict[str, Any]) -> float:
    score = 50.0
    pe = _num(row.get("pe"))
    pb = _num(row.get("pb"))
    if pe is not None:
        score += 12 if 0 < pe <= 35 else -8 if pe > 80 or pe <= 0 else 2
    if pb is not None:
        score += 8 if 0 < pb <= 4 else -6 if pb > 8 or pb <= 0 else 1
    return float(np.clip(score, 0, 100))


def _num(value: Any) -> float | None:
    try:
        if pd.isna(value) or value in {"-", ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
