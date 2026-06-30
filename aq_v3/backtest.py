from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BacktestConfig


class Backtester:
    def __init__(self, config: BacktestConfig):
        self.config = config

    def simulate_equity_curve(self, portfolio: pd.DataFrame, price_history: pd.DataFrame) -> pd.DataFrame:
        selected = portfolio[portfolio["target_weight"] > 0][["code", "target_weight"]]
        dates = sorted(price_history["date"].unique())[-self.config.trading_days :]
        if selected.empty or not dates:
            return pd.DataFrame({"date": dates, "equity": self.config.initial_cash, "drawdown": 0.0})

        pivot = price_history[price_history["code"].isin(selected["code"])].pivot(index="date", columns="code", values="close")
        returns = pivot.pct_change().reindex(dates).fillna(0)
        weights = selected.set_index("code")["target_weight"].reindex(returns.columns).fillna(0)
        cash_weight = max(0.0, 1.0 - weights.sum())
        daily_returns = returns.dot(weights) + cash_weight * 0.00003
        equity = self.config.initial_cash * (1 + daily_returns).cumprod()
        high_water = equity.cummax()
        drawdown = equity / high_water - 1
        return pd.DataFrame({"date": equity.index, "equity": equity.values, "drawdown": drawdown.values})

    @staticmethod
    def performance(equity_curve: pd.DataFrame) -> dict[str, float]:
        if equity_curve.empty:
            return {"total_return": 0.0, "max_drawdown": 0.0, "annual_return": 0.0}
        total_return = equity_curve["equity"].iloc[-1] / equity_curve["equity"].iloc[0] - 1
        max_drawdown = equity_curve["drawdown"].min()
        days = max(1, len(equity_curve))
        annual_return = (1 + total_return) ** (252 / days) - 1
        return {
            "total_return": float(total_return),
            "max_drawdown": float(max_drawdown),
            "annual_return": float(annual_return),
        }
