from __future__ import annotations

import numpy as np
import pandas as pd


class FundamentalAnalyzer:
    def analyze(self, financials: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
        frame = financials.merge(universe[["code", "industry"]], on="code", how="left")
        industry_roe = frame.groupby("industry")["roe"].transform("mean")
        industry_growth = frame.groupby("industry")["revenue_growth"].transform("mean")
        valuation = 100 - (frame["pe"].rank(pct=True) * 45 + frame["pb"].rank(pct=True) * 25)
        quality = frame["roe"].clip(-0.05, 0.3) * 180 + 45
        growth = frame["revenue_growth"].clip(-0.2, 0.7) * 70 + frame["net_profit_growth"].clip(-0.3, 0.9) * 45 + 45
        industry_compare = ((frame["roe"] - industry_roe) * 140 + (frame["revenue_growth"] - industry_growth) * 55 + 50).clip(0, 100)
        frame["industry_compare_score"] = industry_compare
        frame["fundamental_score"] = (valuation * 0.25 + quality * 0.3 + growth * 0.3 + industry_compare * 0.15).clip(0, 100)
        frame["fundamental_view"] = np.select(
            [frame["fundamental_score"] >= 70, frame["fundamental_score"] < 45],
            ["优质", "偏弱"],
            default="中性",
        )
        return frame
