from __future__ import annotations

import pandas as pd

from analysis import FundAnalyzer, FundamentalAnalyzer, TechnicalAnalyzer
from backtest import BacktestEngine
from core.config import PlatformConfig
from data import MarketDataProvider
from notify import Notifier
from portfolio import PortfolioOptimizer
from risk import RiskManager
from sentiment import NewsSentimentEngine
from strategy import AutoStockScreener, MultiStrategyFusionEngine, StockDecisionEngine
from watch import RealtimeWatchScanner


class QuantResearchPlatform:
    def __init__(self, config: PlatformConfig | None = None, seed: int = 42):
        self.config = config or PlatformConfig()
        self.data_provider = MarketDataProvider(seed=seed)
        self.technical = TechnicalAnalyzer()
        self.funds = FundAnalyzer()
        self.fundamental = FundamentalAnalyzer()
        self.sentiment = NewsSentimentEngine()
        self.fusion = MultiStrategyFusionEngine(self.config)
        self.decision = StockDecisionEngine()
        self.screener = AutoStockScreener(self.config)
        self.optimizer = PortfolioOptimizer(self.config)
        self.risk = RiskManager(self.config)
        self.backtest = BacktestEngine(self.config)
        self.watch = RealtimeWatchScanner()

    def run(self, news_items: list[str] | None = None, capital: float | None = None, webhook_url: str | None = None) -> dict:
        universe = self.data_provider.get_universe(self.config.universe_size)
        daily = self.data_provider.get_daily_bars(universe, self.config.history_days)
        minute = self.data_provider.get_minute_bars(universe)
        financials = self.data_provider.get_financials(universe)
        dragon_tiger = self.data_provider.get_dragon_tiger(universe)
        news_items = news_items or self.data_provider.get_news()

        technical = self.technical.analyze(daily)
        funds = self.funds.analyze(daily, dragon_tiger)
        fundamental = self.fundamental.analyze(financials, universe)
        sentiment_scores = self.sentiment.score_universe(news_items, universe)
        fused = self.fusion.fuse(technical, funds, sentiment_scores, fundamental)
        fused = fused.merge(universe[["code", "name", "industry"]], on="code", how="left")
        decisions = self.decision.batch_decide(fused)
        candidates = self.screener.screen(universe, decisions)
        optimized = self.optimizer.optimize(candidates, daily, capital or self.config.initial_capital)
        preliminary_backtest = self.backtest.run(optimized, daily)
        market_risk = self._market_risk(technical, funds)
        controlled, warnings = self.risk.apply(
            optimized,
            market_risk=market_risk,
            current_drawdown=preliminary_backtest["metrics"]["max_drawdown"],
        )
        final_backtest = self.backtest.run(controlled, daily)
        watch_signals = self.watch.scan(decisions)
        news_events = [self.sentiment.parse_event(item, universe).__dict__ for item in news_items]
        notifier = Notifier(webhook_url)
        message = notifier.build_message(controlled, warnings)
        return {
            "universe": universe,
            "daily_bars": daily,
            "minute_bars": minute,
            "financials": financials,
            "dragon_tiger": dragon_tiger,
            "technical": technical,
            "funds": funds,
            "fundamental": fundamental,
            "sentiment": sentiment_scores,
            "news_events": news_events,
            "fused": decisions,
            "candidates": candidates,
            "portfolio": controlled,
            "watch_signals": watch_signals,
            "equity_curve": final_backtest["equity_curve"],
            "metrics": final_backtest["metrics"],
            "warnings": warnings,
            "wechat_message": message,
        }

    @staticmethod
    def _market_risk(technical: pd.DataFrame, funds: pd.DataFrame) -> float:
        down = (technical["trend"] == "下跌").mean()
        outflow = (funds["main_flow_5d"] < 0).mean()
        weak_volume = (technical["volume_ratio"] < 0.9).mean()
        return float((down + outflow + weak_volume) / 3)
