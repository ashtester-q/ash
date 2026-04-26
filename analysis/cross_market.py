"""
跨市场筛选逻辑模块
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import numpy as np

from config import FILTER_CONFIG
from data.sector_mapping import SectorMapper

logger = logging.getLogger(__name__)


class CrossMarketAnalyzer:
    """
    跨市场板块对比分析器
    核心逻辑：找出美股涨得多但A股对应板块涨得少/下跌的机会
    """
    
    def __init__(self, sector_mapper: Optional[SectorMapper] = None):
        self.mapper = sector_mapper or SectorMapper()
        self.config = FILTER_CONFIG
    
    def find_opportunities(self, us_df_5d: pd.DataFrame, cn_df_5d: pd.DataFrame,
                           us_df_20d: Optional[pd.DataFrame] = None,
                           cn_df_20d: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        发现跨市场套利机会
        
        Args:
            us_df_5d: 美股5日涨幅数据
            cn_df_5d: A股5日涨幅数据
            us_df_20d: 美股20日涨幅数据(可选)
            cn_df_20d: A股20日涨幅数据(可选)
            
        Returns:
            DataFrame: 筛选出的机会列表
        """
        logger.info("开始跨市场机会筛选...")
        
        # Step 1: 合并5日数据
        merged_5d = self.mapper.merge_sector_data(us_df_5d, cn_df_5d)
        if merged_5d.empty:
            logger.warning("未找到任何中美板块映射关系")
            return pd.DataFrame()
        
        logger.info(f"共发现 {len(merged_5d)} 个中美映射板块")
        
        # Step 2: 应用筛选条件
        candidates = self._apply_filters(merged_5d)
        
        if candidates.empty:
            logger.info("未找到符合条件的跨市场机会")
            return pd.DataFrame()
        
        # Step 3: 如果提供了20日数据，补充20日分析
        if us_df_20d is not None and cn_df_20d is not None:
            merged_20d = self.mapper.merge_sector_data(us_df_20d, cn_df_20d)
            if not merged_20d.empty:
                candidates = self._merge_period_data(candidates, merged_20d)
        
        # Step 4: 评分排序
        candidates = self._score_and_rank(candidates)
        
        logger.info(f"筛选出 {len(candidates)} 个潜在机会")
        return candidates
    
    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """应用筛选条件"""
        if df.empty:
            return df
        
        result = df.copy()
        
        # 条件1: 美股涨幅大于阈值
        result = result[
            (result['us_change_pct'] >= self.config['us_min_gain_5d'])
        ]
        
        # 条件2: A股涨幅小于阈值（滞涨）
        result = result[
            (result['cn_change_pct'].isna()) | 
            (result['cn_change_pct'] <= self.config['cn_max_gain_5d'])
        ]
        
        # 条件3: 涨幅差异大于阈值
        result = result[
            result['gap'] >= self.config['min_gap_5d']
        ]
        
        return result.reset_index(drop=True)
    
    def _merge_period_data(self, candidates_5d: pd.DataFrame, 
                           merged_20d: pd.DataFrame) -> pd.DataFrame:
        """合并5日和20日数据"""
        result = candidates_5d.copy()
        
        # 添加20日数据列
        for _, row in merged_20d.iterrows():
            mask = result['us_sector'] == row['us_sector']
            if mask.any():
                idx = result[mask].index[0]
                result.loc[idx, 'us_change_20d'] = row['us_change_pct']
                result.loc[idx, 'cn_change_20d'] = row['cn_change_pct']
                result.loc[idx, 'gap_20d'] = row['gap']
        
        # 填充缺失值
        for col in ['us_change_20d', 'cn_change_20d', 'gap_20d']:
            if col not in result.columns:
                result[col] = None
        
        return result
    
    def _score_and_rank(self, df: pd.DataFrame) -> pd.DataFrame:
        """对结果进行评分和排序"""
        result = df.copy()
        
        # 计算综合评分
        scores = []
        for _, row in result.iterrows():
            score = 0.0
            
            # 5日涨幅差异越大越好
            score += min(row['gap'] / 10.0, 30.0)
            
            # 美股涨幅加分
            score += min(row['us_change_pct'] / 5.0, 20.0)
            
            # A股跌幅加分（跌得越多，补涨动力越强）
            if pd.notna(row['cn_change_pct']) and row['cn_change_pct'] < 0:
                score += min(abs(row['cn_change_pct']) / 2.0, 15.0)
            
            # 20日数据加分
            if 'gap_20d' in row and pd.notna(row['gap_20d']):
                score += min(row['gap_20d'] / 10.0, 20.0)
            
            # A股板块如果没数据，说明可能不在主流分类中，适当减分
            if pd.isna(row['cn_change_pct']):
                score *= 0.8
            
            scores.append(min(score, 100.0))
        
        result['score'] = scores
        result = result.sort_values('score', ascending=False).reset_index(drop=True)
        result['rank'] = range(1, len(result) + 1)
        
        return result
    
    def generate_report(self, opportunities: pd.DataFrame) -> str:
        """生成分析报告文本"""
        if opportunities.empty:
            return "暂未发现符合条件的跨市场机会。"
        
        lines = [
            "=" * 70,
            f"📊 AI跨市场板块筛选报告",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"筛选条件: 美股5日涨幅≥{self.config['us_min_gain_5d']}% "
            f"& A股涨幅≤{self.config['cn_max_gain_5d']}% "
            f"& 差异≥{self.config['min_gap_5d']}%",
            "=" * 70,
            "",
        ]
        
        for _, row in opportunities.iterrows():
            us_change = row['us_change_pct']
            cn_change = row.get('cn_change_pct', 'N/A')
            gap = row['gap']
            score = row['score']
            
            cn_change_str = f"{cn_change:+.2f}%" if pd.notna(cn_change) else "无数据"
            
            lines.extend([
                f"【机会 #{row['rank']}】评分: {score:.1f}",
                f"  📈 美股: {row['us_sector']} ({us_change:+.2f}%)",
                f"  📉 A股: {row['cn_sector']} ({cn_change_str})",
                f"  🔍 涨幅差: {gap:+.2f}%",
                f"  📝 描述: {row.get('description', '')}",
                f"  🏷️ 关键词: {row.get('keywords', '')}",
                "",
            ])
        
        lines.append("=" * 70)
        lines.append("⚠️ 风险提示：本报告仅供参考，不构成投资建议。")
        lines.append("=" * 70)
        
        return "\n".join(lines)
