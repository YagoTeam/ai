from __future__ import annotations

import pandas as pd

from core.config import PlatformConfig


class RiskManager:
    def __init__(self, config: PlatformConfig):
        self.config = config

    def apply(self, portfolio: pd.DataFrame, market_risk: float = 0.35, current_drawdown: float = 0.0) -> tuple[pd.DataFrame, list[str]]:
        frame = portfolio.copy()
        warnings = []
        if frame.empty:
            return frame, ["无可建仓标的"]
        if current_drawdown <= -self.config.max_drawdown_limit:
            frame["target_weight"] *= 0.35
            warnings.append("触发最大回撤限制，组合仓位降至防守模式")
        if market_risk >= 0.7:
            frame["target_weight"] *= 0.55
            warnings.append("市场风险偏高，降低整体暴露")
        frame.loc[frame["volatility"] > 0.55, "target_weight"] *= 0.7
        frame["target_weight"] = frame["target_weight"].clip(upper=self.config.max_single_position)
        total = frame["target_weight"].sum()
        if total > self.config.max_total_exposure:
            frame["target_weight"] *= self.config.max_total_exposure / total
            warnings.append("总仓位超过上限，已按比例压缩")
        frame["risk_flag"] = frame.apply(self._flag, axis=1)
        return frame, warnings

    def _flag(self, row: pd.Series) -> str:
        if row["target_weight"] >= self.config.max_single_position * 0.95:
            return "接近单股仓位上限"
        if row["volatility"] > 0.55:
            return "波动率偏高"
        if row["total_score"] < self.config.min_score_to_buy:
            return "评分不足"
        return "正常"
