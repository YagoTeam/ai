from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class NewsImpact:
    polarity: str
    affected_stocks: list[str]
    strength: int
    reason: str


class NewsAnalyzer:
    positive_words = ["中标", "增长", "突破", "回购", "增持", "订单", "政策支持", "盈利", "涨价", "国产替代"]
    negative_words = ["减持", "亏损", "处罚", "调查", "下滑", "违约", "退市", "爆雷", "禁令", "召回"]

    def analyze(self, news: str, universe: pd.DataFrame) -> NewsImpact:
        text = news or ""
        pos = sum(1 for word in self.positive_words if word in text)
        neg = sum(1 for word in self.negative_words if word in text)
        raw_strength = min(100, max(10, abs(pos - neg) * 25 + 35 if pos or neg else 25))
        polarity = "利好" if pos > neg else "利空" if neg > pos else "中性"
        affected = self._match_stocks(text, universe)
        reason = f"识别到{pos}个利好关键词、{neg}个利空关键词"
        return NewsImpact(polarity=polarity, affected_stocks=affected, strength=int(raw_strength), reason=reason)

    def sentiment_frame(self, news_items: list[str], universe: pd.DataFrame) -> pd.DataFrame:
        base = pd.DataFrame({"code": universe["code"], "sentiment_score": 50.0})
        for news in news_items:
            impact = self.analyze(news, universe)
            delta = impact.strength * (0.35 if impact.polarity == "利好" else -0.35 if impact.polarity == "利空" else 0)
            target_codes = impact.affected_stocks or universe.loc[universe["industry"].apply(lambda x: str(x) in news), "code"].tolist()
            if not target_codes:
                target_codes = universe["code"].sample(min(8, len(universe)), random_state=impact.strength).tolist()
            base.loc[base["code"].isin(target_codes), "sentiment_score"] += delta
        base["sentiment_score"] = base["sentiment_score"].clip(0, 100)
        return base

    @staticmethod
    def _match_stocks(text: str, universe: pd.DataFrame) -> list[str]:
        matched = []
        for _, row in universe.iterrows():
            plain_code = str(row["code"]).split(".")[0]
            if plain_code in text or str(row["name"]) in text:
                matched.append(row["code"])
        matched.extend(re.findall(r"\b\d{6}\.(?:SH|SZ)\b", text))
        return sorted(set(matched))
