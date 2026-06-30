from __future__ import annotations

import numpy as np
import pandas as pd


class FundAnalyzer:
    def analyze(self, daily_bars: pd.DataFrame, dragon_tiger: pd.DataFrame) -> pd.DataFrame:
        rows = []
        dragon = dragon_tiger.set_index("code") if not dragon_tiger.empty else pd.DataFrame()
        for code, frame in daily_bars.sort_values("date").groupby("code"):
            recent = frame.tail(5)
            amount = recent["amount"].sum()
            main = recent["main_flow"].sum()
            super_order = recent["super_order_flow"].sum()
            large_order = recent["large_order_flow"].sum()
            northbound = recent["northbound_flow"].sum()
            dragon_net = float(dragon.loc[code, "net_buy"]) if code in dragon.index else 0.0
            main_ratio = main / amount if amount else 0
            score = 50 + main_ratio * 1200 + np.sign(super_order) * 8 + np.sign(northbound) * 6 + np.sign(dragon_net) * 5
            rows.append(
                {
                    "code": code,
                    "main_flow_5d": main,
                    "super_order_flow_5d": super_order,
                    "large_order_flow_5d": large_order,
                    "northbound_flow_5d": northbound,
                    "dragon_tiger_net_buy": dragon_net,
                    "fund_score": float(np.clip(score, 0, 100)),
                    "fund_view": "流入" if main > 0 else "流出",
                }
            )
        return pd.DataFrame(rows)
