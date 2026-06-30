from dataclasses import dataclass, field


@dataclass
class ScreenerConfig:
    min_market_cap: float = 8_000_000_000
    max_market_cap: float = 300_000_000_000
    min_volume_ratio: float = 1.15
    breakout_lookback: int = 20
    min_main_inflow: float = 5_000_000


@dataclass
class StrategyWeights:
    trend: float = 0.45
    fund: float = 0.35
    sentiment: float = 0.20


@dataclass
class RiskConfig:
    max_single_position: float = 0.12
    max_total_exposure: float = 0.85
    max_drawdown: float = 0.15
    min_score_to_buy: float = 65.0
    sell_score: float = 45.0


@dataclass
class BacktestConfig:
    initial_cash: float = 1_000_000
    trading_days: int = 120


@dataclass
class SystemConfig:
    screener: ScreenerConfig = field(default_factory=ScreenerConfig)
    weights: StrategyWeights = field(default_factory=StrategyWeights)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
