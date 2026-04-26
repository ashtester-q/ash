"""
美股映射背离机会分析模块。
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import FILTER_CONFIG, OUTPUT_DIR
from data.sector_mapping_data import SECTOR_MAPPING

logger = logging.getLogger(__name__)


@dataclass
class DivergenceRecord:
    """单个中美映射背离分析结果。"""

    sector: str
    us_sector: str
    us_etf: str
    us_20d: float
    cn_20d: float
    us_5d: float
    cn_5d: float
    gap: float
    macd_status: str
    rating: str
    dynamic_gap_threshold: float
    bottom_divergence: bool


class DivergenceAnalyzer:
    """分析美股行业 ETF 与 A股映射板块之间的阶段背离。"""

    def __init__(
        self,
        cn_fetcher: Any,
        us_fetcher: Any,
        tech_analyzer: Any,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.cn_fetcher = cn_fetcher
        self.us_fetcher = us_fetcher
        self.tech_analyzer = tech_analyzer
        self.config = config or FILTER_CONFIG
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def run(
        self,
        sector_results: Any = None,
        div_us20: Optional[float] = None,
        div_cn20: Optional[float] = None,
        div_us5: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        执行背离筛选、日线 MACD 分析并输出 CSV。

        Args:
            sector_results: scan_all_sectors() 返回值或 SectorScanResult 列表
            div_us20: 美股20日涨幅阈值
            div_cn20: A股20日涨幅阈值
            div_us5: 美股5日涨幅阈值
        """
        thresholds = {
            "us20": float(div_us20 if div_us20 is not None else self.config.get("div_us20", 5.0)),
            "cn20": float(div_cn20 if div_cn20 is not None else self.config.get("div_cn20", 2.0)),
            "us5": float(div_us5 if div_us5 is not None else self.config.get("div_us5", 3.0)),
        }

        records: List[DivergenceRecord] = []
        for sector_name in self._extract_sector_names(sector_results):
            mapping = self._find_mapping_for_cn_sector(sector_name)
            if not mapping:
                continue

            us_sector, mapping_data = mapping
            etf_code = mapping_data.get("us_etf_code") or self.us_fetcher.SECTOR_ETFS.get(us_sector)
            if not etf_code:
                logger.debug("跳过无ETF映射板块: %s", sector_name)
                continue

            cn_hist = self._safe_fetch(self.cn_fetcher.fetch_sector_history, sector_name, 90)
            us_hist = self._safe_fetch(self.us_fetcher.fetch_etf_history, etf_code, 90)
            if cn_hist.empty or us_hist.empty:
                continue

            cn_5d = self._period_return(cn_hist, 5)
            cn_20d = self._period_return(cn_hist, 20)
            us_5d = self._period_return(us_hist, 5)
            us_20d = self._period_return(us_hist, 20)
            gap = us_20d - cn_20d
            dynamic_gap = self._dynamic_gap_threshold(us_hist, cn_hist)

            is_candidate = (
                (us_20d > thresholds["us20"] and cn_20d < thresholds["cn20"])
                or (us_5d > thresholds["us5"] and cn_5d < 0)
                or (gap > dynamic_gap and us_20d > 0 and cn_20d < thresholds["cn20"])
            )
            if not is_candidate:
                continue

            macd = self._analyze_daily_macd(cn_hist)
            rating = self._rate_opportunity(gap, macd)

            records.append(DivergenceRecord(
                sector=sector_name,
                us_sector=us_sector,
                us_etf=etf_code,
                us_20d=round(us_20d, 2),
                cn_20d=round(cn_20d, 2),
                us_5d=round(us_5d, 2),
                cn_5d=round(cn_5d, 2),
                gap=round(gap, 2),
                macd_status=macd["status"],
                rating=rating,
                dynamic_gap_threshold=round(dynamic_gap, 2),
                bottom_divergence=macd["bottom_divergence"],
            ))

        df = self._to_dataframe(records)
        self._print_table(df)
        if not df.empty:
            path = OUTPUT_DIR / f"divergence_{self.timestamp}.csv"
            df.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"📁 背离机会已保存: {Path(path).name}")
        return df

    def _extract_sector_names(self, sector_results: Any) -> List[str]:
        """从 scan_all_sectors 输出中提取已扫描板块名称。"""
        if isinstance(sector_results, dict):
            sector_results = sector_results.get("results", [])
        if not sector_results:
            return sorted({item.get("cn_name", "") for item in SECTOR_MAPPING.values() if item.get("cn_name")})

        names = []
        for item in sector_results:
            name = getattr(item, "sector_name", None)
            if name is None and isinstance(item, dict):
                name = item.get("sector_name")
            if name:
                names.append(str(name))
        return sorted(set(names))

    def _find_mapping_for_cn_sector(self, sector_name: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """按 A股板块名称查找美股映射。"""
        for us_sector, mapping in SECTOR_MAPPING.items():
            cn_name = mapping.get("cn_name", "")
            if cn_name and (cn_name in sector_name or sector_name in cn_name):
                return us_sector, mapping
        return None

    @staticmethod
    def _safe_fetch(fetch_func, *args) -> pd.DataFrame:
        """保护性调用 fetcher，避免单个数据源失败中断全局扫描。"""
        try:
            df = fetch_func(*args)
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        except Exception as exc:
            logger.warning("数据获取失败 %s%r: %s", getattr(fetch_func, "__name__", "fetch"), args, exc)
            return pd.DataFrame()

    @staticmethod
    def _period_return(df: pd.DataFrame, window: int) -> float:
        """计算 window 个交易日累计收益率。"""
        if df.empty or "close" not in df.columns or len(df) < 2:
            return 0.0
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(close) < 2:
            return 0.0
        start_idx = max(0, len(close) - window - 1)
        start = float(close.iloc[start_idx])
        end = float(close.iloc[-1])
        return ((end / start) - 1.0) * 100 if start > 0 else 0.0

    def _dynamic_gap_threshold(self, us_hist: pd.DataFrame, cn_hist: pd.DataFrame) -> float:
        """若历史平均背离大于波动标准差，则自动抬升背离阈值。"""
        default_gap = float(self.config.get("min_gap_20d", 5.0))
        if len(us_hist) < 35 or len(cn_hist) < 35:
            return default_gap

        us_close = pd.to_numeric(us_hist["close"], errors="coerce").dropna().reset_index(drop=True)
        cn_close = pd.to_numeric(cn_hist["close"], errors="coerce").dropna().reset_index(drop=True)
        n = min(len(us_close), len(cn_close))
        if n < 35:
            return default_gap

        us_ret = us_close.tail(n).pct_change(20) * 100
        cn_ret = cn_close.tail(n).pct_change(20) * 100
        gaps = (us_ret - cn_ret).dropna()
        if gaps.empty:
            return default_gap

        avg_gap = float(gaps.mean())
        std_gap = float(gaps.std(ddof=0))
        if avg_gap > std_gap:
            return max(default_gap, avg_gap)
        return default_gap

    def _analyze_daily_macd(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算日线 MACD 状态、柱体趋势和底背离。"""
        close = pd.to_numeric(df["close"], errors="coerce").dropna().values
        if len(close) < 35:
            return {"status": "insufficient_data", "bottom_divergence": False, "golden_imminent": False}

        dif, dea, hist = self.tech_analyzer._calculate_macd(
            close,
            self.config.get("macd_fast", 12),
            self.config.get("macd_slow", 26),
            self.config.get("macd_signal", 9),
        )
        cross = self.tech_analyzer._check_macd_cross(dif, dea)
        position = "DIF>DEA" if dif[-1] > dea[-1] else "DIF<DEA"

        if hist[-1] >= 0:
            color = "red"
            bar_trend = "lengthening" if len(hist) >= 3 and hist[-1] > hist[-2] > hist[-3] else "shortening"
        else:
            color = "green"
            bar_trend = "shortening" if len(hist) >= 3 and hist[-1] > hist[-2] > hist[-3] else "declining"

        gap = dif[-1] - dea[-1]
        prev_gap = dif[-2] - dea[-2] if len(dif) >= 2 else gap
        golden_imminent = dif[-1] < dea[-1] and gap > prev_gap and abs(gap) <= max(abs(dea[-1]) * 0.2, 0.05)
        bottom_divergence = self._detect_bottom_divergence(close, hist)

        parts = [cross, position, f"{color}_{bar_trend}"]
        if golden_imminent:
            parts.append("golden_cross_imminent")
        if bottom_divergence:
            parts.append("bottom_divergence")

        return {
            "status": "/".join(parts),
            "bottom_divergence": bottom_divergence,
            "golden_imminent": golden_imminent,
            "cross": cross,
            "bar_trend": bar_trend,
            "hist_latest": float(hist[-1]),
        }

    @staticmethod
    def _detect_bottom_divergence(close: np.ndarray, hist: np.ndarray, lookback: int = 30) -> bool:
        """检测价格创新低但 MACD 柱未创新低的底背离。"""
        if len(close) < lookback or len(hist) < lookback:
            return False
        price_window = close[-lookback:]
        hist_window = hist[-lookback:]
        recent_price_low = np.min(price_window[-5:])
        prior_price_low = np.min(price_window[:-5])
        recent_hist_low = np.min(hist_window[-5:])
        prior_hist_low = np.min(hist_window[:-5])
        return bool(recent_price_low < prior_price_low and recent_hist_low > prior_hist_low)

    @staticmethod
    def _rate_opportunity(gap: float, macd: Dict[str, Any]) -> str:
        """结合背离幅度和 MACD 状态给出机会评级。"""
        clear_divergence = gap > 5
        if clear_divergence and (macd["bottom_divergence"] or macd["golden_imminent"] or macd.get("cross") == "golden_cross"):
            return "HIGH"
        if clear_divergence and macd.get("hist_latest", 0) < 0 and macd.get("bar_trend") == "shortening":
            return "WATCH"
        return "POTENTIAL"

    @staticmethod
    def _to_dataframe(records: Iterable[DivergenceRecord]) -> pd.DataFrame:
        """转换为输出 DataFrame。"""
        rows = [record.__dict__ for record in records]
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        return df.sort_values(["rating", "gap"], ascending=[True, False]).reset_index(drop=True)

    @staticmethod
    def _print_table(df: pd.DataFrame):
        """打印符合任务格式的背离机会表。"""
        print("\n📊 美股映射背离机会")
        if df.empty:
            print("暂无符合条件的背离机会")
            return

        print(f"{'Sector':16s} {'US 20d':>8s} {'CN 20d':>8s} {'Gap':>8s} {'MACD Status':38s} {'Rating':>10s}")
        print("-" * 94)
        for _, row in df.iterrows():
            status = str(row["macd_status"])[:38]
            print(
                f"{str(row['sector'])[:16]:16s} "
                f"{row['us_20d']:>+7.2f}% "
                f"{row['cn_20d']:>+7.2f}% "
                f"{row['gap']:>+7.2f}% "
                f"{status:38s} "
                f"{row['rating']:>10s}"
            )
