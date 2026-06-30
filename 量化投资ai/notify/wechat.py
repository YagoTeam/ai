from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd


class Notifier:
    def __init__(self, webhook_url: str | None = None, channel: str = "wecom"):
        self.webhook_url = webhook_url
        self.channel = channel

    def build_message(self, portfolio: pd.DataFrame, warnings: list[str]) -> str:
        lines = ["AI量化平台交易信号"]
        if warnings:
            lines.append("风控：" + "；".join(warnings))
        for _, row in portfolio.head(8).iterrows():
            lines.append(
                f"{row['code']} {row.get('name', '')}｜评分{row['total_score']:.1f}｜"
                f"信号{row['signal']}｜仓位{row['target_weight']:.1%}｜"
                f"建仓{row['entry_price_range']}｜止损{row['stop_loss']}｜止盈{row['take_profit']}"
            )
        return "\n".join(lines)

    def send(self, content: str) -> tuple[bool, str]:
        if not self.webhook_url:
            return False, "未配置Webhook，仅生成推送内容"
        payload = {"msgtype": "text", "text": {"content": content}}
        if self.channel == "server_chan":
            payload = {"title": "AI量化平台交易信号", "desp": content}
        try:
            data = json.dumps(payload).encode("utf-8")
            request = Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=8) as response:
                return 200 <= response.status < 300, response.read().decode("utf-8")
        except (URLError, TimeoutError, OSError) as exc:
            return False, str(exc)
