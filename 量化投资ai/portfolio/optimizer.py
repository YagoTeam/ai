from __future__ import annotations

import numpy as np
import pandas as pd

from core.config import PlatformConfig


class PortfolioOptimizer:
    def __init__(self, config: PlatformConfig):
        self.config = config

    def optimize(self, candidates: pd.DataFrame, daily_bars: pd.DataFrame, capital: float | None = None) -> pd.DataFrame:
        capital = capital or self.config.initial_capital
        buyable = candidates[candidates["total_score"] >= self.config.min_score_to_buy].copy()
        if buyable.empty:
            return candidates.assign(target_weight=0.0, target_value=0.0, shares=0)
        volatility = self._volatility(daily_bars)
        buyable = buyable.merge(volatility, on="code", how="left").fillna({"volatility": 0.30})
        edge = ((buyable["total_score"] - 50) / 100).clip(lower=0)
        kelly = edge / (buyable["volatility"] ** 2 + 0.08)
        weight = kelly / kelly.sum()
        weight = weight.clip(upper=self.config.max_single_position)
        if weight.sum() > self.config.max_total_exposure:
            weight *= self.config.max_total_exposure / weight.sum()
        buyable["target_weight"] = weight
        buyable["target_value"] = buyable["target_weight"] * capital
        buyable["shares"] = (buyable["target_value"] / buyable["close"] // 100 * 100).astype(int)
        buyable["diversification_advice"] = buyable.apply(self._advice, axis=1)
        return buyable.sort_values("target_weight", ascending=False).reset_index(drop=True)

    @staticmethod
    def _volatility(daily_bars: pd.DataFrame) -> pd.DataFrame:
        returns = daily_bars.sort_values("date").groupby("code")["close"].pct_change()
        vol = returns.groupby(daily_bars["code"]).std() * np.sqrt(252)
        return vol.rename("volatility").reset_index()

    @staticmethod
    def _advice(row: pd.Series) -> str:
        if row["target_weight"] >= 0.3:
            return "仓位较高，建议搭配低相关行业"
        return "正常分散"
