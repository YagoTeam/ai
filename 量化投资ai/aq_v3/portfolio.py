from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RiskConfig


class PortfolioOptimizer:
    def __init__(self, risk_config: RiskConfig):
        self.risk_config = risk_config

    def allocate(self, scored: pd.DataFrame, price_history: pd.DataFrame) -> pd.DataFrame:
        buyable = scored[scored["total_score"] >= self.risk_config.min_score_to_buy].copy()
        if buyable.empty:
            return scored.assign(target_weight=0.0, target_value=0.0)

        volatility = self._volatility(price_history)
        buyable = buyable.merge(volatility, on="code", how="left").fillna({"volatility": 0.28})
        expected_edge = (buyable["total_score"] - 50) / 100
        kelly_like = (expected_edge / (buyable["volatility"] ** 2 + 0.08)).clip(lower=0)
        raw_weight = kelly_like / kelly_like.sum()
        capped = raw_weight.clip(upper=self.risk_config.max_single_position)
        if capped.sum() > 0:
            capped = capped / capped.sum() * min(capped.sum(), self.risk_config.max_total_exposure)
        buyable["target_weight"] = capped

        result = scored.merge(buyable[["code", "target_weight"]], on="code", how="left")
        result["target_weight"] = result["target_weight"].fillna(0.0)
        return result.sort_values("target_weight", ascending=False).reset_index(drop=True)

    @staticmethod
    def _volatility(price_history: pd.DataFrame) -> pd.DataFrame:
        returns = price_history.sort_values("date").groupby("code")["close"].pct_change()
        vol = returns.groupby(price_history["code"]).std() * np.sqrt(252)
        return vol.rename("volatility").reset_index()
