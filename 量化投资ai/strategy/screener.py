from __future__ import annotations

import pandas as pd

from core.config import PlatformConfig


class AutoStockScreener:
    def __init__(self, config: PlatformConfig):
        self.config = config

    def screen(self, universe: pd.DataFrame, fused: pd.DataFrame) -> pd.DataFrame:
        frame = fused.merge(universe[["code", "is_st", "market_cap"]], on="code", how="left")
        breakout = frame["close"] >= frame["resistance"] * 0.985
        liquidity = frame["amount"] >= self.config.liquidity_min_amount
        hot = frame["sentiment_score"] >= 55
        mask = (
            frame["market_cap"].between(self.config.market_cap_min, self.config.market_cap_max)
            & liquidity
            & ~frame["is_st"]
            & (frame["volume_ratio"] >= self.config.min_volume_ratio)
            & breakout
            & (frame["main_flow_5d"] >= self.config.min_main_inflow)
            & hot
        )
        return frame.loc[mask].sort_values("total_score", ascending=False).reset_index(drop=True)
