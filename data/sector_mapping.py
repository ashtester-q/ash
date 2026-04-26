"""
板块映射模块 - 管理中美板块对应关系
"""
import re
import logging
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher

import pandas as pd

from .sector_mapping_data import (
    SECTOR_MAPPING, get_mapped_sectors, 
    get_all_cn_sector_names, get_all_us_sector_names
)

logger = logging.getLogger(__name__)


class SectorMapper:
    """中美板块映射管理器"""
    
    def __init__(self):
        self.us_to_cn_map = SECTOR_MAPPING
        self._build_reverse_index()
    
    def _build_reverse_index(self):
        """建立反向索引：A股板块 -> 对应美股板块列表"""
        self.cn_to_us_map = {}
        for us_name, mapping in self.us_to_cn_map.items():
            cn_name = mapping["cn_name"]
            if cn_name not in self.cn_to_us_map:
                self.cn_to_us_map[cn_name] = []
            self.cn_to_us_map[cn_name].append(us_name)
    
    def map_us_to_cn(self, us_sector_name: str) -> Optional[Dict]:
        """
        将美股板块名映射到A股板块
        
        Args:
            us_sector_name: 美股板块名称
            
        Returns:
            dict with cn_name, related_codes, description or None
        """
        # 精确匹配
        mapping = get_mapped_sectors(us_sector_name)
        if mapping:
            return mapping
        
        # 模糊匹配
        best_match = None
        best_ratio = 0.6
        
        for us_name, mapping in self.us_to_cn_map.items():
            ratio = max(
                SequenceMatcher(None, us_sector_name.lower(), us_name.lower()).ratio(),
                SequenceMatcher(None, us_sector_name.lower(), mapping["description"].lower()).ratio()
            )
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = mapping
        
        if best_match:
            logger.debug(f"模糊匹配: {us_sector_name} -> {best_match['cn_name']} (相似度={best_ratio:.2f})")
            return best_match
        
        logger.warning(f"未找到美股板块 '{us_sector_name}' 的A股映射")
        return None
    
    def map_cn_to_us(self, cn_sector_name: str) -> List[str]:
        """将A股板块名映射到美股板块"""
        # 精确匹配
        if cn_sector_name in self.cn_to_us_map:
            return self.cn_to_us_map[cn_sector_name]
        
        # 模糊匹配
        results = []
        for cn_name, us_names in self.cn_to_us_map.items():
            if cn_name in cn_sector_name or cn_sector_name in cn_name:
                results.extend(us_names)
        
        return results
    
    def merge_sector_data(self, us_df: pd.DataFrame, cn_df: pd.DataFrame) -> pd.DataFrame:
        """
        合并中美板块数据，按映射关系对齐
        
        Args:
            us_df: 美股板块DataFrame
            cn_df: A股板块DataFrame
            
        Returns:
            合并后的DataFrame，每行对应一个映射关系
        """
        merged_records = []
        
        for _, us_row in us_df.iterrows():
            us_name = us_row.get('sector_name', '')
            us_change = us_row.get('change_pct', 0)
            
            mapping = self.map_us_to_cn(us_name)
            if not mapping:
                continue
            
            cn_name = mapping["cn_name"]
            
            # 在A股数据中查找对应板块
            cn_match = cn_df[cn_df['sector_name'].str.contains(cn_name, na=False)]
            
            if cn_match.empty:
                # 尝试模糊匹配
                for _, cn_row in cn_df.iterrows():
                    cn_row_name = cn_row.get('sector_name', '')
                    if (cn_name in cn_row_name or 
                        SequenceMatcher(None, cn_name, cn_row_name).ratio() > 0.5):
                        cn_match = pd.concat([cn_match, cn_row.to_frame().T])
                        break
            
            cn_change = cn_match['change_pct'].iloc[0] if not cn_match.empty else None
            
            merged_records.append({
                'us_sector': us_name,
                'us_change_pct': us_change,
                'cn_sector': cn_name,
                'cn_change_pct': cn_change,
                'gap': (us_change - cn_change) if cn_change is not None else None,
                'description': mapping['description'],
                'related_codes': ','.join(mapping['related_codes'][:5]),
                'keywords': ','.join(mapping.get('keywords', [])),
            })
        
        result = pd.DataFrame(merged_records)
        if not result.empty and 'gap' in result.columns:
            result = result.sort_values('gap', ascending=False).reset_index(drop=True)
        
        return result


class FuzzySectorMapper(SectorMapper):
    """增强版模糊匹配映射器"""
    
    def __init__(self, keyword_dict: Optional[Dict[str, List[str]]] = None):
        super().__init__()
        self.keyword_dict = keyword_dict or self._build_keyword_dict()
    
    def _build_keyword_dict(self) -> Dict[str, List[str]]:
        """从映射数据中提取关键词字典"""
        kw_dict = {}
        for us_name, mapping in self.us_to_cn_map.items():
            cn_name = mapping["cn_name"]
            keywords = [us_name.lower(), cn_name.lower()]
            keywords.extend(mapping.get("keywords", []))
            kw_dict[us_name] = keywords
        return kw_dict
    
    def smart_match(self, us_sector_name: str, us_keywords: List[str] = None) -> Optional[str]:
        """
        智能匹配：结合名称和关键词进行匹配
        """
        us_lower = us_sector_name.lower()
        
        # 关键词匹配
        if us_keywords:
            for kw in us_keywords:
                kw_lower = kw.lower()
                for us_name, mapping in self.us_to_cn_map.items():
                    cn_keywords = [mapping["cn_name"].lower()] + [k.lower() for k in mapping.get("keywords", [])]
                    if any(kw_lower in ck or ck in kw_lower for ck in cn_keywords):
                        logger.info(f"关键词匹配: {us_sector_name} -> {mapping['cn_name']} (关键词: {kw})")
                        return mapping["cn_name"]
        
        return super().map_us_to_cn(us_sector_name)
