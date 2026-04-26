"""
技术分析模块 - MACD(日线/周线)、支撑位/压力位(多方法共振)、趋势分析
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from config import FILTER_CONFIG

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class WeeklyMACDSignal:
    """周线MACD信号"""
    symbol: str = ""
    name: str = ""
    
    # MACD原始值
    dif: float = 0.0           # 快线 (12周EMA - 26周EMA)
    dea: float = 0.0           # 慢线 (DIF的9周EMA)
    macd_bar: float = 0.0      # MACD柱 = (DIF - DEA) * 2
    
    # 历史趋势
    bar_change_1w: float = 0.0     # 柱值较上周变化
    bar_change_2w: float = 0.0     # 柱值较前两周变化
    bar_acceleration: float = 0.0  # 加速度 (diff of diff)
    
    # 信号标记
    is_green_shortening: bool = False    # 绿柱缩短 (从最低点回升)
    is_red_lengthening: bool = False     # 红柱拉长加速
    has_golden_cross_expectation: bool = False  # 金叉预期 (DIF即将上穿DEA)
    consecutive_green_shorten: int = 0   # 连续绿柱缩短周数
    consecutive_red_lengthen: int = 0    # 连续红柱拉长周数
    
    # 综合评分
    signal_strength: float = 0.0   # 信号强度 (0~100)
    signal_type: str = "neutral"   # 'bullish' | 'bearish' | 'neutral'
    
    # MACD交叉状态
    cross_status: str = "none"     # 'golden_cross' | 'death_cross' | 'bullish' | 'bearish' | 'none'
    
    # DIF与DEA的关系
    dif_dea_gap: float = 0.0       # DIF - DEA 差值
    dif_dea_gap_change: float = 0.0  # 差值变化
    
    # 历史MACD柱值 (用于判断是否从最低点回升)
    bar_history: List[float] = field(default_factory=list)
    
    # 附加信息
    current_price: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'dif': round(self.dif, 4),
            'dea': round(self.dea, 4),
            'macd_bar': round(self.macd_bar, 4),
            'signal_type': self.signal_type,
            'signal_strength': round(self.signal_strength, 1),
            'cross_status': self.cross_status,
            'is_green_shortening': self.is_green_shortening,
            'is_red_lengthening': self.is_red_lengthening,
            'has_golden_cross_expectation': self.has_golden_cross_expectation,
            'consecutive_green_shorten': self.consecutive_green_shorten,
            'consecutive_red_lengthen': self.consecutive_red_lengthen,
            'green_shorten_strength': round(self.bar_acceleration, 4),
            'dif_dea_gap': round(self.dif_dea_gap, 4),
            'current_price': round(self.current_price, 2),
        }


@dataclass
class SupportResistanceResult:
    """支撑位/压力位分析结果"""
    symbol: str = ""
    name: str = ""
    current_price: float = 0.0
    
    # 斐波那契回撤位
    fib_supports: Dict[str, float] = field(default_factory=dict)   # {'0.382': xxx, '0.5': xxx, '0.618': xxx}
    fib_resistances: Dict[str, float] = field(default_factory=dict)
    
    # 前高前低
    recent_high: float = 0.0
    recent_low: float = 0.0
    pivot_highs: List[float] = field(default_factory=list)
    pivot_lows: List[float] = field(default_factory=list)
    
    # 均线支撑/压力
    ma_supports: Dict[int, float] = field(default_factory=dict)    # {20: xxx, 60: xxx}
    ma_resistances: Dict[int, float] = field(default_factory=dict)
    
    # 最近支撑位 (综合)
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    support_distance_pct: float = 0.0     # 距支撑位百分比
    resistance_distance_pct: float = 0.0  # 距压力位百分比
    
    # 成交量确认
    volume_confirm_support: bool = False   # 缩量回踩支撑
    volume_confirm_resistance: bool = False  # 放量突破压力
    
    # 多重支撑共振
    confluence_supports: List[Dict] = field(default_factory=list)   # 共振的支撑位列表
    confluence_resistances: List[Dict] = field(default_factory=list)
    best_support: Dict = field(default_factory=dict)   # 最佳支撑 (方法来源+价位)
    best_resistance: Dict = field(default_factory=dict)
    
    # 综合
    support_quality: str = "unknown"   # 'strong' | 'moderate' | 'weak'
    resistance_quality: str = "unknown"
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'current_price': round(self.current_price, 2),
            'nearest_support': round(self.nearest_support, 2),
            'nearest_resistance': round(self.nearest_resistance, 2),
            'support_distance_pct': round(self.support_distance_pct, 2),
            'resistance_distance_pct': round(self.resistance_distance_pct, 2),
            'support_quality': self.support_quality,
            'resistance_quality': self.resistance_quality,
            'fib_support_0.382': round(self.fib_supports.get('0.382', 0), 2),
            'fib_support_0.5': round(self.fib_supports.get('0.5', 0), 2),
            'fib_support_0.618': round(self.fib_supports.get('0.618', 0), 2),
            'recent_low': round(self.recent_low, 2),
            'recent_high': round(self.recent_high, 2),
            'ma_20': round(self.ma_supports.get(20, 0), 2),
            'ma_60': round(self.ma_supports.get(60, 0), 2),
            'volume_confirm_support': self.volume_confirm_support,
            'confluence_count': len(self.confluence_supports),
        }


@dataclass
class TechAnalysisResult:
    """完整技术分析结果"""
    symbol: str
    name: str
    macd_bullish: bool
    macd_histogram_trend: str
    weekly_macd: Optional[WeeklyMACDSignal] = None
    support_resistance: Optional[SupportResistanceResult] = None
    wave_count: Optional[int] = None
    wave_position: str = 'unknown'
    support_level: float = 0.0
    resistance_level: float = 0.0
    current_price: float = 0.0
    near_support: bool = False
    near_resistance: bool = False
    near_fib_support: bool = False
    near_ma_support: bool = False
    trend: str = 'sideways'
    summary: str = ''
    score: float = 50.0  # 综合评分


# ==================== 周线MACD分析器 ====================

class WeeklyMACDAnalyzer:
    """
    周线MACD套利分析器 ★★★
    
    核心逻辑：
    1. 计算周线MACD (12, 26, 9)
    2. 检测绿柱缩短转折点 (从最低点回升)
    3. 检测加速度 (diff of diff > 0)
    4. 检测金叉预期 (DIF即将上穿DEA)
    5. 综合评分
    """
    
    def __init__(self, config: dict = None):
        self.config = config or FILTER_CONFIG
    
    def resample_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        将日K线重采样为周K线
        
        Args:
            df: 日线DataFrame，必须包含 'date' (datetime) 和 'close' 列
                也可以包含 'high', 'low', 'volume'
                
        Returns:
            周线DataFrame: [date, close, high, low, volume]
        """
        if df.empty:
            return pd.DataFrame()
        
        df = df.copy()
        if 'date' not in df.columns:
            logger.error("缺少 'date' 列，无法重采样")
            return pd.DataFrame()
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 设置日期索引，使用周五作为周标识
        df['week'] = df['date'].dt.isocalendar().week.astype(int)
        df['year'] = df['date'].dt.isocalendar().year.astype(int)
        df['week_key'] = df['year'].astype(str) + '-W' + df['week'].astype(str).str.zfill(2)
        
        # 按周聚合 - 动态构建聚合字典，只聚合存在的列
        agg_dict = {
            'date': 'last',
            'close': 'last',
            'high': 'max',
            'low': 'min',
        }
        if 'open' in df.columns:
            agg_dict['open'] = 'first'
        if 'volume' in df.columns:
            agg_dict['volume'] = 'sum'
        
        weekly = df.groupby('week_key').agg(agg_dict).reset_index()
        weekly = weekly.sort_values('date').reset_index(drop=True)
        return weekly
    
    def calculate_weekly_macd(self, weekly_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        计算周线MACD
        
        Args:
            weekly_df: 周线DataFrame，需包含 'close' 列
            
        Returns:
            (dif, dea, histogram) 三个numpy数组
        """
        close = weekly_df['close'].values
        
        if len(close) < 35:  # 至少需要26+9周数据
            logger.warning(f"周线数据不足 {len(close)} 周，至少需要35周")
            return np.array([]), np.array([]), np.array([])
        
        fast = self.config.get('weekly_macd_fast', 12)
        slow = self.config.get('weekly_macd_slow', 26)
        signal = self.config.get('weekly_macd_signal', 9)
        
        # EMA计算
        def ema(data: np.ndarray, period: int) -> np.ndarray:
            result = np.zeros_like(data)
            multiplier = 2.0 / (period + 1)
            # 初始值用SMA
            result[:period] = np.mean(data[:period])
            for i in range(period, len(data)):
                result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
            return result
        
        # DIF = EMA(close, 12) - EMA(close, 26)
        ema_fast = ema(close, fast)
        ema_slow = ema(close, slow)
        dif = ema_fast - ema_slow
        
        # DEA = EMA(DIF, 9)
        dea = ema(dif, signal)
        
        # MACD柱 = (DIF - DEA) * 2
        histogram = 2 * (dif - dea)
        
        return dif, dea, histogram
    
    def detect_green_shortening(self, histogram: np.ndarray, 
                                min_weeks: int = None) -> Tuple[bool, int, float]:
        """
        检测绿柱缩短（看涨信号）
        
        核心逻辑：
        - MACD柱值为负（绿柱）
        - 从最低点开始回升（柱值上升）
        - 连续回升周数 >= min_weeks
        - 加速度为正
        
        Returns:
            (is_shortening, consecutive_weeks, acceleration)
        """
        if len(histogram) < 3:
            return False, 0, 0.0
        
        min_weeks = min_weeks or self.config.get('weekly_green_shorten_weeks', 2)
        
        last_bar = histogram[-1]
        
        # 当前柱值为负（绿柱）
        if last_bar >= 0:
            return False, 0, 0.0
        
        # 找最近N周的最低柱值
        lookback = min(20, len(histogram))
        recent_bars = histogram[-lookback:]
        min_idx = np.argmin(recent_bars)
        
        # 当前就是最低点，还没回升
        if min_idx == len(recent_bars) - 1:
            return False, 0, 0.0
        
        # 从最低点之后，从后往前检查最近几周的柱值是否连续回升
        # 从最近一周开始往回数，统计连续上升的周数
        ascending_bars = recent_bars[min_idx:]
        consecutive_up = 0
        for i in range(len(ascending_bars) - 1, 0, -1):
            if ascending_bars[i] > ascending_bars[i-1]:
                consecutive_up += 1
            else:
                break
        
        if consecutive_up < min_weeks:
            return False, consecutive_up, 0.0
        
        # 计算加速度 (二阶导) — 使用最近几周的差值变化
        # 取从最低点之后的所有上升段数据
        if len(ascending_bars) >= 3:
            first_diff = np.diff(ascending_bars)
            if len(first_diff) >= 2:
                # 使用最近的两个一阶差计算加速度
                acceleration = first_diff[-1] - first_diff[-2]
            else:
                acceleration = 0.0
        else:
            acceleration = 0.0
        
        return True, consecutive_up, acceleration
    
    def detect_red_lengthening(self, histogram: np.ndarray,
                                min_weeks: int = None) -> Tuple[bool, int, float]:
        """
        检测红柱拉长加速（看涨信号）
        
        从最近一周往前检查，看是否有连续N周的红柱拉长
        
        Returns:
            (is_lengthening, consecutive_weeks, acceleration)
        """
        if len(histogram) < 3:
            return False, 0, 0.0
        
        min_weeks = min_weeks or self.config.get('weekly_red_lengthen_weeks', 2)
        
        last_bar = histogram[-1]
        
        # 当前柱值为正（红柱）
        if last_bar <= 0:
            return False, 0, 0.0
        
        # 从最近一周向前检查连续拉长
        consecutive_up = 0
        for i in range(len(histogram) - 1, 0, -1):
            if histogram[i] > histogram[i-1]:
                consecutive_up += 1
            else:
                break
        
        if consecutive_up < min_weeks:
            return False, consecutive_up, 0.0
        
        # 加速度 — 使用最近3个柱值计算
        if len(histogram) >= 3:
            d1 = histogram[-1] - histogram[-2]
            d2 = histogram[-2] - histogram[-3]
            acceleration = d1 - d2
        else:
            acceleration = 0.0
        
        return True, consecutive_up, acceleration
    
    def check_golden_cross_expectation(self, dif: np.ndarray, dea: np.ndarray) -> Tuple[bool, float]:
        """
        检测金叉预期（DIF即将上穿DEA）
        
        条件：
        1. DIF < DEA (尚未金叉)
        2. DIF - DEA 的差值在收窄
        3. 按当前趋势，未来1-2周内可能金叉
        
        Returns:
            (has_expectation, weeks_to_cross)
        """
        if len(dif) < 3:
            return False, float('inf')
        
        current_dif = dif[-1]
        current_dea = dea[-1]
        
        # 已经金叉了
        if current_dif > current_dea:
            return False, 0
        
        gap = current_dif - current_dea
        prev_gap = dif[-2] - dea[-2]
        prev_gap2 = dif[-3] - dea[-3]
        
        # 差值是否在收窄 (负值减小，即趋于0)
        gap_change = gap - prev_gap
        gap_change_prev = prev_gap - prev_gap2
        
        # 需要差值在收窄 (gap_change > 0 意味着负值在减小)
        if gap_change <= 0:
            return False, float('inf')
        
        # 估算需要几周金叉
        if gap_change > 0:
            weeks_to_cross = abs(gap) / abs(gap_change) if gap_change != 0 else float('inf')
        else:
            weeks_to_cross = float('inf')
        
        # 未来4周内可能金叉
        has_expectation = weeks_to_cross <= 4
        
        return has_expectation, weeks_to_cross
    
    def analyze(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> Optional[WeeklyMACDSignal]:
        """
        完整分析周线MACD信号
        
        Args:
            df: 日线DataFrame (会被重采样为周线)
            symbol: 股票代码
            name: 股票名称
            
        Returns:
            WeeklyMACDSignal 或 None
        """
        if df.empty or len(df) < 60:
            logger.warning(f"{name} 数据不足，无法进行周线MACD分析")
            return None
        
        # 重采样为周线
        weekly = self.resample_to_weekly(df)
        if weekly.empty or len(weekly) < 35:
            logger.warning(f"{name} 周线数据不足 {len(weekly) if not weekly.empty else 0} 周")
            return None
        
        # 计算MACD
        dif, dea, histogram = self.calculate_weekly_macd(weekly)
        if len(dif) == 0:
            return None
        
        # 构建结果
        signal = WeeklyMACDSignal(
            symbol=symbol,
            name=name,
            dif=dif[-1],
            dea=dea[-1],
            macd_bar=histogram[-1],
            current_price=weekly['close'].iloc[-1] if 'close' in weekly.columns else 0,
        )
        
        # 柱值变化
        if len(histogram) >= 2:
            signal.bar_change_1w = histogram[-1] - histogram[-2]
        if len(histogram) >= 3:
            signal.bar_change_2w = histogram[-1] - histogram[-3]
            signal.bar_acceleration = (histogram[-1] - histogram[-2]) - (histogram[-2] - histogram[-3])
        
        # 绿柱缩短检测
        is_green_short, green_weeks, green_acc = self.detect_green_shortening(histogram)
        signal.is_green_shortening = is_green_short
        signal.consecutive_green_shorten = green_weeks
        signal.bar_acceleration = green_acc if is_green_short else signal.bar_acceleration
        
        # 红柱拉长检测
        is_red_long, red_weeks, red_acc = self.detect_red_lengthening(histogram)
        signal.is_red_lengthening = is_red_long
        signal.consecutive_red_lengthen = red_weeks
        
        # 金叉预期检测
        has_exp, weeks_to_cross = self.check_golden_cross_expectation(dif, dea)
        signal.has_golden_cross_expectation = has_exp
        
        # DIF-DEA差值
        signal.dif_dea_gap = dif[-1] - dea[-1]
        if len(dif) >= 2:
            signal.dif_dea_gap_change = (dif[-1] - dea[-1]) - (dif[-2] - dea[-2])
        
        # 交叉状态
        if len(dif) >= 2 and len(dea) >= 2:
            if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
                signal.cross_status = 'golden_cross'
            elif dif[-1] < dea[-1] and dif[-2] >= dea[-2]:
                signal.cross_status = 'death_cross'
            elif dif[-1] > dea[-1]:
                signal.cross_status = 'bullish'
            else:
                signal.cross_status = 'bearish'
        
        # 保存柱值历史
        signal.bar_history = histogram[-10:].tolist()
        
        # 综合信号评分
        signal.signal_strength, signal.signal_type = self._score_signal(signal)
        
        return signal
    
    def _score_signal(self, signal: WeeklyMACDSignal) -> Tuple[float, str]:
        """
        综合评分看涨/看跌信号强度
        
        评分项：
        - 绿柱缩短: +30分
        - 加速度为正: +20分
        - 金叉预期: +25分
        - 连续缩短周数: +5/周
        - 红柱拉长加速: +20分
        - 已金叉: +15分
        """
        score = 50.0  # 中性基准分
        signal_type = "neutral"
        
        # 绿柱缩短（主要看涨信号）
        if signal.is_green_shortening:
            score += 30
            score += min(signal.consecutive_green_shorten * 5, 15)
            if signal.bar_acceleration > 0:
                score += 20
            signal_type = "bullish"
        
        # 红柱拉长加速
        if signal.is_red_lengthening:
            score += 20
            score += min(signal.consecutive_red_lengthen * 5, 10)
            if signal.bar_acceleration > 0:
                score += 15
            if signal_type == "neutral":
                signal_type = "bullish"
        
        # 金叉预期
        if signal.has_golden_cross_expectation:
            score += 25
            if signal_type == "neutral":
                signal_type = "bullish"
        
        # 已金叉
        if signal.cross_status == 'golden_cross':
            score += 15
            signal_type = "bullish"
        elif signal.cross_status == 'death_cross':
            score -= 25
            signal_type = "bearish"
        
        # DIF-DEA差值趋势
        if signal.dif_dea_gap_change > 0:
            score += 10
        elif signal.dif_dea_gap_change < 0:
            score -= 10
        
        # 限制范围
        score = max(0, min(100, score))
        
        if score >= 65:
            signal_type = "bullish"
        elif score <= 35:
            signal_type = "bearish"
        else:
            signal_type = "neutral"
        
        return score, signal_type


# ==================== 支撑位/压力位分析器 ====================

class SupportResistanceAnalyzer:
    """
    支撑位/压力位分析器
    
    使用多种方法：
    1. 斐波那契回撤 (0.382, 0.5, 0.618)
    2. 前高前低 (波段高低点)
    3. 均线支撑 (20周线, 60周线)
    4. 成交量确认
    5. 多重支撑共振
    """
    
    def __init__(self, config: dict = None):
        self.config = config or FILTER_CONFIG
    
    def analyze(self, df: pd.DataFrame, symbol: str = "", name: str = "") -> Optional[SupportResistanceResult]:
        """
        完整支撑位/压力位分析
        
        Args:
            df: 日线DataFrame，需包含 [date, close, high, low, volume]
            symbol: 股票代码
            name: 股票名称
            
        Returns:
            SupportResistanceResult 或 None
        """
        if df.empty or len(df) < 30:
            return None
        
        # 先转周线再做分析
        weekly = self._resample_to_weekly(df)
        if weekly.empty or len(weekly) < 10:
            return None
        
        close_weekly = weekly['close'].values
        high_weekly = weekly['high'].values
        low_weekly = weekly['low'].values
        volume_weekly = weekly['volume'].values if 'volume' in weekly.columns else None
        
        current_price = close_weekly[-1]
        
        result = SupportResistanceResult(
            symbol=symbol,
            name=name,
            current_price=current_price,
        )
        
        # 1. 斐波那契回撤
        fib_supports, fib_resistances = self._fibonacci_levels(high_weekly, low_weekly, close_weekly)
        result.fib_supports = fib_supports
        result.fib_resistances = fib_resistances
        
        # 2. 前高前低
        pivot_highs, pivot_lows = self._find_pivot_points(high_weekly, low_weekly)
        result.pivot_highs = pivot_highs
        result.pivot_lows = pivot_lows
        result.recent_high = max(high_weekly[-20:]) if len(high_weekly) >= 20 else max(high_weekly)
        result.recent_low = min(low_weekly[-20:]) if len(low_weekly) >= 20 else min(low_weekly)
        
        # 3. 均线支撑/压力
        ma_supports, ma_resistances = self._ma_levels(close_weekly)
        result.ma_supports = ma_supports
        result.ma_resistances = ma_resistances
        
        # 4. 成交量确认
        if volume_weekly is not None and len(volume_weekly) >= 10:
            vol_confirm_support, vol_confirm_resistance = self._volume_confirmation(
                close_weekly, volume_weekly, pivot_lows, pivot_highs
            )
            result.volume_confirm_support = vol_confirm_support
            result.volume_confirm_resistance = vol_confirm_resistance
        
        # 5. 多重支撑共振
        confluence_supports, confluence_resistances = self._find_confluence(
            current_price, fib_supports, fib_resistances,
            pivot_lows, pivot_highs,
            ma_supports, ma_resistances
        )
        result.confluence_supports = confluence_supports
        result.confluence_resistances = confluence_resistances
        
        # 6. 最近支撑/压力位
        nearest_support, nearest_resistance = self._find_nearest_levels(
            current_price, confluence_supports, confluence_resistances
        )
        result.nearest_support = nearest_support
        result.nearest_resistance = nearest_resistance
        
        if nearest_support > 0:
            result.support_distance_pct = ((current_price - nearest_support) / current_price) * 100
        if nearest_resistance > 0:
            result.resistance_distance_pct = ((nearest_resistance - current_price) / current_price) * 100
        
        # 7. 最佳支撑/压力位
        result.best_support = self._get_best_level(confluence_supports, 'support')
        result.best_resistance = self._get_best_level(confluence_resistances, 'resistance')
        
        # 8. 质量评估
        result.support_quality = self._assess_quality(confluence_supports, 'support')
        result.resistance_quality = self._assess_quality(confluence_resistances, 'resistance')
        
        return result
    
    def _resample_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """日线转周线"""
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        df['year'] = df['date'].dt.isocalendar().year.astype(int)
        df['week'] = df['date'].dt.isocalendar().week.astype(int)
        df['week_key'] = df['year'].astype(str) + '-W' + df['week'].astype(str).str.zfill(2)
        
        agg_dict = {
            'date': 'last',
            'close': 'last',
            'high': 'max',
            'low': 'min',
        }
        if 'open' in df.columns:
            agg_dict['open'] = 'first'
        if 'volume' in df.columns:
            agg_dict['volume'] = 'sum'
        
        weekly = df.groupby('week_key').agg(agg_dict).reset_index()
        weekly = weekly.sort_values('date').reset_index(drop=True)
        return weekly
    
    def _fibonacci_levels(self, high: np.ndarray, low: np.ndarray, 
                          close: np.ndarray) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        计算斐波那契回撤位
        
        从最近一个显著波段（高点-低点）计算回撤
        """
        lookback = min(30, len(close))
        
        # 找到最近波段的高低点
        recent_high_idx = np.argmax(high[-lookback:])
        recent_low_idx = np.argmin(low[-lookback:])
        
        # 确定波段方向（先有高点的下跌波段，或先有低点的上涨波段）
        if recent_high_idx < recent_low_idx:
            # 下跌波段：从高点到低点
            start_price = high[-lookback:][recent_high_idx]
            end_price = low[-lookback:][recent_low_idx]
            is_downtrend = True
        else:
            # 上涨波段：从低点到高点
            start_price = low[-lookback:][recent_low_idx]
            end_price = high[-lookback:][recent_high_idx]
            is_downtrend = False
        
        diff = abs(end_price - start_price)
        
        fib_levels = self.config.get('fib_levels', [0.236, 0.382, 0.5, 0.618, 0.786])
        
        supports = {}
        resistances = {}
        
        for level in fib_levels:
            level_str = str(level)
            if is_downtrend:
                # 下跌后反弹，回撤位是压力位
                fib_price = start_price - diff * level
                if fib_price < close[-1]:
                    supports[level_str] = fib_price
                else:
                    resistances[level_str] = fib_price
            else:
                # 上涨后回调，回撤位是支撑位
                fib_price = start_price + diff * level
                if fib_price < close[-1]:
                    supports[level_str] = fib_price
                else:
                    resistances[level_str] = fib_price
        
        return supports, resistances
    
    def _find_pivot_points(self, high: np.ndarray, low: np.ndarray) -> Tuple[List[float], List[float]]:
        """
        找到波段高低点（枢轴点）
        
        Args:
            high: 最高价数组
            low: 最低价数组
            
        Returns:
            (pivot_highs, pivot_lows) 价格列表
        """
        lookback = self.config.get('pivot_lookback_weeks', 20)
        n = min(lookback, len(high))
        
        pivot_highs = []
        pivot_lows = []
        
        # 使用scipy寻找局部极值（如果可用）
        try:
            from scipy.signal import argrelextrema
            local_max_idx = argrelextrema(high[-n:], np.greater, order=3)[0]
            local_min_idx = argrelextrema(low[-n:], np.less, order=3)[0]
            
            pivot_highs = [float(high[-n:][idx]) for idx in local_max_idx]
            pivot_lows = [float(low[-n:][idx]) for idx in local_min_idx]
        except ImportError:
            # 手动寻找
            for i in range(3, n - 3):
                if high[-n:][i] == max(high[-n:][i-3:i+4]):
                    pivot_highs.append(float(high[-n:][i]))
                if low[-n:][i] == min(low[-n:][i-3:i+4]):
                    pivot_lows.append(float(low[-n:][i]))
        
        return pivot_highs, pivot_lows
    
    def _ma_levels(self, close: np.ndarray) -> Tuple[Dict[int, float], Dict[int, float]]:
        """
        计算均线支撑/压力位
        
        Returns:
            (ma_supports, ma_resistances)
        """
        periods = self.config.get('ma_support_periods', [20, 60])
        
        ma_supports = {}
        ma_resistances = {}
        current_price = close[-1]
        
        for period in periods:
            if len(close) >= period:
                ma_value = np.mean(close[-period:])
                if ma_value < current_price:
                    ma_supports[period] = float(ma_value)
                else:
                    ma_resistances[period] = float(ma_value)
        
        return ma_supports, ma_resistances
    
    def _volume_confirmation(self, close: np.ndarray, volume: np.ndarray,
                              pivot_lows: List[float], pivot_highs: List[float]) -> Tuple[bool, bool]:
        """
        成交量确认支撑/压力
        
        - 缩量回踩支撑 = 支撑有效
        - 放量突破压力 = 突破有效
        
        Returns:
            (support_confirmed, resistance_confirmed)
        """
        if len(volume) < 10:
            return False, False
        
        current_price = close[-1]
        avg_volume = np.mean(volume[-10:])
        recent_volume = volume[-1]
        
        support_confirmed = False
        resistance_confirmed = False
        
        # 检查是否在支撑位附近
        for pivot_low in pivot_lows:
            if abs(current_price - pivot_low) / current_price < 0.03:
                # 在支撑位附近，检查成交量是否萎缩
                if recent_volume < avg_volume * 0.8:
                    support_confirmed = True
                break
        
        # 检查是否在压力位附近
        for pivot_high in pivot_highs:
            if abs(current_price - pivot_high) / current_price < 0.03:
                # 在压力位附近，检查成交量是否放大
                if recent_volume > avg_volume * 1.3:
                    resistance_confirmed = True
                break
        
        return support_confirmed, resistance_confirmed
    
    def _find_confluence(self, current_price: float,
                          fib_supports: Dict, fib_resistances: Dict,
                          pivot_lows: List[float], pivot_highs: List[float],
                          ma_supports: Dict, ma_resistances: Dict) -> Tuple[List[Dict], List[Dict]]:
        """
        寻找多重支撑/压力共振
        
        将不同方法得出的价位进行聚类，当多个方法指向同一价位时标记为共振
        
        Returns:
            (confluence_supports, confluence_resistances)
        """
        tolerance = self.config.get('support_confluence_tolerance', 0.02)
        
        # 收集所有支撑位（带来源标签）
        all_supports = []
        for level_key, price in fib_supports.items():
            all_supports.append({'price': price, 'method': f'fib_{level_key}', 'type': 'fibonacci'})
        for price in pivot_lows:
            all_supports.append({'price': price, 'method': 'pivot_low', 'type': 'pivot'})
        for period, price in ma_supports.items():
            all_supports.append({'price': price, 'method': f'ma_{period}', 'type': 'moving_average'})
        
        # 收集所有压力位
        all_resistances = []
        for level_key, price in fib_resistances.items():
            all_resistances.append({'price': price, 'method': f'fib_{level_key}', 'type': 'fibonacci'})
        for price in pivot_highs:
            all_resistances.append({'price': price, 'method': 'pivot_high', 'type': 'pivot'})
        for period, price in ma_resistances.items():
            all_resistances.append({'price': price, 'method': f'ma_{period}', 'type': 'moving_average'})
        
        # 聚类算法：将相近价位聚类
        def cluster_levels(levels: List[Dict], tol: float) -> List[Dict]:
            if not levels:
                return []
            
            # 按价格排序
            sorted_levels = sorted(levels, key=lambda x: x['price'])
            
            clusters = []
            current_cluster = [sorted_levels[0]]
            
            for level in sorted_levels[1:]:
                if abs(level['price'] - current_cluster[-1]['price']) / max(current_cluster[-1]['price'], 1) <= tol:
                    current_cluster.append(level)
                else:
                    # 保存当前聚类
                    if len(current_cluster) >= 1:
                        avg_price = np.mean([l['price'] for l in current_cluster])
                        methods = [l['method'] for l in current_cluster]
                        types = list(set([l['type'] for l in current_cluster]))
                        clusters.append({
                            'price': round(float(avg_price), 2),
                            'methods': methods,
                            'types': types,
                            'count': len(current_cluster),
                            'unique_types': len(types),
                        })
                    current_cluster = [level]
            
            # 最后一个聚类
            if current_cluster:
                avg_price = np.mean([l['price'] for l in current_cluster])
                methods = [l['method'] for l in current_cluster]
                types = list(set([l['type'] for l in current_cluster]))
                clusters.append({
                    'price': round(float(avg_price), 2),
                    'methods': methods,
                    'types': types,
                    'count': len(current_cluster),
                    'unique_types': len(types),
                })
            
            return clusters
        
        confluence_supports = cluster_levels(all_supports, tolerance)
        confluence_resistances = cluster_levels(all_resistances, tolerance)
        
        # 只保留当前价格下方的支撑和上方的压力
        confluence_supports = [s for s in confluence_supports if s['price'] < current_price]
        confluence_resistances = [r for r in confluence_resistances if r['price'] > current_price]
        
        return confluence_supports, confluence_resistances
    
    def _find_nearest_levels(self, current_price: float,
                               confluence_supports: List[Dict],
                               confluence_resistances: List[Dict]) -> Tuple[float, float]:
        """找到最近的支撑位和压力位"""
        nearest_support = 0.0
        nearest_resistance = 0.0
        
        # 找最近支撑
        supports_below = [s for s in confluence_supports if s['price'] < current_price]
        if supports_below:
            nearest_support = max(supports_below, key=lambda x: x['price'])['price']
        
        # 如果没有共振支撑，用最近低点
        if nearest_support == 0 and confluence_supports:
            nearest_support = max(s['price'] for s in confluence_supports)
        
        # 找最近压力
        resistances_above = [r for r in confluence_resistances if r['price'] > current_price]
        if resistances_above:
            nearest_resistance = min(resistances_above, key=lambda x: x['price'])['price']
        
        if nearest_resistance == 0 and confluence_resistances:
            nearest_resistance = min(r['price'] for r in confluence_resistances)
        
        return nearest_support, nearest_resistance
    
    def _get_best_level(self, confluence_levels: List[Dict], level_type: str) -> Dict:
        """
        获取最佳支撑/压力位
        
        标准：方法来源越多、类型越多样越好
        """
        if not confluence_levels:
            return {'price': 0, 'methods': [], 'count': 0}
        
        # 按方法数量 + 类型数量 排序
        def score(level):
            return level['count'] * 0.6 + level['unique_types'] * 0.4
        
        best = max(confluence_levels, key=score)
        best['type'] = level_type
        return best
    
    def _assess_quality(self, confluence_levels: List[Dict], level_type: str) -> str:
        """
        评估支撑/压力质量
        
        - strong: 3种方法以上共振，或2种方法+成交量确认
        - moderate: 2种方法共振
        - weak: 仅1种方法
        """
        if not confluence_levels:
            return 'weak'
        
        # 找最佳的那个
        def score(level):
            return level['count'] * 0.6 + level['unique_types'] * 0.4
        
        best = max(confluence_levels, key=score)
        
        if best['unique_types'] >= 3:
            return 'strong'
        elif best['unique_types'] >= 2:
            return 'moderate'
        else:
            return 'weak'


# ==================== 综合技术分析器 ====================

class TechnicalAnalyzer:
    """
    综合技术分析器
    - MACD (日线/周线)
    - 支撑位/压力位 (多方法共振)
    - 趋势分析
    """
    
    def __init__(self):
        self.config = FILTER_CONFIG
        self.weekly_macd = WeeklyMACDAnalyzer()
        self.sr_analyzer = SupportResistanceAnalyzer()
    
    def analyze(self, df: pd.DataFrame, name: str = "", 
                symbol: str = "") -> Optional[TechAnalysisResult]:
        """
        综合分析一只股票/板块的技术面
        """
        if df.empty or len(df) < 30:
            logger.warning(f"{name} 数据不足，无法进行技术分析")
            return None
        
        close = df['close'].values
        high = df['high'].values if 'high' in df.columns else close
        low = df['low'].values if 'low' in df.columns else close
        current_price = float(close[-1])
        
        # ===== 日线MACD分析 =====
        macd_line, signal_line, histogram = self._calculate_macd(close)
        macd_bullish = len(macd_line) > 0 and macd_line[-1] > signal_line[-1]
        macd_cross = self._check_macd_cross(macd_line, signal_line)
        
        # 直方图趋势
        if len(histogram) >= 3:
            if histogram[-1] > histogram[-2] > histogram[-3]:
                hist_trend = 'rising'
            elif histogram[-1] < histogram[-2] < histogram[-3]:
                hist_trend = 'falling'
            else:
                hist_trend = 'neutral'
        else:
            hist_trend = 'neutral'
        
        # ===== 周线MACD分析 =====
        weekly_signal = self.weekly_macd.analyze(df, symbol, name)
        
        # ===== 支撑压力位分析 =====
        sr_result = self.sr_analyzer.analyze(df, symbol, name)
        
        # ===== 综合评估 =====
        support_level = 0.0
        resistance_level = 0.0
        near_support = False
        near_resistance = False
        near_fib_support = False
        near_ma_support = False
        
        if sr_result:
            support_level = sr_result.nearest_support
            resistance_level = sr_result.nearest_resistance
            near_support = sr_result.support_distance_pct < 3.0 and sr_result.support_distance_pct > 0
            near_resistance = sr_result.resistance_distance_pct < 3.0 and sr_result.resistance_distance_pct > 0
            
            # 斐波那契支撑检查
            for key, price in sr_result.fib_supports.items():
                if price > 0 and abs(current_price - price) / current_price < 0.03:
                    near_fib_support = True
                    break
            
            # 均线支撑检查
            for period, price in sr_result.ma_supports.items():
                if price > 0 and abs(current_price - price) / current_price < 0.03:
                    near_ma_support = True
                    break
        
        # ===== 趋势判断 =====
        trend = self._determine_trend(close)
        
        # ===== 综合评分 =====
        score = 50.0
        
        # MACD评分
        if macd_bullish:
            score += 10
        if hist_trend == 'rising':
            score += 10
        elif hist_trend == 'falling':
            score -= 10
        
        # 周线MACD评分
        if weekly_signal:
            score += (weekly_signal.signal_strength - 50) * 0.3
            if weekly_signal.is_green_shortening:
                score += 15
            if weekly_signal.has_golden_cross_expectation:
                score += 10
        
        # 支撑位评分
        if near_support:
            score += 10
        if near_fib_support:
            score += 5
        if near_ma_support:
            score += 5
        if sr_result and sr_result.support_quality == 'strong':
            score += 10
        elif sr_result and sr_result.support_quality == 'moderate':
            score += 5
        
        # 趋势评分
        if trend == 'uptrend':
            score += 10
        elif trend == 'downtrend':
            score -= 10
        
        score = max(0, min(100, score))
        
        # ===== 生成评语 =====
        summary = self._generate_summary(
            macd_bullish, macd_cross, hist_trend, weekly_signal,
            sr_result, near_support, near_resistance,
            near_fib_support, near_ma_support,
            trend, current_price, support_level, resistance_level
        )
        
        return TechAnalysisResult(
            symbol=symbol,
            name=name,
            macd_bullish=macd_bullish,
            macd_histogram_trend=hist_trend,
            weekly_macd=weekly_signal,
            support_resistance=sr_result,
            support_level=support_level,
            resistance_level=resistance_level,
            current_price=current_price,
            near_support=near_support,
            near_resistance=near_resistance,
            near_fib_support=near_fib_support,
            near_ma_support=near_ma_support,
            trend=trend,
            summary=summary,
            score=round(score, 1),
        )
    
    def _calculate_macd(self, close: np.ndarray, 
                         fast: int = None, slow: int = None, 
                         signal: int = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算MACD指标 (日线)"""
        fast = fast or self.config['macd_fast']
        slow = slow or self.config['macd_slow']
        signal = signal or self.config['macd_signal']
        
        def ema(data: np.ndarray, period: int) -> np.ndarray:
            result = np.zeros_like(data)
            multiplier = 2.0 / (period + 1)
            result[:period] = np.mean(data[:period])
            for i in range(period, len(data)):
                result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
            return result
        
        ema_fast = ema(close, fast)
        ema_slow = ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = ema(macd_line, signal)
        histogram = 2 * (macd_line - signal_line)
        
        return macd_line, signal_line, histogram
    
    def _check_macd_cross(self, macd_line: np.ndarray, 
                          signal_line: np.ndarray) -> str:
        """检查MACD交叉状态"""
        if len(macd_line) < 2:
            return 'none'
        
        if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
            return 'golden_cross'
        elif macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
            return 'death_cross'
        elif macd_line[-1] > signal_line[-1]:
            return 'bullish'
        else:
            return 'bearish'
    
    def _determine_trend(self, close: np.ndarray) -> str:
        """判断趋势方向"""
        if len(close) < 20:
            return 'sideways'
        
        ma20 = np.mean(close[-20:])
        ma60 = np.mean(close[-60:]) if len(close) >= 60 else np.mean(close)
        current = close[-1]
        
        if current > ma20 > ma60:
            return 'uptrend'
        elif current < ma20 < ma60:
            return 'downtrend'
        else:
            return 'sideways'
    
    def _generate_summary(self, macd_bullish: bool, macd_cross: str,
                           hist_trend: str, weekly_signal: Optional[WeeklyMACDSignal],
                           sr_result: Optional[SupportResistanceResult],
                           near_support: bool, near_resistance: bool,
                           near_fib_support: bool, near_ma_support: bool,
                           trend: str, price: float, 
                           support: float, resistance: float) -> str:
        """生成技术分析综合评语"""
        parts = []
        
        # 日线MACD评语
        if macd_cross == 'golden_cross':
            parts.append("✅ 日线MACD金叉")
        elif macd_cross == 'death_cross':
            parts.append("❌ 日线MACD死叉")
        elif macd_bullish:
            parts.append("📈 日线MACD多头")
        else:
            parts.append("📉 日线MACD空头")
        
        if hist_trend == 'rising':
            parts.append("(动量↑)")
        elif hist_trend == 'falling':
            parts.append("(动量↓)")
        
        # 周线MACD评语
        if weekly_signal:
            if weekly_signal.is_green_shortening:
                parts.append(f"🔥 周线绿柱缩短{weekly_signal.consecutive_green_shorten}周")
            if weekly_signal.is_red_lengthening:
                parts.append(f"📊 周线红柱拉长{weekly_signal.consecutive_red_lengthen}周")
            if weekly_signal.has_golden_cross_expectation:
                parts.append("🌟 周线金叉预期")
            if weekly_signal.cross_status == 'golden_cross':
                parts.append("✅ 周线MACD金叉")
            parts.append(f"周线信号:{weekly_signal.signal_type}({weekly_signal.signal_strength:.0f})")
        
        # 支撑压力
        if sr_result:
            # 斐波那契
            fib_0382 = sr_result.fib_supports.get('0.382', 0)
            fib_05 = sr_result.fib_supports.get('0.5', 0)
            fib_0618 = sr_result.fib_supports.get('0.618', 0)
            if fib_0382 or fib_05 or fib_0618:
                parts.append(f"斐波那契支撑: 0.382={fib_0382:.2f} 0.5={fib_05:.2f} 0.618={fib_0618:.2f}")
            
            # 均线
            ma_20 = sr_result.ma_supports.get(20, 0)
            ma_60 = sr_result.ma_supports.get(60, 0)
            if ma_20 or ma_60:
                parts.append(f"均线支撑: MA20={ma_20:.2f} MA60={ma_60:.2f}")
            
            # 共振
            if sr_result.confluence_supports:
                best = sr_result.best_support
                if best and best.get('price', 0) > 0:
                    parts.append(f"💎 支撑共振:{best['price']:.2f}({best.get('count',0)}方法)")
            
            # 成交量确认
            if sr_result.volume_confirm_support:
                parts.append("📊 缩量回踩支撑")
            if sr_result.volume_confirm_resistance:
                parts.append("📊 放量突破压力")
        
        if near_support:
            parts.append(f"💪 接近支撑位{support:.2f}")
        if near_resistance:
            parts.append(f"⚠️ 接近压力位{resistance:.2f}")
        if near_fib_support:
            parts.append("📐 斐波那契支撑位附近")
        if near_ma_support:
            parts.append("📈 均线支撑位附近")
        
        # 趋势
        trend_msgs = {
            'uptrend': "📊 趋势向上",
            'downtrend': "📊 趋势向下",
            'sideways': "📊 震荡整理",
        }
        parts.append(trend_msgs.get(trend, ""))
        
        return " | ".join(p for p in parts if p)
    
    def batch_analyze(self, stocks_data: Dict[str, pd.DataFrame]) -> List[TechAnalysisResult]:
        """批量分析多个股票/板块"""
        results = []
        for key, df in stocks_data.items():
            result = self.analyze(df, name=key)
            if result:
                results.append(result)
        return results
    
    def analyze_weekly_macd_batch(self, stocks_data: Dict[str, pd.DataFrame]) -> List[WeeklyMACDSignal]:
        """批量分析周线MACD"""
        results = []
        for key, df in stocks_data.items():
            signal = self.weekly_macd.analyze(df, name=key)
            if signal:
                results.append(signal)
        return results
