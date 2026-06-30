from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from data.provider import MarketDataProvider, normalize_symbol


provider = MarketDataProvider()


def run_backtest(symbol: str, short_window: int = 5, long_window: int = 20, days: int = 180) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    bars = provider.get_daily_bars(normalized, days=max(days, long_window + 20)).copy().sort_values("date")
    if bars.empty or len(bars) < long_window + 2:
        raise ValueError(f"not enough real daily bars for {normalized}")
    close = bars["close"].astype(float)
    bars["ma_short"] = close.rolling(short_window).mean()
    bars["ma_long"] = close.rolling(long_window).mean()
    bars["signal"] = (bars["ma_short"] > bars["ma_long"]).astype(float)
    bars["position"] = bars["signal"].shift(1).fillna(0.0)
    bars["return"] = close.pct_change().fillna(0.0)
    bars["strategy_return"] = bars["position"] * bars["return"]
    bars["equity"] = (1 + bars["strategy_return"]).cumprod()
    bars["drawdown"] = bars["equity"] / bars["equity"].cummax() - 1
    ret = bars["strategy_return"]
    total_return = float(bars["equity"].iloc[-1] - 1)
    annual_return = float((1 + total_return) ** (252 / max(len(bars), 1)) - 1)
    sharpe = float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0.0
    trade_returns = ret[bars["position"] > 0]
    win_rate = float((trade_returns > 0).sum() / len(trade_returns)) if len(trade_returns) else 0.0
    curve = [
        {"date": row["date"].strftime("%Y-%m-%d"), "equity": round(float(row["equity"]), 4), "drawdown": round(float(row["drawdown"]), 4)}
        for _, row in bars.tail(60).iterrows()
    ]
    return {
        "symbol": normalized,
        "strategy": "MA_CROSS",
        "params": {"short_window": short_window, "long_window": long_window, "days": days},
        "metrics": {
            "annual_return": round(annual_return, 4),
            "max_drawdown": round(float(bars["drawdown"].min()), 4),
            "sharpe": round(sharpe, 4),
            "win_rate": round(win_rate, 4),
            "total_return": round(total_return, 4),
        },
        "equity_curve": curve,
        "data_source": "REAL_DAILY_KLINE",
    }

