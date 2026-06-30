from __future__ import annotations

from typing import Any


PREFIXES = ("000", "002", "300", "600", "601", "603", "688")


def is_a_share_code(code: str) -> bool:
    return str(code or "").startswith(PREFIXES)


def generated_a_share_codes() -> list[str]:
    codes: list[str] = []
    for prefix in PREFIXES:
        for suffix in range(1000):
            code = f"{prefix}{suffix:03d}"
            market = "sh" if code.startswith("6") else "sz"
            codes.append(f"{market}{code}")
    return codes


def normalize_universe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "price": row.get("price"),
        "change_pct": row.get("change_pct"),
        "volume": row.get("volume"),
        "amount": row.get("amount"),
        "pe": row.get("pe"),
        "pb": row.get("pb"),
        "turnover": row.get("turnover"),
        "market_cap": row.get("market_cap"),
        "industry": row.get("industry") or "",
    }

