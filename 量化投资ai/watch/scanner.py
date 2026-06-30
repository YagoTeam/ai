from __future__ import annotations

import pandas as pd


class RealtimeWatchScanner:
    def scan(self, fused: pd.DataFrame, news_events: list[dict] | None = None) -> pd.DataFrame:
        signals = []
        for _, row in fused.iterrows():
            triggers = []
            if row.get("volume_ratio", 1) >= 1.8 and row.get("close", 0) > row.get("ma20", 0):
                triggers.append("放量上涨")
            if row.get("volume_ratio", 1) >= 1.8 and row.get("close", 0) < row.get("ma20", 0):
                triggers.append("放量下跌")
            if row.get("main_flow_5d", 0) > 20_000_000:
                triggers.append("主力资金异动")
            if row.get("macd_hist", 0) > 0 and row.get("macd_dif", 0) > row.get("macd_dea", 0):
                triggers.append("MACD金叉/强势")
            if row.get("sentiment_score", 50) >= 70:
                triggers.append("新闻突发利好")
            if triggers:
                signals.append(
                    {
                        "code": row["code"],
                        "name": row.get("name", ""),
                        "signal": row.get("signal", "观望"),
                        "score": row.get("total_score", 0),
                        "triggers": "；".join(triggers),
                    }
                )
        return pd.DataFrame(signals).sort_values("score", ascending=False) if signals else pd.DataFrame()
