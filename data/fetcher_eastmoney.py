"""
东方财富数据源 fetcher。

用于补充 AKShare/yfinance 路径的交叉验证，不作为唯一数据源。
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import requests

from config import FILTER_CONFIG, HEADERS

logger = logging.getLogger(__name__)


class EastMoneyFetcher:
    """东方财富 API 数据获取器。"""

    CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.retry_max = int(FILTER_CONFIG.get("request_retry_max", 3))
        self.session = requests.Session()
        self.session.headers.update({
            **HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://quote.eastmoney.com/",
            "Host": "push2.eastmoney.com",
        })

    def _request_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """带重试的东方财富 JSON 请求。"""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.retry_max + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_error = exc
                if attempt >= self.retry_max:
                    break
        raise last_error if last_error else RuntimeError("EastMoney request failed")

    @staticmethod
    def _stock_secid(symbol: str) -> str:
        """将 A股代码转换为东方财富 secid。"""
        code = symbol.lower().replace("sh", "").replace("sz", "").replace("bj", "")
        if code.startswith(("6", "9")):
            return f"1.{code}"
        if code.startswith(("0", "2", "3")):
            return f"0.{code}"
        if code.startswith(("4", "8")):
            return f"0.{code}"
        return code

    def fetch_sector_list(self) -> pd.DataFrame:
        """
        获取东方财富行业板块列表。

        Returns:
            DataFrame columns: sector_code, sector_name, change_pct, current_price, volume, amount
        """
        params = {
            "pn": 1,
            "pz": 200,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:2",
            "fields": "f12,f14,f2,f3,f5,f6",
        }
        try:
            payload = self._request_json(self.CLIST_URL, params)
            rows = payload.get("data", {}).get("diff", []) or []
            records = []
            for row in rows:
                records.append({
                    "sector_code": row.get("f12"),
                    "sector_name": row.get("f14"),
                    "current_price": row.get("f2"),
                    "change_pct": row.get("f3"),
                    "volume": row.get("f5"),
                    "amount": row.get("f6"),
                    "data_source": "eastmoney",
                })
            df = pd.DataFrame(records)
            for col in ["current_price", "change_pct", "volume", "amount"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        except Exception as exc:
            logger.warning("东方财富行业列表获取失败: %s", exc)
            return pd.DataFrame()

    def fetch_stock_kline(self, symbol: str, days: int = 120, adjust: str = "1") -> pd.DataFrame:
        """
        获取 A股历史 K 线。

        Args:
            symbol: 证券代码，如 600519、sh600519、sz002714
            days: 回溯天数
            adjust: 复权类型，东方财富 1=前复权，2=后复权，空=不复权
        """
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        params = {
            "secid": self._stock_secid(symbol),
            "klt": 101,
            "fqt": adjust,
            "beg": start,
            "end": end,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }
        try:
            payload = self._request_json(self.KLINE_URL, params)
            klines = payload.get("data", {}).get("klines", []) or []
            records = []
            for item in klines:
                parts = item.split(",")
                if len(parts) < 6:
                    continue
                records.append({
                    "date": parts[0],
                    "open": parts[1],
                    "close": parts[2],
                    "high": parts[3],
                    "low": parts[4],
                    "volume": parts[5],
                    "amount": parts[6] if len(parts) > 6 else None,
                    "change_pct": parts[8] if len(parts) > 8 else None,
                    "data_source": "eastmoney",
                })
            df = pd.DataFrame(records)
            if df.empty:
                return df
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "close", "high", "low", "volume", "amount", "change_pct"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.sort_values("date").reset_index(drop=True)
        except Exception as exc:
            logger.warning("东方财富K线获取失败 [%s]: %s", symbol, exc)
            return pd.DataFrame()
