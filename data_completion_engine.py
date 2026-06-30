from __future__ import annotations

from typing import Any

import numpy as np

from data.provider import DataProviderError, normalize_symbol
from data_aggregator import get_full_stock_data
from data_schema import metric


def get_complete_stock_data(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    raw = get_full_stock_data(normalized)
    price_data = _complete_price_data(raw.get("price_data", {}), raw.get("technical_data", {}), normalized)
    technical_data = _complete_technical_data(raw.get("technical_data", {}), price_data, normalized)
    fund_flow_data = _complete_fund_flow_data(raw.get("fund_flow_data", {}), price_data, technical_data)
    fundamental_data = _complete_fundamental_data(raw.get("fundamental_data", {}), price_data, normalized)
    sentiment_data = _complete_sentiment_data(raw.get("sentiment_data", {}), price_data, technical_data)
    modules = [price_data, technical_data, fund_flow_data, fundamental_data, sentiment_data]
    data_status = "COMPLETE" if all(item.get("status") == "OK" for item in modules) else "PARTIAL"
    price_data = _standardize_price_data(price_data)
    technical_data = _standardize_technical_data(technical_data)
    fund_flow_data = _standardize_fund_flow_data(fund_flow_data)
    fundamental_data = _standardize_fundamental_data(fundamental_data)
    sentiment_data = _standardize_sentiment_data(sentiment_data)
    return {
        "symbol": normalized,
        "price_data": price_data,
        "technical_data": technical_data,
        "fund_flow_data": fund_flow_data,
        "fundamental_data": fundamental_data,
        "sentiment_data": sentiment_data,
        "data_status": data_status,
        "completion_notes": [item.get("message", "") for item in modules if item.get("status") != "OK" and item.get("message")],
    }


def _complete_price_data(price: dict[str, Any], technical: dict[str, Any], symbol: str) -> dict[str, Any]:
    completed = dict(price or {})
    bars = technical.get("bars") or []
    latest_bar = bars[-1] if bars else {}
    if completed.get("price") is None and latest_bar.get("close") is not None:
        completed["price"] = latest_bar.get("close")
        completed["status"] = "COMPLETED"
        completed["source"] = "latest K-line close"
        completed["message"] = "price completed from latest K-line close"
    if completed.get("volume") is None and latest_bar.get("volume") is not None:
        completed["volume"] = latest_bar.get("volume")
    if completed.get("change_pct") is None and latest_bar.get("change_pct") is not None:
        completed["change_pct"] = latest_bar.get("change_pct")
    completed.setdefault("status", "OK" if completed.get("price") is not None else "COMPLETED")
    completed.setdefault("source", "aggregated quote/K-line")
    completed.setdefault("message", "")
    completed.setdefault("symbol", symbol)
    completed.setdefault("name", symbol)
    if completed.get("price") is None:
        raise DataProviderError(f"price cannot be completed for {symbol}")
    completed["data_source"] = "REAL"
    return completed


def _complete_technical_data(technical: dict[str, Any], price: dict[str, Any], symbol: str) -> dict[str, Any]:
    completed = dict(technical or {})
    if completed.get("ma5") is not None and completed.get("macd") and completed.get("rsi") is not None:
        completed.setdefault("status", "OK")
        completed.setdefault("source", "aggregated K-line")
        completed.setdefault("message", "")
        completed["data_source"] = "REAL"
        return completed

    current_price = _num(price.get("price"))
    if current_price is None:
        raise DataProviderError(f"technical data cannot be completed for {symbol}: missing price")
    raise DataProviderError(f"technical indicators cannot be estimated for {symbol}: real K-line indicators required")


def _complete_fund_flow_data(fund_flow: dict[str, Any], price: dict[str, Any], technical: dict[str, Any]) -> dict[str, Any]:
    completed = dict(fund_flow or {})
    amount = _num(price.get("amount"))
    if amount is None:
        amount = (_num(price.get("price")) or 0.0) * (_num(price.get("volume")) or 0.0)
    if completed.get("status") == "OK" and any(completed.get(key) is not None for key in ["main_flow", "large_order", "super_order"]):
        raw_values = {key: _num(completed.get(key)) for key in ["main_flow", "large_order", "super_order"]}
        if amount:
            for key, value in raw_values.items():
                completed[key] = round(value / amount, 6) if value is not None else None
            completed["normalization"] = "flow / traded_amount"
            completed["raw_values"] = raw_values
        completed["data_source"] = "REAL"
        return completed

    change_pct = _num(price.get("change_pct")) or 0.0
    volume_change = _num(technical.get("volume_change")) or 0.0
    direction = 1 if change_pct > 0 else -1 if change_pct < 0 else 0
    intensity = min(1.0, abs(change_pct) / 10 + max(volume_change, 0) * 0.5)
    proxy_main_ratio = direction * intensity * 0.08
    completed.update(
        {
            "status": "COMPLETED",
            "data_source": "ESTIMATED",
            "source": "price-volume fund-flow proxy",
            "message": "fund flow completed by normalized proxy using price change, volume change, and traded amount",
            "main_flow": round(proxy_main_ratio, 6),
            "large_order": round(proxy_main_ratio * 0.45, 6),
            "super_order": round(proxy_main_ratio * 0.25, 6),
            "normalization": "proxy_flow / traded_amount",
            "proxy_inputs": {
                "change_pct": change_pct,
                "volume_change": volume_change,
                "amount": round(amount, 2),
                "raw_proxy_amount": round(amount * proxy_main_ratio, 2),
            },
        }
    )
    return completed


def _complete_fundamental_data(fundamental: dict[str, Any], price: dict[str, Any], symbol: str) -> dict[str, Any]:
    completed = dict(fundamental or {})
    if completed.get("pe") is None and _num(price.get("pe")) is not None:
        completed["pe"] = _num(price.get("pe"))
    if completed.get("pb") is None and _num(price.get("pb")) is not None:
        completed["pb"] = _num(price.get("pb"))
    if completed.get("status") == "OK" and all(completed.get(key) is not None for key in ["pe", "pb", "roe", "revenue_growth"]):
        completed["data_source"] = "REAL"
        completed["estimated"] = {}
        return completed

    sector = _infer_sector(symbol)
    averages = _sector_average(sector)
    estimated = {
        "pe": averages["pe"] if completed.get("pe") is None else None,
        "pb": averages["pb"] if completed.get("pb") is None else None,
        "roe": averages["roe"] if completed.get("roe") is None else None,
        "revenue_growth": averages["revenue_growth"] if completed.get("revenue_growth") is None else None,
    }
    estimated = {key: value for key, value in estimated.items() if value is not None}
    completed.update(
        {
            "status": "COMPLETED",
            "data_source": "ESTIMATED",
            "source": "sector-average fundamental completion",
            "message": f"fundamental data completed with real quote valuation when available and {sector} sector averages only for missing fields; estimates do not overwrite real financial fields",
            "sector": sector,
            "pe": completed.get("pe"),
            "pb": completed.get("pb"),
            "roe": completed.get("roe"),
            "revenue_growth": completed.get("revenue_growth"),
            "estimated": estimated,
            "completion_method": "industry average estimate; does not overwrite real financial fields",
        }
    )
    estimated_pe = estimated.get("pe")
    if completed.get("eps") is None and estimated_pe not in (None, 0):
        completed["estimated_eps"] = round((_num(price.get("price")) or 0) / float(estimated_pe), 4)
    return completed


def _complete_sentiment_data(sentiment: dict[str, Any], price: dict[str, Any], technical: dict[str, Any]) -> dict[str, Any]:
    completed = dict(sentiment or {})
    if completed.get("status") == "OK":
        completed["data_source"] = "AI_INFERRED"
        return completed

    change_abs = abs(_num(price.get("change_pct")) or 0.0)
    volume_abs = abs(_num(technical.get("volume_change")) or 0.0)
    volatility_proxy = min(1.0, change_abs / 10 + volume_abs * 0.25)
    confidence = round(float(np.clip(0.3 + volatility_proxy * 0.25, 0.3, 0.55)), 2)
    completed.update(
        {
            "status": "COMPLETED",
            "data_source": "AI_INFERRED",
            "source": "neutral sentiment + volatility proxy",
            "message": "sentiment completed with neutral baseline and volatility proxy because news source was unavailable",
            "sentiment": "NEUTRAL",
            "confidence": confidence,
            "volatility_proxy": round(volatility_proxy, 4),
            "headlines": completed.get("headlines") or [],
        }
    )
    return completed


def _standardize_price_data(data: dict[str, Any]) -> dict[str, Any]:
    output = dict(data)
    source = "REAL" if output.get("data_source") == "REAL" else "ESTIMATED"
    confidence = 0.95 if source == "REAL" else 0.65
    for key in ["price", "change_pct", "volume", "amount", "market_cap", "pe", "pb"]:
        if key in output:
            output[key] = metric(_num(output.get(key)), source, confidence)
    return output


def _standardize_technical_data(data: dict[str, Any]) -> dict[str, Any]:
    output = dict(data)
    source = "REAL" if output.get("data_source") == "REAL" else "ESTIMATED"
    confidence = 0.95 if source == "REAL" else 0.55
    for key in ["ma5", "ma20", "ma60", "rsi", "volume", "volume_change"]:
        if key in output:
            output[key] = metric(_num(output.get(key)), source, confidence)
    if isinstance(output.get("macd"), dict):
        output["macd"] = {
            key: metric(_num(value), source, confidence)
            for key, value in output["macd"].items()
            if key in {"dif", "dea", "hist"}
        }
    if "trend" in output:
        output["trend"] = metric(output.get("trend"), source, confidence)
    output["timeframe"] = "daily"
    output["calculation_basis"] = "daily close price from one K-line source"
    return output


def _standardize_fund_flow_data(data: dict[str, Any]) -> dict[str, Any]:
    output = dict(data)
    source = "REAL" if output.get("data_source") == "REAL" else "ESTIMATED"
    confidence = 0.85 if source == "REAL" else 0.55
    for key in ["main_flow", "large_order", "super_order"]:
        if key in output:
            output[key] = metric(_num(output.get(key)), source, confidence)
    output["timeframe"] = "daily"
    output.setdefault("unit", "ratio_to_traded_amount")
    return output


def _standardize_fundamental_data(data: dict[str, Any]) -> dict[str, Any]:
    output = dict(data)
    module_source = "REAL" if output.get("data_source") == "REAL" else "ESTIMATED"
    real_confidence = 0.9
    estimated_confidence = 0.6
    for key in ["pe", "pb", "roe", "revenue_growth", "eps"]:
        if key in output:
            value = _num(output.get(key))
            field_source = "REAL" if value is not None else "ESTIMATED"
            confidence = real_confidence if field_source == "REAL" else estimated_confidence
            output[key] = metric(value, field_source, confidence)
    estimated = output.get("estimated") or {}
    output["estimated"] = {
        key: metric(_num(value), "ESTIMATED", estimated_confidence)
        for key, value in estimated.items()
    }
    if "estimated_eps" in output:
        output["estimated_eps"] = metric(_num(output.get("estimated_eps")), "ESTIMATED", estimated_confidence)
    output["timeframe"] = "latest_report"
    return output


def _standardize_sentiment_data(data: dict[str, Any]) -> dict[str, Any]:
    output = dict(data)
    confidence = _num(output.get("confidence")) or 0.3
    if "sentiment" in output:
        output["sentiment"] = metric(output.get("sentiment"), "AI", confidence)
    output["confidence"] = metric(confidence, "AI", 1.0)
    if "volatility_proxy" in output:
        output["volatility_proxy"] = metric(_num(output.get("volatility_proxy")), "AI", confidence)
    output["timeframe"] = "daily"
    return output


def _infer_sector(symbol: str) -> str:
    code = normalize_symbol(symbol).split(".")[0]
    if code.startswith("688"):
        return "科创成长"
    if code.startswith("300"):
        return "创业成长"
    if code.startswith("600") or code.startswith("601"):
        return "沪市蓝筹"
    if code.startswith("000"):
        return "深市主板"
    return "A股全市场"


def _sector_average(sector: str) -> dict[str, float]:
    averages = {
        "科创成长": {"pe": 45.0, "pb": 5.0, "roe": 8.0, "revenue_growth": 12.0},
        "创业成长": {"pe": 38.0, "pb": 4.2, "roe": 7.5, "revenue_growth": 10.0},
        "沪市蓝筹": {"pe": 18.0, "pb": 1.8, "roe": 9.0, "revenue_growth": 5.0},
        "深市主板": {"pe": 24.0, "pb": 2.5, "roe": 8.0, "revenue_growth": 6.0},
        "A股全市场": {"pe": 28.0, "pb": 3.0, "roe": 8.0, "revenue_growth": 7.0},
    }
    return averages.get(sector, averages["A股全市场"])


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        if np.isnan(float(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
