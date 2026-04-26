"""
个股筛选模块 - 板块内二次筛选 + 多数据源验证 + 风险排除
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

import pandas as pd
import numpy as np

from config import FILTER_CONFIG
from analysis.technical import TechnicalAnalyzer, TechAnalysisResult, WeeklyMACDSignal

logger = logging.getLogger(__name__)


@dataclass
class StockScore:
    """个股综合评分结果"""
    stock_code: str
    stock_name: str
    sector_name: str
    score: float                # 综合评分 (0-100)
    price_trend_score: float    # 趋势评分
    tech_score: float           # 技术面评分 (含周线MACD)
    gap_score: float            # 补涨潜力评分
    weekly_macd_score: float    # 周线MACD评分
    support_score: float        # 支撑位评分
    risk_score: float           # 风险评分 (越高越安全)
    current_price: float
    change_pct: float
    volume_ratio: float         # 量比
    reason: str                 # 推荐理由
    warnings: List[str] = field(default_factory=list)   # 风险警告
    weekly_macd_signal: Optional[WeeklyMACDSignal] = None  # 周线MACD详情
    tech_detail: Optional[TechAnalysisResult] = None       # 技术分析详情
    
    def to_dict(self) -> Dict:
        d = {
            'stock_code': self.stock_code,
            'stock_name': self.stock_name,
            'sector_name': self.sector_name,
            '综合评分': round(self.score, 1),
            '趋势评分': round(self.price_trend_score, 1),
            '技术评分': round(self.tech_score, 1),
            '周线MACD评分': round(self.weekly_macd_score, 1),
            '支撑位评分': round(self.support_score, 1),
            '风险评分': round(self.risk_score, 1),
            '补涨潜力评分': round(self.gap_score, 1),
            '当前价': round(self.current_price, 2),
            '涨跌幅%': round(self.change_pct, 2),
            '推荐理由': self.reason,
            '风险警告': '; '.join(self.warnings) if self.warnings else '',
        }
        # 添加周线MACD信号
        if self.weekly_macd_signal:
            d['周线MACD信号'] = self.weekly_macd_signal.signal_type
            d['周线信号强度'] = round(self.weekly_macd_signal.signal_strength, 1)
            d['绿柱缩短'] = self.weekly_macd_signal.is_green_shortening
            d['金叉预期'] = self.weekly_macd_signal.has_golden_cross_expectation
            d['连续缩短周数'] = self.weekly_macd_signal.consecutive_green_shorten
            d['MACD_DIF'] = round(self.weekly_macd_signal.dif, 4)
            d['MACD_DEA'] = round(self.weekly_macd_signal.dea, 4)
            d['MACD_BAR'] = round(self.weekly_macd_signal.macd_bar, 4)
        return d


class StockFilter:
    """
    个股筛选器
    板块机会确定后，进一步筛选板块内最有潜力的个股
    """
    
    def __init__(self):
        self.config = FILTER_CONFIG
        self.tech_analyzer = TechnicalAnalyzer()
    
    def filter_stocks(self, sector_name: str, stocks_df: pd.DataFrame,
                      history_data: Dict[str, pd.DataFrame] = None) -> List[StockScore]:
        """
        筛选某个板块内最有潜力的个股
        
        Args:
            sector_name: 板块名称
            stocks_df: 板块内个股列表, 需包含 [stock_code, stock_name, change_pct, current_price]
            history_data: 个股历史数据字典 {code: df}
            
        Returns:
            评分排序后的个股列表
        """
        if stocks_df.empty:
            return []
        
        logger.info(f"筛选板块 [{sector_name}] 中的个股，共 {len(stocks_df)} 只")
        
        scores = []
        
        for _, stock in stocks_df.iterrows():
            code = str(stock.get('stock_code', ''))
            name = stock.get('stock_name', '')
            change = stock.get('change_pct', 0)
            price = stock.get('current_price', 0)
            
            if not code or not name:
                continue
            
            try:
                change = float(change) if change else 0
                price = float(price) if price else 0
            except (ValueError, TypeError):
                continue
            
            # ===== 步骤1: 风险检查 =====
            risk_score, warnings = self._check_risks(code, name, stock)
            
            # 如果有严重风险，直接跳过
            if risk_score < 20:
                logger.debug(f"跳过 {name}({code}): 高风险 ({'; '.join(warnings)})")
                continue
            
            # ===== 步骤2: 获取历史数据 =====
            hist_df = None
            if history_data and code in history_data:
                hist_df = history_data[code]
            
            # ===== 步骤3: 技术分析（含周线MACD + 支撑位）=====
            tech_result = None
            weekly_signal = None
            if hist_df is not None and not hist_df.empty:
                tech_result = self.tech_analyzer.analyze(hist_df, name, code)
                if tech_result:
                    weekly_signal = tech_result.weekly_macd
                    tech_score = self._score_technical(tech_result)
                else:
                    tech_score = 40.0
            else:
                tech_score = 40.0  # 无数据时给保守分
            
            # ===== 步骤4: 计算各项评分 =====
            trend_score = self._score_price_trend(change, price, hist_df)
            gap_score = self._score_gap_potential(change, tech_score)
            weekly_macd_score = self._score_weekly_macd(weekly_signal)
            support_score = self._score_support_level(tech_result)
            
            # ===== 步骤5: 综合评分 =====
            total_score = (
                trend_score * 0.20 +
                tech_score * 0.15 +
                weekly_macd_score * 0.30 +  # 周线MACD权重最高
                support_score * 0.15 +
                gap_score * 0.10 +
                risk_score * 0.10
            )
            
            # 生成推荐理由
            reason = self._generate_reason(change, tech_score, weekly_macd_score, 
                                            support_score, risk_score, weekly_signal)
            
            scores.append(StockScore(
                stock_code=code,
                stock_name=name,
                sector_name=sector_name,
                score=round(total_score, 1),
                price_trend_score=round(trend_score, 1),
                tech_score=round(tech_score, 1),
                gap_score=round(gap_score, 1),
                weekly_macd_score=round(weekly_macd_score, 1),
                support_score=round(support_score, 1),
                risk_score=round(risk_score, 1),
                current_price=price,
                change_pct=change,
                volume_ratio=0.0,
                reason=reason,
                warnings=warnings,
                weekly_macd_signal=weekly_signal,
                tech_detail=tech_result,
            ))
        
        # 排序并筛选
        scores.sort(key=lambda x: x.score, reverse=True)
        max_count = self.config.get('max_stocks_per_sector', 10)
        threshold = self.config.get('stock_score_threshold', 60)
        
        filtered = [s for s in scores if s.score >= threshold][:max_count]
        
        logger.info(f"板块 [{sector_name}] 筛选出 {len(filtered)}/{len(scores)} 只个股")
        return filtered
    
    def _check_risks(self, code: str, name: str, stock_row: pd.Series) -> Tuple[float, List[str]]:
        """
        风险检查
        
        Returns:
            (risk_score, warnings_list)
            risk_score: 0-100, 越高越安全
        """
        warnings = []
        risk_score = 100.0
        
        # 1. ST股票检查
        if self.config.get('exclude_st_stocks', True):
            if self._is_st_stock(code, name):
                warnings.append("ST股票")
                risk_score -= 60
        
        # 2. 价格异常检查
        price = stock_row.get('current_price', 0)
        try:
            price = float(price) if price else 0
        except:
            price = 0
        
        if price <= 0:
            warnings.append("价格数据异常")
            risk_score -= 30
        
        # 3. 涨跌幅异常检查
        change = stock_row.get('change_pct', 0)
        try:
            change = float(change) if change else 0
        except:
            change = 0
        
        max_decline = self.config.get('max_decline_ratio', -0.15) * 100
        if change < max_decline:
            warnings.append(f"近期跌幅过大({change:.1f}%)")
            risk_score -= 20
        
        if change > 20:
            warnings.append(f"短期涨幅过高({change:.1f}%)，追高风险")
            risk_score -= 15
        
        # 4. 检查新股
        # 通过代码判断 (新股代码特征)
        if self._is_new_stock(code):
            warnings.append("次新股，波动可能较大")
            risk_score -= 10
        
        risk_score = max(0, min(100, risk_score))
        return risk_score, warnings
    
    def _is_st_stock(self, code: str, name: str) -> bool:
        """判断是否为ST股票"""
        # 方法1: 名称包含ST
        if 'ST' in name.upper() or '*ST' in name.upper():
            return True
        # 方法2: 代码特征（科创板、北交所等不是ST）
        if code.startswith('688') or code.startswith('8'):
            return False
        return False
    
    def _is_new_stock(self, code: str) -> bool:
        """判断是否为次新股"""
        # 新股代码特征
        # 沪市: 60xxxx (但近期上市的)
        # 深市: 00xxxx, 30xxxx
        # 北交所: 8xxxxx
        # 简单判断：代码以特定开头
        if code.startswith('301') or code.startswith('688'):
            return True
        return False
    
    def _score_price_trend(self, change_pct: float, price: float, 
                            hist_df: Optional[pd.DataFrame] = None) -> float:
        """
        价格趋势评分
        
        偏好：
        - 微跌或微涨，有补涨空间
        - 如果历史数据可用，结合均线位置
        """
        score = 50.0
        
        if change_pct <= -10:
            score = 20
        elif change_pct <= -5:
            score = 40
        elif change_pct <= 0:
            score = 70  # 横盘/微跌
        elif change_pct <= 3:
            score = 80  # 微涨，最佳
        elif change_pct <= 8:
            score = 60
        elif change_pct <= 15:
            score = 40
        else:
            score = 20
        
        # 如果历史数据可用，检查价格与均线的关系
        if hist_df is not None and len(hist_df) >= 30:
            close = hist_df['close'].values
            ma20 = np.mean(close[-20:])
            ma60 = np.mean(close[-60:]) if len(close) >= 60 else np.mean(close)
            
            # 价格在均线附近 = 有支撑
            if abs(price - ma20) / price < 0.03:
                score += 10
            if abs(price - ma60) / price < 0.03:
                score += 5
            
            # 价格在均线下方 = 可能超跌
            if price < ma20 and price < ma60:
                score += 5  # 超跌反弹机会
        
        return max(0, min(100, score))
    
    def _score_technical(self, tech_result: TechAnalysisResult) -> float:
        """技术面评分"""
        score = 50.0
        
        # 日线MACD
        if tech_result.macd_bullish:
            score += 10
        if tech_result.macd_histogram_trend == 'rising':
            score += 10
        elif tech_result.macd_histogram_trend == 'falling':
            score -= 5
        
        # 周线MACD (主要权重)
        if tech_result.weekly_macd:
            wm = tech_result.weekly_macd
            if wm.is_green_shortening:
                score += 20
            if wm.has_golden_cross_expectation:
                score += 15
            if wm.cross_status == 'golden_cross':
                score += 15
            if wm.signal_type == 'bullish':
                score += 10
            elif wm.signal_type == 'bearish':
                score -= 15
        
        # 趋势
        if tech_result.trend == 'uptrend':
            score += 10
        elif tech_result.trend == 'downtrend':
            score -= 10
        
        return max(0, min(100, score))
    
    def _score_weekly_macd(self, weekly_signal: Optional[WeeklyMACDSignal]) -> float:
        """
        周线MACD专项评分 ★★★
        
        这是核心策略，权重最高
        """
        if weekly_signal is None:
            return 40.0  # 无数据时中性偏保守
        
        score = 50.0
        
        # 1. 绿柱缩短（核心信号）
        if weekly_signal.is_green_shortening:
            score += 25
            score += min(weekly_signal.consecutive_green_shorten * 5, 15)
        
        # 2. 加速度为正
        if weekly_signal.bar_acceleration > 0:
            score += 15
        
        # 3. 金叉预期
        if weekly_signal.has_golden_cross_expectation:
            score += 20
        
        # 4. 已金叉
        if weekly_signal.cross_status == 'golden_cross':
            score += 15
        elif weekly_signal.cross_status == 'death_cross':
            score -= 25
        
        # 5. 红柱拉长加速
        if weekly_signal.is_red_lengthening:
            score += 15
            score += min(weekly_signal.consecutive_red_lengthen * 3, 9)
        
        # 6. DIF接近DEA
        if weekly_signal.dif_dea_gap_change > 0:
            score += 10
        
        # 7. 信号强度加权
        score += (weekly_signal.signal_strength - 50) * 0.2
        
        return max(0, min(100, score))
    
    def _score_support_level(self, tech_result: Optional[TechAnalysisResult]) -> float:
        """支撑位评分"""
        if tech_result is None:
            return 50.0
        
        score = 50.0
        
        sr = tech_result.support_resistance
        if sr is None:
            return 50.0
        
        # 接近支撑位
        if tech_result.near_support:
            score += 15
        
        # 斐波那契支撑
        if tech_result.near_fib_support:
            score += 10
        
        # 均线支撑
        if tech_result.near_ma_support:
            score += 10
        
        # 支撑质量
        if sr.support_quality == 'strong':
            score += 15
        elif sr.support_quality == 'moderate':
            score += 8
        
        # 共振支撑
        if sr.confluence_supports:
            best = sr.best_support
            if best and best.get('count', 0) >= 3:
                score += 15
            elif best and best.get('count', 0) >= 2:
                score += 8
        
        # 成交量确认
        if sr.volume_confirm_support:
            score += 10
        
        return max(0, min(100, score))
    
    def _score_gap_potential(self, change_pct: float, tech_score: float) -> float:
        """补涨潜力评分"""
        score = 50.0
        
        if -3 <= change_pct <= 2:
            score += 20
        elif -5 <= change_pct < -3:
            score += 15
        elif 2 < change_pct <= 5:
            score += 10
        
        if tech_score > 70:
            score += 10
        
        return max(0, min(100, score))
    
    def _generate_reason(self, change_pct: float, tech_score: float,
                          weekly_macd_score: float, support_score: float,
                          risk_score: float, weekly_signal: Optional[WeeklyMACDSignal]) -> str:
        """生成推荐理由"""
        reasons = []
        
        # 周线MACD信号
        if weekly_signal:
            if weekly_signal.is_green_shortening:
                reasons.append(f"周线绿柱缩短{weekly_signal.consecutive_green_shorten}周")
            if weekly_signal.has_golden_cross_expectation:
                reasons.append("周线金叉预期")
            if weekly_signal.cross_status == 'golden_cross':
                reasons.append("周线MACD金叉")
            if weekly_signal.is_red_lengthening:
                reasons.append("周线红柱拉长")
        
        # 涨跌幅
        if change_pct <= 0:
            reasons.append(f"滞涨({change_pct:+.1f}%)")
        else:
            reasons.append(f"涨幅{change_pct:+.1f}%")
        
        # 技术面
        if tech_score >= 70:
            reasons.append("技术面偏多")
        elif tech_score >= 50:
            reasons.append("技术面中性")
        else:
            reasons.append("技术面偏弱")
        
        # 周线MACD
        if weekly_macd_score >= 70:
            reasons.append("周线MACD信号强")
        elif weekly_macd_score >= 50:
            reasons.append("周线MACD信号中性")
        
        # 支撑位
        if support_score >= 70:
            reasons.append("强支撑")
        
        # 综合评分
        total = (tech_score * 0.15 + weekly_macd_score * 0.30 + support_score * 0.15 + risk_score * 0.10)
        if total >= 70:
            reasons.append("综合评分优秀")
        elif total >= 60:
            reasons.append("综合评分良好")
        
        return "，".join(reasons) if reasons else "常规关注"
    
    def generate_stock_report(self, stock_scores: List[StockScore]) -> str:
        """生成个股推荐报告"""
        if not stock_scores:
            return "未选出符合条件的个股。"
        
        lines = [
            f"📋 个股推荐列表 ({len(stock_scores)} 只)",
            "-" * 80,
            f"{'#':3s} {'名称':10s} {'代码':8s} {'评分':5s} {'周MACD':8s} {'趋势':5s} {'技术':5s} {'支撑':5s} {'涨幅':7s} {'理由':20s}",
            "-" * 80,
        ]
        
        for i, stock in enumerate(stock_scores, 1):
            macd_signal = ""
            if stock.weekly_macd_signal:
                if stock.weekly_macd_signal.is_green_shortening:
                    macd_signal = "🔥绿缩"
                elif stock.weekly_macd_signal.is_red_lengthening:
                    macd_signal = "📊红拉"
                else:
                    macd_signal = stock.weekly_macd_signal.signal_type[:4]
            
            warnings_str = f" ⚠️{' '.join(stock.warnings[:2])}" if stock.warnings else ""
            
            lines.append(
                f"{i:3d} {stock.stock_name:10s} {stock.stock_code:8s} "
                f"{stock.score:5.1f} {macd_signal:8s} "
                f"{stock.price_trend_score:5.1f} {stock.tech_score:5.1f} "
                f"{stock.support_score:5.1f} {stock.change_pct:>+7.2f}% "
                f"{stock.reason[:20]:20s}{warnings_str}"
            )
        
        lines.append("-" * 80)
        return "\n".join(lines)
    
    def export_to_dataframe(self, stock_scores: List[StockScore]) -> pd.DataFrame:
        """导出为DataFrame"""
        if not stock_scores:
            return pd.DataFrame()
        records = [s.to_dict() for s in stock_scores]
        return pd.DataFrame(records)
