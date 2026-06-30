from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class NewsEvent:
    text: str
    polarity: str
    impact_strength: float
    affected_stocks: list[str]
    concept_spread: list[str]
    reason: str


class NewsSentimentEngine:
    positive_words = ["政策支持", "中标", "订单", "增长", "突破", "回购", "增持", "盈利改善", "国产替代", "涨价"]
    negative_words = ["调查", "处罚", "减持", "亏损", "召回", "违约", "退市", "禁令", "下滑", "爆雷"]
    concept_words = ["AI算力", "半导体", "新能源", "医药", "消费", "军工", "金融", "机器人"]

    def parse_event(self, text: str, universe: pd.DataFrame) -> NewsEvent:
        pos = sum(word in text for word in self.positive_words)
        neg = sum(word in text for word in self.negative_words)
        polarity = "利好" if pos > neg else "利空" if neg > pos else "中性"
        strength = min(1.0, max(0.15, abs(pos - neg) * 0.23 + 0.34 if pos or neg else 0.2))
        concepts = [word for word in self.concept_words if word in text]
        stocks = self._affected_stocks(text, concepts, universe)
        reason = f"利好关键词{pos}个，利空关键词{neg}个，概念传播{len(concepts)}个"
        return NewsEvent(text, polarity, float(strength), stocks, concepts, reason)

    def score_universe(self, news_items: list[str], universe: pd.DataFrame) -> pd.DataFrame:
        scores = pd.DataFrame({"code": universe["code"], "sentiment_score": 50.0, "hot_concepts": ""})
        for item in news_items:
            event = self.parse_event(item, universe)
            direction = 1 if event.polarity == "利好" else -1 if event.polarity == "利空" else 0
            delta = direction * event.impact_strength * 35
            target = event.affected_stocks
            if not target:
                continue
            scores.loc[scores["code"].isin(target), "sentiment_score"] += delta
            scores.loc[scores["code"].isin(target), "hot_concepts"] = ",".join(event.concept_spread)
        scores["sentiment_score"] = scores["sentiment_score"].clip(0, 100)
        return scores

    @staticmethod
    def _affected_stocks(text: str, concepts: list[str], universe: pd.DataFrame) -> list[str]:
        direct = []
        for _, row in universe.iterrows():
            plain = str(row["code"]).split(".")[0]
            if plain in text or row["code"] in text or row["name"] in text:
                direct.append(row["code"])
        if direct:
            return sorted(set(direct))
        if concepts:
            return universe.loc[universe["industry"].isin(concepts), "code"].head(40).tolist()
        return []
