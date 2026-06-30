from __future__ import annotations

import numpy as np
import pandas as pd


class TechnicalAnalyzer:
    def analyze(self, daily_bars: pd.DataFrame) -> pd.DataFrame:
        frames = []
        for code, frame in daily_bars.sort_values("date").groupby("code"):
            f = frame.copy()
            f["ma5"] = f["close"].rolling(5).mean()
            f["ma20"] = f["close"].rolling(20).mean()
            f["ma60"] = f["close"].rolling(60).mean()
            ema12 = f["close"].ewm(span=12, adjust=False).mean()
            ema26 = f["close"].ewm(span=26, adjust=False).mean()
            f["macd_dif"] = ema12 - ema26
            f["macd_dea"] = f["macd_dif"].ewm(span=9, adjust=False).mean()
            f["macd_hist"] = f["macd_dif"] - f["macd_dea"]
            f["rsi"] = self._rsi(f["close"])
            f["volume_ratio"] = f["volume"] / f["volume"].rolling(20).mean()
            f["support"] = f["low"].rolling(20).min()
            f["resistance"] = f["high"].rolling(20).max()
            latest = f.tail(1).copy()
            latest["trend"] = latest.apply(self._trend_label, axis=1)
            latest["technical_score"] = latest.apply(self._score, axis=1)
            frames.append(latest)
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return (100 - 100 / (1 + rs)).fillna(50)

    @staticmethod
    def _trend_label(row: pd.Series) -> str:
        if row["ma5"] > row["ma20"] > row["ma60"] and row["macd_hist"] > 0:
            return "上涨"
        if row["ma5"] < row["ma20"] < row["ma60"] and row["macd_hist"] < 0:
            return "下跌"
        return "震荡"

    @staticmethod
    def _score(row: pd.Series) -> float:
        score = 50
        score += 18 if row["trend"] == "上涨" else -15 if row["trend"] == "下跌" else 0
        score += 10 if row["close"] >= row["resistance"] * 0.985 else 0
        score += np.clip((row["rsi"] - 50) * 0.35, -12, 12)
        score += np.clip((row["volume_ratio"] - 1) * 12, -10, 14)
        return float(np.clip(score, 0, 100))
