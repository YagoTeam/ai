from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyWeights


class StrategyScorer:
    def __init__(self, weights: StrategyWeights):
        self.weights = weights

    def score(self, candidates: pd.DataFrame, price_history: pd.DataFrame, sentiment: pd.DataFrame) -> pd.DataFrame:
        if candidates.empty:
            return candidates.assign(trend_score=[], fund_score=[], sentiment_score=[], total_score=[], signal=[])

        trend_scores = self._trend_scores(price_history)
        fund_scores = self._fund_scores(price_history)
        scored = candidates.merge(trend_scores, on="code", how="left")
        scored = scored.merge(fund_scores, on="code", how="left")
        scored = scored.merge(sentiment[["code", "sentiment_score"]], on="code", how="left")
        scored[["trend_score", "fund_score", "sentiment_score"]] = scored[
            ["trend_score", "fund_score", "sentiment_score"]
        ].fillna(50)
        scored["total_score"] = (
            scored["trend_score"] * self.weights.trend
            + scored["fund_score"] * self.weights.fund
            + scored["sentiment_score"] * self.weights.sentiment
        ).clip(0, 100)
        scored["signal"] = np.select(
            [scored["total_score"] >= 75, scored["total_score"] >= 60, scored["total_score"] < 45],
            ["强买入", "买入观察", "卖出/规避"],
            default="持有/观望",
        )
        return scored.sort_values("total_score", ascending=False).reset_index(drop=True)

    @staticmethod
    def _trend_scores(price_history: pd.DataFrame) -> pd.DataFrame:
        records = []
        for code, frame in price_history.sort_values("date").groupby("code"):
            close = frame["close"]
            ma5 = close.rolling(5).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            ma60 = close.rolling(60).mean().iloc[-1]
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False).mean()
            macd_hist = (dif - dea).iloc[-1]
            momentum = close.iloc[-1] / close.iloc[-20] - 1 if len(close) >= 20 else 0
            score = 50
            score += 18 if ma5 > ma20 > ma60 else 0
            score += 12 if macd_hist > 0 else -8
            score += np.clip(momentum * 160, -18, 22)
            records.append({"code": code, "trend_score": float(np.clip(score, 0, 100))})
        return pd.DataFrame(records)

    @staticmethod
    def _fund_scores(price_history: pd.DataFrame) -> pd.DataFrame:
        records = []
        for code, frame in price_history.sort_values("date").groupby("code"):
            recent = frame.tail(5)
            inflow = recent["main_inflow"].sum()
            amount = (recent["volume"] * recent["close"]).sum()
            ratio = inflow / amount if amount else 0
            records.append({"code": code, "fund_score": float(np.clip(50 + ratio * 900, 0, 100))})
        return pd.DataFrame(records)
