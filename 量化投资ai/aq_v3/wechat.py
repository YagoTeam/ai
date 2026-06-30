from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd


class WeComPusher:
    def __init__(self, webhook_url: str | None = None, timeout: int = 8):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def build_signal_message(self, portfolio: pd.DataFrame, warnings: list[str]) -> str:
        top = portfolio.sort_values("target_weight", ascending=False).head(8)
        lines = ["A股AI量化投资系统V3 交易信号"]
        if warnings:
            lines.append("风控提示：" + "；".join(warnings))
        for _, row in top.iterrows():
            if row.get("target_weight", 0) <= 0:
                continue
            lines.append(
                f"{row['code']} {row['name']}｜评分{row['total_score']:.1f}｜"
                f"信号{row['signal']}｜目标仓位{row['target_weight']:.1%}"
            )
        return "\n".join(lines)

    def send_text(self, content: str) -> tuple[bool, str]:
        if not self.webhook_url:
            return False, "未配置企业微信Webhook，已生成消息但未发送"
        payload = {"msgtype": "text", "text": {"content": content}}
        try:
            data = json.dumps(payload).encode("utf-8")
            request = Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return 200 <= response.status < 300, body
        except (URLError, TimeoutError, OSError) as exc:
            return False, str(exc)
