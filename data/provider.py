from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
import requests


class DataProviderError(RuntimeError):
    """Raised when real market data cannot be fetched from configured providers."""


@dataclass(frozen=True)
class StockCandidate:
    code: str
    name: str


def normalize_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    if not raw:
        raise ValueError("symbol is required")
    if "." in raw:
        code, suffix = raw.split(".", 1)
        return f"{code.zfill(6)}.{suffix}"
    if raw.startswith(("SH", "SZ")) and len(raw) >= 8:
        return f"{raw[-6:]}.{raw[:2]}"
    if raw.startswith("6"):
        return f"{raw.zfill(6)}.SH"
    return f"{raw.zfill(6)}.SZ"


def symbol_to_ak(symbol: str) -> str:
    return normalize_symbol(symbol).split(".")[0]


def symbol_to_tushare(symbol: str) -> str:
    return normalize_symbol(symbol)


def symbol_to_market(symbol: str) -> str:
    return normalize_symbol(symbol).split(".")[1].lower()


def _first_existing(frame: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = pd.to_numeric(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return float(parsed)
    except (TypeError, ValueError):
        return None


class MarketDataProvider:
    """Real A-share data access layer. AkShare is primary; Tushare is a token-gated fallback."""

    def __init__(self, tushare_token: str | None = None):
        self.tushare_token = tushare_token or os.getenv("TUSHARE_TOKEN")
        self.timeout = float(os.getenv("MARKET_HTTP_TIMEOUT", "8"))

    @lru_cache(maxsize=1)
    def stock_master(self) -> pd.DataFrame:
        try:
            import akshare as ak

            frame = ak.stock_info_a_code_name()
        except Exception as exc:
            frame = self._tushare_stock_basic(exc)
        if frame.empty:
            raise DataProviderError("real stock list is empty")
        code_col = _first_existing(frame, ["code", "代码", "ts_code"])
        name_col = _first_existing(frame, ["name", "名称"])
        if not code_col or not name_col:
            raise DataProviderError(f"stock list schema is unsupported: {list(frame.columns)}")
        result = frame.rename(columns={code_col: "raw_code", name_col: "name"}).copy()
        result["code"] = result["raw_code"].map(normalize_symbol)
        return result[["code", "name"]].dropna(subset=["code", "name"]).drop_duplicates("code")

    @lru_cache(maxsize=1)
    def stock_spot(self) -> pd.DataFrame:
        try:
            import akshare as ak

            frame = ak.stock_zh_a_spot_em()
        except Exception as exc:
            frame = self._tushare_stock_spot(exc)
        if frame.empty:
            raise DataProviderError("real stock list is empty")
        code_col = _first_existing(frame, ["代码", "ts_code", "code"])
        name_col = _first_existing(frame, ["名称", "name"])
        if not code_col or not name_col:
            raise DataProviderError(f"stock spot schema is unsupported: {list(frame.columns)}")
        result = frame.rename(columns={code_col: "raw_code", name_col: "name"}).copy()
        result["code"] = result["raw_code"].map(normalize_symbol)
        keep = ["code", "name"]
        for source, target in [("最新价", "price"), ("涨跌幅", "change_pct"), ("成交量", "volume"), ("成交额", "amount"), ("总市值", "market_cap")]:
            if source in result.columns:
                result[target] = pd.to_numeric(result[source], errors="coerce")
                keep.append(target)
        return result[keep].dropna(subset=["code", "name"]).drop_duplicates("code")

    def search_stock(self, keyword: str, limit: int = 20) -> list[dict[str, str]]:
        query = str(keyword or "").strip().upper()
        if not query:
            return []
        if query.replace(".", "").replace("SH", "").replace("SZ", "").isdigit():
            normalized = normalize_symbol(query)
            try:
                quote = self.get_realtime_quote(normalized)
                return [{"code": normalized, "name": quote.get("name") or ""}]
            except DataProviderError:
                return [{"code": normalized, "name": ""}]
        frame = self.stock_master()
        code_plain = frame["code"].str.split(".").str[0]
        mask = frame["code"].str.upper().str.contains(query, regex=False)
        mask |= code_plain.str.contains(query, regex=False)
        mask |= frame["name"].astype(str).str.contains(query, regex=False)
        rows = frame.loc[mask, ["code", "name"]].head(limit)
        return rows.to_dict(orient="records")

    def get_realtime_quote(self, symbol: str) -> dict[str, float | str | None]:
        normalized = normalize_symbol(symbol)
        try:
            return self._tencent_quote(normalized)
        except Exception:
            pass
        try:
            return self._eastmoney_quote(normalized)
        except Exception as exc:
            if os.getenv("MARKET_ENABLE_AK_SPOT_FALLBACK") != "1":
                raise DataProviderError(f"realtime quote failed for {normalized}: {exc}") from exc
        try:
            frame = self.stock_spot()
            row = frame.loc[frame["code"] == normalized]
            if row.empty:
                raise DataProviderError(f"stock not found in real A-share list: {normalized}")
            data = row.iloc[0].to_dict()
            return {
                "code": normalized,
                "name": str(data.get("name", "")),
                "price": _to_float(data.get("price")),
                "change_pct": _to_float(data.get("change_pct")),
                "volume": _to_float(data.get("volume")),
                "amount": _to_float(data.get("amount")),
                "market_cap": _to_float(data.get("market_cap")),
            }
        except DataProviderError:
            raise
        except Exception as exc:
            raise DataProviderError(f"realtime quote failed for {normalized}: {exc}") from exc

    def get_daily_bars(self, symbol: str, days: int = 180) -> pd.DataFrame:
        normalized = normalize_symbol(symbol)
        start = (date.today() - timedelta(days=max(days * 2, 120))).strftime("%Y%m%d")
        end = date.today().strftime("%Y%m%d")
        try:
            return self._tencent_daily(normalized, days)
        except Exception:
            pass
        try:
            return self._eastmoney_daily(normalized, start, end, days)
        except Exception as exc:
            if os.getenv("MARKET_ENABLE_AK_HIST_FALLBACK") != "1" and not self.tushare_token:
                raise DataProviderError(f"daily bars failed for {normalized}: {exc}") from exc
        try:
            import akshare as ak

            frame = ak.stock_zh_a_hist(symbol=symbol_to_ak(normalized), period="daily", start_date=start, end_date=end, adjust="qfq")
        except Exception as exc:
            frame = self._tushare_daily(normalized, start, end, exc)
        if frame.empty:
            raise DataProviderError(f"daily bars are empty for {normalized}")
        rename = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "change_pct",
        }
        frame = frame.rename(columns=rename).copy()
        required = ["date", "open", "close", "high", "low", "volume"]
        missing = [name for name in required if name not in frame.columns]
        if missing:
            raise DataProviderError(f"daily bar schema missing {missing}: {list(frame.columns)}")
        if "amount" not in frame.columns:
            frame["amount"] = pd.NA
        frame["code"] = normalized
        for col in ["open", "close", "high", "low", "volume", "amount", "change_pct"]:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.sort_values("date").tail(days).reset_index(drop=True)

    def get_fund_flow(self, symbol: str) -> dict[str, float | None]:
        normalized = normalize_symbol(symbol)
        if os.getenv("MARKET_ENABLE_AK_FUNDS") != "1":
            return {"main_flow": None, "large_order": None, "super_order": None}
        try:
            import akshare as ak

            frame = ak.stock_individual_fund_flow(stock=symbol_to_ak(normalized), market=symbol_to_market(normalized))
        except Exception as exc:
            raise DataProviderError(f"AkShare fund flow failed for {normalized}: {exc}") from exc
        if frame.empty:
            return {"main_flow": None, "large_order": None, "super_order": None}
        latest = frame.tail(1).iloc[0]
        return {
            "main_flow": _to_float(latest.get("主力净流入-净额")),
            "large_order": _to_float(latest.get("大单净流入-净额")),
            "super_order": _to_float(latest.get("超大单净流入-净额")),
        }

    def get_fundamental(self, symbol: str) -> dict[str, float | None]:
        normalized = normalize_symbol(symbol)
        result = {"pe": None, "pb": None, "roe": None, "revenue_growth": None}
        try:
            quote = self._tencent_quote(normalized)
            result["pe"] = quote.get("pe")
            result["pb"] = quote.get("pb")
        except Exception:
            pass
        if os.getenv("MARKET_ENABLE_EASTMONEY_FUNDAMENTAL") == "1":
            try:
                quote = self._eastmoney_quote(normalized)
                result["pe"] = result["pe"] if result["pe"] is not None else quote.get("pe")
                result["pb"] = result["pb"] if result["pb"] is not None else quote.get("pb")
            except Exception:
                pass
        self._merge_tushare_fundamental(normalized, result)
        if os.getenv("MARKET_ENABLE_AK_FINANCIALS") != "1":
            return result
        try:
            import akshare as ak

            if result["pe"] is None or result["pb"] is None:
                info = ak.stock_individual_info_em(symbol=symbol_to_ak(normalized))
                if not info.empty and {"item", "value"}.issubset(info.columns):
                    values = dict(zip(info["item"], info["value"]))
                    result["pe"] = result["pe"] if result["pe"] is not None else _to_float(values.get("市盈率-动态") or values.get("市盈率"))
                    result["pb"] = result["pb"] if result["pb"] is not None else _to_float(values.get("市净率"))
            abstract = ak.stock_financial_abstract_ths(symbol=symbol_to_ak(normalized), indicator="按年度")
            self._merge_financial_abstract(result, abstract)
        except TypeError:
            try:
                import akshare as ak

                abstract = ak.stock_financial_abstract_ths(symbol=symbol_to_ak(normalized))
                self._merge_financial_abstract(result, abstract)
            except Exception:
                pass
        except Exception:
            pass
        return result

    def _merge_tushare_fundamental(self, symbol: str, result: dict[str, float | None]) -> None:
        if not self.tushare_token:
            return
        try:
            pro = self._tushare_client(DataProviderError("Tushare fundamental requested"))
            indicator = pro.fina_indicator(ts_code=symbol_to_tushare(symbol), limit=1, fields="ts_code,roe,or_yoy")
            if indicator is None or indicator.empty:
                return
            row = indicator.iloc[0]
            result["roe"] = result["roe"] if result["roe"] is not None else _to_float(row.get("roe"))
            result["revenue_growth"] = result["revenue_growth"] if result["revenue_growth"] is not None else _to_float(row.get("or_yoy"))
        except Exception:
            return

    def get_news(self, symbol: str, limit: int = 20) -> list[str]:
        normalized = normalize_symbol(symbol)
        if os.getenv("MARKET_ENABLE_AK_NEWS") != "1":
            return []
        try:
            import akshare as ak

            frame = ak.stock_news_em(symbol=symbol_to_ak(normalized))
        except Exception:
            return []
        if frame.empty:
            return []
        title_col = _first_existing(frame, ["新闻标题", "标题", "title"])
        if not title_col:
            return []
        return [str(item) for item in frame[title_col].dropna().head(limit).tolist()]

    def _eastmoney_quote(self, symbol: str) -> dict[str, float | str | None]:
        secid = self._eastmoney_secid(symbol)
        params = {"secid": secid, "fields": "f43,f47,f48,f57,f58,f116,f162,f167,f170"}
        response = requests.get("https://push2.eastmoney.com/api/qt/stock/get", params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json().get("data") or {}
        if not data:
            raise DataProviderError(f"Eastmoney quote is empty for {symbol}")
        return {
            "code": normalize_symbol(data.get("f57") or symbol),
            "name": data.get("f58") or "",
            "price": self._eastmoney_scaled(data.get("f43")),
            "change_pct": self._eastmoney_scaled(data.get("f170")),
            "volume": _to_float(data.get("f47")),
            "amount": _to_float(data.get("f48")),
            "market_cap": _to_float(data.get("f116")),
            "pe": self._eastmoney_scaled(data.get("f162")),
            "pb": self._eastmoney_scaled(data.get("f167")),
        }

    def _tencent_quote(self, symbol: str) -> dict[str, float | str | None]:
        market_symbol = self._tencent_symbol(symbol)
        response = requests.get("https://web.sqt.gtimg.cn/q=" + market_symbol, timeout=self.timeout)
        response.raise_for_status()
        text = response.content.decode("gbk", errors="ignore")
        if '="' not in text:
            raise DataProviderError(f"Tencent quote response is unsupported for {symbol}")
        payload = text.split('="', 1)[1].rsplit('"', 1)[0]
        fields = payload.split("~")
        if len(fields) < 39 or not fields[2]:
            raise DataProviderError(f"Tencent quote is empty for {symbol}")
        price = _to_float(fields[3])
        change_pct = _to_float(fields[32])
        volume = _to_float(fields[36]) or _to_float(fields[6])
        amount = _to_float(fields[37]) or _to_float(fields[57])
        return {
            "code": normalize_symbol(fields[2]),
            "name": fields[1],
            "price": price,
            "change_pct": change_pct,
            "volume": volume,
            "amount": amount,
            "market_cap": _to_float(fields[45]) or _to_float(fields[80] if len(fields) > 80 else None),
            "pe": _to_float(fields[39] if len(fields) > 39 else None),
            "pb": _to_float(fields[46] if len(fields) > 46 else None),
        }

    def _eastmoney_daily(self, symbol: str, start: str, end: str, days: int) -> pd.DataFrame:
        params = {
            "secid": self._eastmoney_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "beg": start,
            "end": end,
        }
        response = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get", params=params, timeout=self.timeout)
        response.raise_for_status()
        klines = (response.json().get("data") or {}).get("klines") or []
        if not klines:
            raise DataProviderError(f"Eastmoney daily bars are empty for {symbol}")
        rows = []
        for item in klines:
            parts = item.split(",")
            if len(parts) < 7:
                continue
            rows.append(
                {
                    "date": parts[0],
                    "open": parts[1],
                    "close": parts[2],
                    "high": parts[3],
                    "low": parts[4],
                    "volume": parts[5],
                    "amount": parts[6],
                    "change_pct": parts[8] if len(parts) > 8 else None,
                    "code": symbol,
                }
            )
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise DataProviderError(f"Eastmoney daily bars are empty for {symbol}")
        for col in ["open", "close", "high", "low", "volume", "amount", "change_pct"]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.sort_values("date").tail(days).reset_index(drop=True)

    def _tencent_daily(self, symbol: str, days: int) -> pd.DataFrame:
        market_symbol = self._tencent_symbol(symbol)
        params = {"param": f"{market_symbol},day,,,{max(days, 80)},"}
        response = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json().get("data", {}).get(market_symbol, {})
        rows = data.get("day") or data.get("qfqday") or []
        if not rows:
            raise DataProviderError(f"Tencent daily bars are empty for {symbol}")
        frame = pd.DataFrame(
            [
                {
                    "date": row[0],
                    "open": row[1],
                    "close": row[2],
                    "high": row[3],
                    "low": row[4],
                    "volume": row[5],
                    "amount": None,
                    "code": normalize_symbol(symbol),
                }
                for row in rows
                if len(row) >= 6
            ]
        )
        if frame.empty:
            raise DataProviderError(f"Tencent daily bars are empty for {symbol}")
        for col in ["open", "close", "high", "low", "volume", "amount"]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame["change_pct"] = frame["close"].pct_change() * 100
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.sort_values("date").tail(days).reset_index(drop=True)

    @staticmethod
    def _eastmoney_secid(symbol: str) -> str:
        normalized = normalize_symbol(symbol)
        code, suffix = normalized.split(".")
        market = "1" if suffix == "SH" else "0"
        return f"{market}.{code}"

    @staticmethod
    def _tencent_symbol(symbol: str) -> str:
        normalized = normalize_symbol(symbol)
        code, suffix = normalized.split(".")
        prefix = "sh" if suffix == "SH" else "sz"
        return f"{prefix}{code}"

    @staticmethod
    def _eastmoney_scaled(value: Any) -> float | None:
        parsed = _to_float(value)
        if parsed is None or parsed == -1:
            return None
        return parsed / 100

    def _tushare_stock_basic(self, primary_error: Exception) -> pd.DataFrame:
        pro = self._tushare_client(primary_error)
        return pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")

    def _tushare_stock_spot(self, primary_error: Exception) -> pd.DataFrame:
        pro = self._tushare_client(primary_error)
        stocks = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        daily = pro.daily_basic(trade_date=self._latest_trade_date(pro), fields="ts_code,close,pct_chg,volume,total_mv")
        frame = stocks.merge(daily, on="ts_code", how="left")
        return frame.rename(columns={"close": "最新价", "pct_chg": "涨跌幅", "volume": "成交量", "total_mv": "总市值"})

    def _tushare_daily(self, symbol: str, start: str, end: str, primary_error: Exception) -> pd.DataFrame:
        try:
            import tushare as ts

            token = self.tushare_token
            if not token:
                raise DataProviderError(f"AkShare daily failed and TUSHARE_TOKEN is not set: {primary_error}")
            frame = ts.pro_bar(ts_code=symbol_to_tushare(symbol), adj="qfq", start_date=start, end_date=end)
        except Exception as exc:
            raise DataProviderError(f"AkShare daily failed; Tushare fallback failed: {exc}") from exc
        if frame is None:
            return pd.DataFrame()
        return frame.rename(
            columns={
                "trade_date": "日期",
                "open": "开盘",
                "close": "收盘",
                "high": "最高",
                "low": "最低",
                "vol": "成交量",
                "amount": "成交额",
                "pct_chg": "涨跌幅",
            }
        )

    def _tushare_client(self, primary_error: Exception):
        try:
            import tushare as ts
        except Exception as exc:
            raise DataProviderError(f"AkShare failed and Tushare is not installed: {primary_error}") from exc
        if not self.tushare_token:
            raise DataProviderError(f"AkShare failed and TUSHARE_TOKEN is not set: {primary_error}")
        ts.set_token(self.tushare_token)
        return ts.pro_api()

    @staticmethod
    def _latest_trade_date(pro) -> str:
        today = date.today().strftime("%Y%m%d")
        calendar = pro.trade_cal(exchange="SSE", start_date=(date.today() - timedelta(days=14)).strftime("%Y%m%d"), end_date=today)
        opened = calendar.loc[calendar["is_open"] == 1, "cal_date"]
        if opened.empty:
            return today
        return str(opened.max())

    @staticmethod
    def _merge_financial_abstract(result: dict[str, float | None], frame: pd.DataFrame) -> None:
        if frame is None or frame.empty:
            return
        text_cols = [col for col in frame.columns if str(col) in {"指标", "项目", "报告期"}]
        value_cols = [col for col in frame.columns if col not in text_cols]
        for _, row in frame.iterrows():
            label = " ".join(str(row.get(col, "")) for col in text_cols)
            latest = next((_to_float(row.get(col)) for col in value_cols if _to_float(row.get(col)) is not None), None)
            if latest is None:
                continue
            if result["roe"] is None and ("净资产收益率" in label or "ROE" in label.upper()):
                result["roe"] = latest
            if result["revenue_growth"] is None and ("营业总收入同比增长率" in label or "营业收入同比增长率" in label):
                result["revenue_growth"] = latest
