from __future__ import annotations

import numpy as np
import pandas as pd

from core.config import PlatformConfig


class BacktestEngine:
    def __init__(self, config: PlatformConfig):
        self.config = config

    def run(self, portfolio: pd.DataFrame, daily_bars: pd.DataFrame) -> dict:
        selected = portfolio[portfolio["target_weight"] > 0][["code", "target_weight"]]
        dates = sorted(daily_bars["date"].unique())
        if selected.empty:
            equity = pd.DataFrame({"date": dates, "equity": self.config.initial_capital, "drawdown": 0.0})
            return {"equity_curve": equity, "metrics": self._metrics(equity, pd.Series(dtype=float))}
        prices = daily_bars[daily_bars["code"].isin(selected["code"])].pivot(index="date", columns="code", values="close")
        returns = prices.pct_change().fillna(0)
        weights = selected.set_index("code")["target_weight"].reindex(returns.columns).fillna(0)
        cash = max(0, 1 - weights.sum())
        daily_ret = returns.dot(weights) + cash * 0.00003
        if len(daily_ret):
            daily_ret.iloc[0] = 0.0
        equity = self.config.initial_capital * (1 + daily_ret).cumprod()
        curve = pd.DataFrame({"date": equity.index, "equity": equity.values})
        curve["drawdown"] = curve["equity"] / curve["equity"].cummax() - 1
        trades = self._pseudo_trades(returns, weights)
        return {"equity_curve": curve, "metrics": self._metrics(curve, trades)}

    @staticmethod
    def _pseudo_trades(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
        weighted = returns.mul(weights, axis=1)
        return weighted.where(weighted.abs() > 0).stack()

    @staticmethod
    def _metrics(curve: pd.DataFrame, trades: pd.Series) -> dict:
        if curve.empty:
            return {"annual_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "sharpe": 0.0, "profit_loss_ratio": 0.0}
        ret = curve["equity"].pct_change().fillna(0)
        total_return = curve["equity"].iloc[-1] / curve["equity"].iloc[0] - 1
        annual_return = (1 + total_return) ** (252 / max(1, len(curve))) - 1
        sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0.0
        wins = trades[trades > 0]
        losses = trades[trades < 0]
        win_rate = len(wins) / len(trades) if len(trades) else 0.0
        profit_loss_ratio = wins.mean() / abs(losses.mean()) if len(wins) and len(losses) else 0.0
        return {
            "annual_return": float(annual_return),
            "max_drawdown": float(curve["drawdown"].min()),
            "win_rate": float(win_rate),
            "sharpe": float(sharpe),
            "profit_loss_ratio": float(profit_loss_ratio),
            "total_return": float(total_return),
            "initial_capital": float(curve["equity"].iloc[0]),
            "current_capital": float(curve["equity"].iloc[-1]),
        }
