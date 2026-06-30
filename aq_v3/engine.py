from __future__ import annotations

from dataclasses import asdict

from .backtest import Backtester
from .config import SystemConfig
from .data_provider import AShareDataProvider
from .news_ai import NewsAnalyzer
from .portfolio import PortfolioOptimizer
from .risk import RiskManager
from .stock_screener import StockScreener
from .strategies import StrategyScorer
from .wechat import WeComPusher


class QuantEngine:
    def __init__(self, config: SystemConfig | None = None, seed: int = 42):
        self.config = config or SystemConfig()
        self.data_provider = AShareDataProvider(seed=seed)
        self.news_ai = NewsAnalyzer()
        self.screener = StockScreener(self.config.screener)
        self.scorer = StrategyScorer(self.config.weights)
        self.optimizer = PortfolioOptimizer(self.config.risk)
        self.risk = RiskManager(self.config.risk)
        self.backtester = Backtester(self.config.backtest)

    def run(self, news_items: list[str] | None = None, webhook_url: str | None = None) -> dict:
        news_items = news_items or []
        universe = self.data_provider.get_universe()
        history = self.data_provider.get_price_history(universe)
        snapshot = self.data_provider.get_latest_snapshot(universe, history)
        candidates = self.screener.screen(snapshot, history)
        sentiment = self.news_ai.sentiment_frame(news_items, universe)
        scored = self.scorer.score(candidates, history, sentiment)
        allocated = self.optimizer.allocate(scored, history)
        equity_curve = self.backtester.simulate_equity_curve(allocated, history)
        perf = self.backtester.performance(equity_curve)
        current_drawdown = perf["max_drawdown"]
        market_risk = self._market_risk(snapshot)
        portfolio, warnings = self.risk.apply(allocated, current_drawdown=current_drawdown, market_risk=market_risk)
        equity_curve = self.backtester.simulate_equity_curve(portfolio, history)
        perf = self.backtester.performance(equity_curve)
        pusher = WeComPusher(webhook_url)
        message = pusher.build_signal_message(portfolio, warnings)
        return {
            "config": asdict(self.config),
            "universe": universe,
            "snapshot": snapshot,
            "candidates": candidates,
            "sentiment": sentiment,
            "scored": scored,
            "portfolio": portfolio,
            "equity_curve": equity_curve,
            "performance": perf,
            "warnings": warnings,
            "wechat_message": message,
        }

    @staticmethod
    def _market_risk(snapshot) -> float:
        weak_volume = (snapshot["volume_ratio"] < 0.9).mean()
        outflow = (snapshot["main_inflow"] < 0).mean()
        return float((weak_volume + outflow) / 2)
