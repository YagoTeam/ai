from __future__ import annotations

import numpy as np
import pandas as pd

from core.config import PlatformConfig


class MultiStrategyFusionEngine:
    def __init__(self, config: PlatformConfig):
        self.config = config

    def fuse(self, technical: pd.DataFrame, funds: pd.DataFrame, sentiment: pd.DataFrame, fundamental: pd.DataFrame) -> pd.DataFrame:
        frame = technical.merge(funds, on="code", how="left")
        frame = frame.merge(sentiment, on="code", how="left")
        frame = frame.merge(
            fundamental[
                [
                    "code",
                    "pe",
                    "pb",
                    "roe",
                    "revenue_growth",
                    "net_profit_growth",
                    "industry_compare_score",
                    "fundamental_score",
                    "fundamental_view",
                ]
            ],
            on="code",
            how="left",
        )
        frame[["fund_score", "sentiment_score", "fundamental_score"]] = frame[
            ["fund_score", "sentiment_score", "fundamental_score"]
        ].fillna(50)
        frame["total_score"] = (
            frame["technical_score"] * self.config.technical_weight
            + frame["fund_score"] * self.config.fund_weight
            + frame["sentiment_score"] * self.config.sentiment_weight
            + frame["fundamental_score"] * self.config.fundamental_weight
        ).clip(0, 100)
        frame["signal"] = np.select(
            [frame["total_score"] >= 75, frame["total_score"] >= 65, frame["total_score"] < 45],
            ["买入", "观望偏多", "卖出"],
            default="观望",
        )
        frame["confidence"] = ((frame["total_score"] - 50).abs() / 50).clip(0.1, 0.95)
        return frame.sort_values("total_score", ascending=False).reset_index(drop=True)
