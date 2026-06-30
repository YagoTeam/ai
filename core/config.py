from dataclasses import dataclass


@dataclass
class PlatformConfig:
    universe_size: int = 260
    history_days: int = 180
    initial_capital: float = 1_000_000
    max_single_position: float = 0.40
    max_total_exposure: float = 0.90
    max_drawdown_limit: float = 0.18
    min_score_to_buy: float = 65.0
    market_cap_min: float = 5_000_000_000
    market_cap_max: float = 350_000_000_000
    liquidity_min_amount: float = 80_000_000
    min_volume_ratio: float = 1.18
    min_main_inflow: float = 3_000_000
    technical_weight: float = 0.35
    fund_weight: float = 0.30
    sentiment_weight: float = 0.20
    fundamental_weight: float = 0.15
