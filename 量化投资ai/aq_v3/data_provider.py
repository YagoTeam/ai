from __future__ import annotations

import numpy as np
import pandas as pd


class AShareDataProvider:
    """Data provider with deterministic demo data and a clear production adapter surface."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_universe(self, size: int = 220) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed)
        codes = [f"{i:06d}.{'SH' if i % 2 == 0 else 'SZ'}" for i in range(600000, 600000 + size)]
        names = [f"样本A股{i + 1}" for i in range(size)]
        market_cap = rng.lognormal(mean=23.7, sigma=0.9, size=size)
        turnover = rng.uniform(0.8, 8.0, size=size)
        industry = rng.choice(["新能源", "半导体", "医药", "消费", "军工", "金融", "AI算力"], size=size)
        return pd.DataFrame(
            {
                "code": codes,
                "name": names,
                "industry": industry,
                "market_cap": market_cap,
                "turnover_rate": turnover,
            }
        )

    def get_price_history(self, universe: pd.DataFrame, days: int = 160) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + 1)
        rows = []
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
        for idx, row in universe.iterrows():
            drift = rng.normal(0.0009, 0.0012)
            volatility = rng.uniform(0.012, 0.035)
            shocks = rng.normal(drift, volatility, size=days)
            base = rng.uniform(8, 80)
            close = base * np.exp(np.cumsum(shocks))
            high = close * (1 + rng.uniform(0.002, 0.035, size=days))
            low = close * (1 - rng.uniform(0.002, 0.035, size=days))
            volume_base = rng.uniform(20_000_000, 600_000_000)
            volume = volume_base * rng.lognormal(0, 0.35, size=days)
            main_flow = rng.normal(0, volume * close * 0.015)
            if idx % 11 == 0:
                close[-8:] *= np.linspace(1.01, 1.13, 8)
                main_flow[-5:] += rng.uniform(8_000_000, 60_000_000, 5)
                volume[-5:] *= rng.uniform(1.25, 2.4)
            rows.extend(
                {
                    "date": date,
                    "code": row["code"],
                    "close": close[i],
                    "high": high[i],
                    "low": low[i],
                    "volume": volume[i],
                    "main_inflow": main_flow[i],
                }
                for i, date in enumerate(dates)
            )
        return pd.DataFrame(rows)

    def get_latest_snapshot(self, universe: pd.DataFrame, price_history: pd.DataFrame) -> pd.DataFrame:
        latest = price_history.sort_values("date").groupby("code").tail(1)
        vol_mean = price_history.groupby("code")["volume"].rolling(20).mean().reset_index(level=0, drop=True)
        enriched = price_history.assign(volume_ma20=vol_mean)
        latest_vol = enriched.sort_values("date").groupby("code").tail(1)[["code", "volume_ma20"]]
        snapshot = latest.merge(latest_vol, on="code").merge(universe, on="code")
        snapshot["volume_ratio"] = snapshot["volume"] / snapshot["volume_ma20"].replace(0, np.nan)
        return snapshot.fillna(0)
