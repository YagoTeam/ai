from __future__ import annotations

import pandas as pd

from .config import RiskConfig


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config

    def apply(self, portfolio: pd.DataFrame, current_drawdown: float = 0.0, market_risk: float = 0.35) -> tuple[pd.DataFrame, list[str]]:
        adjusted = portfolio.copy()
        warnings = []
        if current_drawdown <= -self.config.max_drawdown:
            adjusted["target_weight"] *= 0.35
            warnings.append(f"触发最大回撤风控：当前回撤{current_drawdown:.2%}")
        if market_risk >= 0.75:
            adjusted["target_weight"] *= 0.55
            warnings.append(f"市场风险偏高：风险暴露系数{market_risk:.2f}")
        adjusted["target_weight"] = adjusted["target_weight"].clip(upper=self.config.max_single_position)
        total = adjusted["target_weight"].sum()
        if total > self.config.max_total_exposure:
            adjusted["target_weight"] *= self.config.max_total_exposure / total
            warnings.append("组合总仓位超过上限，已按比例压降")
        adjusted["risk_flag"] = adjusted.apply(self._risk_flag, axis=1)
        return adjusted, warnings

    def _risk_flag(self, row: pd.Series) -> str:
        if row.get("total_score", 0) < self.config.sell_score:
            return "评分跌破卖出线"
        if row.get("target_weight", 0) >= self.config.max_single_position:
            return "接近单票仓位上限"
        return "正常"
