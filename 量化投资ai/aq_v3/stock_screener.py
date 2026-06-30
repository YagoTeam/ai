from __future__ import annotations

import pandas as pd

from .config import ScreenerConfig


class StockScreener:
    def __init__(self, config: ScreenerConfig):
        self.config = config

    def screen(self, snapshot: pd.DataFrame, price_history: pd.DataFrame) -> pd.DataFrame:
        breakout = self._trend_breakout(price_history, self.config.breakout_lookback)
        candidates = snapshot.merge(breakout, on="code", how="left").fillna({"trend_breakout": False})
        mask = (
            candidates["market_cap"].between(self.config.min_market_cap, self.config.max_market_cap)
            & (candidates["volume_ratio"] >= self.config.min_volume_ratio)
            & (candidates["trend_breakout"])
            & (candidates["main_inflow"] >= self.config.min_main_inflow)
        )
        return candidates.loc[mask].sort_values(["main_inflow", "volume_ratio"], ascending=False).reset_index(drop=True)

    @staticmethod
    def _trend_breakout(price_history: pd.DataFrame, lookback: int) -> pd.DataFrame:
        records = []
        for code, frame in price_history.sort_values("date").groupby("code"):
            if len(frame) <= lookback:
                records.append({"code": code, "trend_breakout": False})
                continue
            latest_close = frame["close"].iloc[-1]
            recent_high = frame["high"].iloc[-lookback - 1 : -1].max()
            records.append({"code": code, "trend_breakout": latest_close > recent_high})
        return pd.DataFrame(records)
