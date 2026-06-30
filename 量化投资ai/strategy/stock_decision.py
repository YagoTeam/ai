from __future__ import annotations

import numpy as np
import pandas as pd


class StockDecisionEngine:
    def decide(self, row: pd.Series) -> dict:
        close = float(row["close"])
        atr_like = max(close * 0.035, float(row["close"] - row.get("support", close * 0.94)) * 0.35)
        buy_low = close * 0.985
        buy_high = close * 1.015
        stop_loss = min(close - atr_like, close * 0.93)
        take_profit = close + atr_like * 2.2
        score = float(row["total_score"])
        risk_level = "低" if score >= 78 and row.get("trend") == "上涨" else "中" if score >= 60 else "高"
        signal = "买入" if score >= 75 else "卖出" if score < 45 else "观望"
        return {
            "code": row["code"],
            "signal": signal,
            "score": score,
            "confidence": float(np.clip(row.get("confidence", 0.5), 0, 1)),
            "entry_price_range": f"{buy_low:.2f}-{buy_high:.2f}",
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "risk_level": risk_level,
        }

    def batch_decide(self, fused: pd.DataFrame) -> pd.DataFrame:
        decisions = pd.DataFrame([self.decide(row) for _, row in fused.iterrows()])
        return fused.merge(decisions, on="code", suffixes=("", "_decision"), how="left")
