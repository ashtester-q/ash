"""
数据获取模块 - 多数据源交叉验证
A股: AKShare(同花顺) + 东方财富
美股: yfinance + 新浪
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import time
import re

import pandas as pd
import numpy as np
import requests

from config import DATA_DIR, FILTER_CONFIG, HEADERS
from data.sector_mapping_data import SECTOR_MAPPING
from utils.helpers import StockDataCache

logger = logging.getLogger(__name__)


# ==================== 多源数据交叉验证 ====================

class DataSourceValidator:
    """
    多数据源交叉验证器
    
    对同一数据从多个源获取，计算置信度评分
    """
    
    def __init__(self, config: dict = None):
        self.config = config or FILTER_CONFIG
    
    def validate_price(self, sources_data: List[Dict[str, Any]]) -> Dict:
        """
        交叉验证价格数据
        
        Args:
            sources_data: 各数据源返回的相同指标字典列表
                每个元素: {'source': 'yfinance', 'price': 100.0, 'change_pct': 2.5}
                
        Returns:
            {
                'final_price': 最终价格,
                'final_change': 最终涨跌幅,
                'confidence': 置信度分数,
                'sources_used': 使用的数据源数量,
                'source_details': 各源详细数据,
                'discrepancies': 数据差异说明
            }
        """
        if not sources_data:
            return {
                'final_price': None,
                'final_change': None,
                'confidence': 0.0,
                'sources_used': 0,
                'source_details': [],
                'discrepancies': '无数据源'
            }
        
        prices = [s.get('price') for s in sources_data if s.get('price') is not None]
        changes = [s.get('change_pct') for s in sources_data if s.get('change_pct') is not None]
        
        if not prices:
            return {
                'final_price': None,
                'final_change': None,
                'confidence': 0.0,
                'sources_used': len(sources_data),
                'source_details': sources_data,
                'discrepancies': '所有数据源均无价格数据'
            }
        
        # 计算加权平均
        weights = {
            'yfinance': self.config.get('confidence_weight_yfinance', 0.4),
            'sina': self.config.get('confidence_weight_sina', 0.3),
            'eastmoney': self.config.get('confidence_weight_eastmoney', 0.3),
        }
        
        total_weight = 0
        weighted_price = 0
        weighted_change = 0
        
        source_details = []
        for s in sources_data:
            src = s.get('source', 'unknown')
            w = weights.get(src, 0.2)
            
            if s.get('price') is not None:
                weighted_price += s['price'] * w
                total_weight += w
            
            if s.get('change_pct') is not None:
                weighted_change += s['change_pct'] * w
            
            source_details.append({
                'source': src,
                'price': s.get('price'),
                'change_pct': s.get('change_pct'),
                'weight': w,
                'available': s.get('price') is not None,
            })
        
        if total_weight == 0:
            return {
                'final_price': None,
                'final_change': None,
                'confidence': 0.0,
                'sources_used': len(sources_data),
                'source_details': source_details,
                'discrepancies': '权重总和为0'
            }
        
        final_price = weighted_price / total_weight if total_weight > 0 else prices[0]
        final_change = weighted_change / total_weight if total_weight > 0 else (changes[0] if changes else 0)
        
        # 计算置信度
        # 1. 数据源数量评分
        source_count_score = min(len([s for s in sources_data if s.get('price') is not None]) / 3.0, 1.0)
        
        # 2. 数据一致性评分
        if len(prices) >= 2:
            price_std = np.std(prices)
            price_mean = np.mean(prices)
            cv = price_std / price_mean if price_mean != 0 else 0  # 变异系数
            consistency_score = max(0, 1.0 - cv / self.config.get('cross_validate_tolerance', 0.05))
        else:
            consistency_score = 0.5  # 单个数据源，折中
        
        # 3. 综合置信度
        confidence = source_count_score * 0.4 + consistency_score * 0.6
        confidence = max(0, min(1.0, confidence))
        
        # 差异说明
        discrepancies = []
        if len(prices) >= 2:
            max_diff = max(prices) - min(prices)
            if max_diff / max(abs(price) for price in prices) > 0.02:
                discrepancies.append(f"数据源间最大差异 {max_diff:.2f} ({max_diff/abs(price_mean) if price_mean != 0 else 0:.2%})")
        
        return {
            'final_price': round(final_price, 2),
            'final_change': round(final_change, 2),
            'confidence': round(confidence, 4),
            'sources_used': len([s for s in sources_data if s.get('price') is not None]),
            'source_details': source_details,
            'discrepancies': '; '.join(discrepancies) if discrepancies else '数据一致性好',
        }
    
    def is_reliable(self, validation_result: Dict) -> bool:
        """判断数据是否可靠"""
        min_confidence = self.config.get('min_confidence_score', 0.6)
        return validation_result.get('confidence', 0) >= min_confidence
    
    def get_best_value(self, validation_result: Dict, key: str = 'final_price'):
        """获取最佳值"""
        return validation_result.get(key)
    
    def validate_with_eastmoney(self, sources_data: List[Dict[str, Any]]) -> Dict:
        """将东方财富数据纳入统一价格交叉验证流程。"""
        return self.validate_price(sources_data)


# ==================== A股数据获取器（增强版） ====================

class AKShareFetcher:
    """基于AKShare的A股数据获取器"""
    
    def __init__(self):
        try:
            import akshare as ak
            self.ak = ak
            self.validator = DataSourceValidator()
            self.cache = StockDataCache()
            self.retry_max = int(FILTER_CONFIG.get('request_retry_max', 3))
            self.retry_delay = float(FILTER_CONFIG.get('request_retry_delay', 0.8))
            self.request_delay = float(FILTER_CONFIG.get('request_delay', 0.25))
            self.cache_ttl_hours = int(FILTER_CONFIG.get('sector_cache_ttl_hours', 1))
            logger.info("AKShare 加载成功")
        except ImportError:
            raise ImportError("请先安装 akshare: pip install akshare")
    
    def _sleep(self):
        """请求间隔，降低 AKShare/网页接口限流概率。"""
        if self.request_delay > 0:
            time.sleep(self.request_delay)
    
    def _with_retry(self, func, *args, **kwargs):
        """带指数退避的轻量重试包装。"""
        last_error = None
        for attempt in range(1, self.retry_max + 1):
            try:
                self._sleep()
                return func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= self.retry_max:
                    break
                time.sleep(self.retry_delay * attempt)
        raise last_error
    
    @staticmethod
    def _cache_key(prefix: str, *parts: Any) -> str:
        text = "_".join(str(part) for part in parts)
        safe_text = re.sub(r"[^0-9A-Za-z_\-]+", "_", text)
        return f"{prefix}_{safe_text}"
    
    def _get_cached_df(self, key: str) -> pd.DataFrame:
        cached = self.cache.get(key, max_age_hours=self.cache_ttl_hours)
        if not cached:
            return pd.DataFrame()
        try:
            return pd.DataFrame(cached)
        except Exception as exc:
            logger.debug(f"缓存反序列化失败 [{key}]: {exc}")
            return pd.DataFrame()
    
    def _set_cached_df(self, key: str, df: pd.DataFrame):
        if df.empty:
            return
        serializable = df.copy()
        for col in serializable.columns:
            if pd.api.types.is_datetime64_any_dtype(serializable[col]):
                serializable[col] = serializable[col].dt.strftime('%Y-%m-%d')
        self.cache.set(key, serializable.to_dict(orient='records'))
    
    def fetch_cn_sectors(self, period: int = 5) -> pd.DataFrame:
        """
        获取A股行业板块实时行情（同花顺）
        """
        logger.info("获取A股行业板块实时行情 (同花顺)")
        try:
            df = self._with_retry(self.ak.stock_board_industry_summary_ths)
            if df.empty:
                return pd.DataFrame()
            
            rename_map = {
                '板块': 'sector_name', '涨跌幅': 'change_pct',
                '上涨家数': 'up_count', '下跌家数': 'down_count',
                '领涨股': 'lead_stock', '均价': 'avg_price',
                '总成交量': 'total_volume', '总成交额': 'total_amount',
                '净流入': 'net_inflow',
                '领涨股-最新价': 'lead_price', '领涨股-涨跌幅': 'lead_change_pct',
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            
            if 'change_pct' in df.columns:
                df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')
            
            df['market'] = 'cn'
            df['period'] = period
            df['fetch_time'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            df['data_source'] = 'ths'  # 同花顺
            
            # 尝试从东方财富补充数据
            try:
                df_em = self._fetch_cn_sectors_eastmoney()
                if not df_em.empty:
                    # 合并两个数据源的信息
                    df = self._merge_cn_sector_sources(df, df_em)
                    df['data_source'] = 'ths+em'
            except Exception as e:
                logger.debug(f"东方财富数据获取失败(非致命): {e}")
            
            df = df.sort_values('change_pct', ascending=False).reset_index(drop=True)
            logger.info(f"获取到 {len(df)} 个A股行业板块")
            return df
        except Exception as e:
            logger.error(f"获取A股板块数据失败: {e}")
            return pd.DataFrame()
    
    def _fetch_cn_sectors_eastmoney(self) -> pd.DataFrame:
        """
        从东方财富获取行业板块数据（辅助验证）
        """
        try:
            df = self._with_retry(self.ak.stock_board_industry_name_em)
            if df.empty:
                return pd.DataFrame()
            
            rename_map = {
                '板块名称': 'sector_name', 
                '涨跌幅': 'change_pct',
                '上涨家数': 'up_count', 
                '下跌家数': 'down_count',
                '领涨股名称': 'lead_stock',
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            
            if 'change_pct' in df.columns:
                df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')
            
            df['source_em'] = True
            logger.info(f"东方财富数据: {len(df)} 个板块")
            return df
        except Exception as e:
            logger.warning(f"东方财富数据获取失败: {e}")
            return pd.DataFrame()
    
    def _merge_cn_sector_sources(self, df_ths: pd.DataFrame, df_em: pd.DataFrame) -> pd.DataFrame:
        """合并同花顺和东方财富的板块数据"""
        if df_em.empty:
            return df_ths
        
        result = df_ths.copy()
        
        # 对每个板块，尝试用东方财富数据验证
        for idx, row in result.iterrows():
            name = row.get('sector_name', '')
            if not name:
                continue
            
            # 在东方财富数据中找匹配
            match = df_em[df_em['sector_name'].str.contains(name, na=False)]
            if match.empty:
                continue
            
            em_row = match.iloc[0]
            em_change = em_row.get('change_pct')
            
            if em_change is not None and pd.notna(em_change):
                # 交叉验证
                validation = self.validator.validate_price([
                    {'source': 'ths', 'price': row.get('avg_price', 0), 'change_pct': row.get('change_pct', 0)},
                    {'source': 'eastmoney', 'price': 0, 'change_pct': em_change},
                ])
                result.at[idx, 'change_pct_validated'] = validation.get('final_change', row.get('change_pct'))
                result.at[idx, 'confidence'] = validation.get('confidence', 1.0)
                
                # 如果置信度低，标记
                if not self.validator.is_reliable(validation):
                    result.at[idx, 'data_warning'] = f"数据差异: 同花顺{row.get('change_pct',0):+.2f}% vs 东方财富{em_change:+.2f}%"
        
        return result
    
    def fetch_sector_stocks(self, sector_name: str) -> pd.DataFrame:
        """获取板块成分股（多源交叉验证）
        
        优先级：东方财富 > 新浪 > 同花顺概念
        """
        sources = []
        
        try:
            # 1. 首选：东方财富（数据最全）
            stocks_em = self._fetch_sector_stocks_em(sector_name)
            if not stocks_em.empty:
                sources.append(stocks_em)
            
            # 2. 备选：新浪行业
            stocks_sina = self._fetch_sector_stocks_sina(sector_name)
            if not stocks_sina.empty:
                sources.append(stocks_sina)
            
            # 3. 同花顺概念
            stocks_ths = self._fetch_sector_stocks_ths(sector_name)
            if not stocks_ths.empty:
                sources.append(stocks_ths)
            
            if len(sources) >= 2:
                # 多源验证：以数据最多的为准，标记置信度
                best = max(sources, key=lambda x: len(x))
                return self._merge_stock_sources(*sources)
            elif len(sources) == 1:
                return sources[0]
            else:
                logger.warning(f"所有数据源均无法获取板块 [{sector_name}] 成分股")
            
        except Exception as e:
            logger.error(f"获取成分股失败: {e}")
        
        return pd.DataFrame()
    
    # 同花顺→新浪行业分类映射表
    THS_TO_SINA_MAP = {
        '半导体': 'new_dzqj', '电子化学品': 'new_dzqj', '芯片': 'new_dzqj',
        '电子': 'new_dzxx', '计算机': 'new_dzxx', '软件': 'new_dzxx',
        '通信': 'new_dzxx', 'IT': 'new_dzxx', '互联网': 'new_dzxx',
        '电池': 'new_dqhy', '光伏': 'new_dqhy', '储能': 'new_dqhy',
        '电力': 'new_dlhy', '能源金属': 'new_nyhf', '新能源': 'new_nyhf',
        '风电': 'new_fdsb', '发电': 'new_fdsb',
        '汽车': 'new_qczz', '新能源车': 'new_qczz', '汽车零部件': 'new_qczz',
        '军工': 'new_fjzz', '航天': 'new_fjzz', '航空': 'new_fjzz',
        '医药': 'new_swzz', '生物': 'new_swzz', '医疗': 'new_ylqx', '制药': 'new_swzz',
        '银行': 'new_jrhy', '证券': 'new_jrhy', '保险': 'new_jrhy', '金融': 'new_jrhy',
        '房地产': 'new_fdc', '开发': 'new_kfq',
        '食品': 'new_sphy', '饮料': 'new_sphy', '白酒': 'new_ljhy', '酿酒': 'new_ljhy',
        '煤炭': 'new_mthy', '钢铁': 'new_gthy', '有色': 'new_ysjs', '金属': 'new_ysjs',
        '化工': 'new_hghy', '化学': 'new_hghy', '化纤': 'new_hqhy', '石化': 'new_syhy',
        '石油': 'new_syhy', '燃气': 'new_gsgq', '环保': 'new_hbhy',
        '机械': 'new_jxhy', '设备': 'new_jxhy', '工程': 'new_jxhy',
        '家电': 'new_jdhy', '家具': 'new_jjhy', '家居': 'new_jjhy',
        '服装': 'new_fzxl', '纺织': 'new_fzhy', '鞋': 'new_fzxl',
        '建材': 'new_jzjc', '建筑': 'new_jzjc', '水泥': 'new_snhy',
        '交运': 'new_jtys', '运输': 'new_jtys', '物流': 'new_jtys',
        '传媒': 'new_cmyl', '游戏': 'new_cmyl', '教育': 'new_cmyl',
        '农业': 'new_nlmy', '牧渔': 'new_nlmy', '农药': 'new_nyhf', '化肥': 'new_nyhf',
        '造纸': 'new_zzhy', '包装': 'new_ysbz', '印刷': 'new_ysbz',
        '商贸': 'new_sybh', '商业': 'new_sybh', '零售': 'new_sybh',
        '旅游': 'new_jdly', '酒店': 'new_jdly',
        '电器': 'new_dqhy', '仪器': 'new_yqyb', '仪表': 'new_yqyb',
        '自动化': 'new_yqyb', '通用设备': 'new_jxhy', '专用设备': 'new_jxhy',
    }

    def _fetch_sector_stocks_ths(self, sector_name: str) -> pd.DataFrame:
        """同花顺获取板块成分股（备用方案：使用新浪行业分类）"""
        try:
            # 尝试通过同花顺概念板块获取（部分可用）
            concepts = self._with_retry(self.ak.stock_board_concept_name_ths)
            concept_match = concepts[concepts['name'] == sector_name]
            if not concept_match.empty:
                logger.debug(f"同花顺概念板块 '{sector_name}' 无法直接获取成分股，转新浪")
            
            # 备用方案：新浪行业分类
            return self._fetch_sector_stocks_sina(sector_name)
        except:
            return self._fetch_sector_stocks_sina(sector_name)
    
    def _find_sina_label(self, sector_name: str) -> str:
        """根据同花顺板块名查找对应的新浪行业label"""
        # 1. 精确匹配
        if sector_name in self.THS_TO_SINA_MAP:
            return self.THS_TO_SINA_MAP[sector_name]
        # 2. 关键词匹配
        for keyword, label in self.THS_TO_SINA_MAP.items():
            if keyword in sector_name:
                return label
        return None
    
    def _fetch_sector_stocks_sina(self, sector_name: str) -> pd.DataFrame:
        """新浪财经获取板块成分股（备选数据源）"""
        try:
            label = self._find_sina_label(sector_name)
            if not label:
                logger.debug(f"未找到 '{sector_name}' 对应新浪行业分类")
                return pd.DataFrame()
            
            df = self._with_retry(self.ak.stock_sector_detail, sector=label)
            if df.empty:
                return pd.DataFrame()
            
            df = df.rename(columns={
                'code': 'stock_code', 'name': 'stock_name',
                'trade': 'current_price', 'changepercent': 'change_pct',
            })
            for col in ['current_price', 'change_pct']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'change_pct' in df.columns:
                df['change_pct'] = df['change_pct'] / 100  # 新浪是百分比数值，转小数
            df['data_source'] = 'sina'
            logger.info(f"新浪 '{sector_name}'({label}): 获取到 {len(df)} 只股票")
            return df
        except Exception as e:
            logger.warning(f"新浪获取成分股失败 '{sector_name}': {e}")
        return pd.DataFrame()
    
    def _fetch_sector_stocks_em(self, sector_name: str) -> pd.DataFrame:
        """东方财富获取板块成分股（首选数据源，但可能被阻断）"""
        try:
            stocks = self._with_retry(self.ak.stock_board_industry_cons_em, symbol=sector_name)
            if not stocks.empty:
                rename_map = {
                    '名称': 'stock_name', '代码': 'stock_code', 
                    '最新价': 'current_price', '涨跌幅': 'change_pct',
                    '涨速': 'change_speed', '换手率': 'turnover_rate',
                    '市盈率-动态': 'pe_ratio', '成交量': 'volume',
                    '成交额': 'amount', '流通市值': 'float_market_cap',
                    '总市值': 'total_market_cap',
                }
                stocks = stocks.rename(columns={k: v for k, v in rename_map.items() if k in stocks.columns})
                if 'change_pct' in stocks.columns:
                    stocks['change_pct'] = pd.to_numeric(stocks['change_pct'], errors='coerce')
                stocks['data_source'] = 'eastmoney'
                logger.info(f"东方财富 '{sector_name}': 获取到 {len(stocks)} 只股票")
                return stocks
        except Exception as e:
            logger.debug(f"东方财富成分股获取失败: {e}")
        return pd.DataFrame()
    
    def _merge_stock_sources(self, *sources: pd.DataFrame) -> pd.DataFrame:
        """合并多个数据源的个股数据"""
        valid_sources = [df for df in sources if df is not None and not df.empty]
        if not valid_sources:
            return pd.DataFrame()
        eastmoney_sources = [
            df for df in valid_sources
            if 'data_source' in df.columns and str(df['data_source'].iloc[0]) == 'eastmoney'
        ]
        best = eastmoney_sources[0] if eastmoney_sources else max(valid_sources, key=len)
        return best.drop_duplicates(subset=['stock_code']).reset_index(drop=True)
    
    def fetch_sector_history(self, sector_name: str, period_days: int = 120) -> pd.DataFrame:
        """
        获取A股行业板块历史K线，并使用1小时JSON缓存。

        Returns:
            DataFrame with [date, open, high, low, close, volume]
        """
        cache_key = self._cache_key("sector_history", sector_name, period_days)
        cached = self._get_cached_df(cache_key)
        if not cached.empty:
            if 'date' in cached.columns:
                cached['date'] = pd.to_datetime(cached['date'])
            return cached

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=period_days + 20)).strftime("%Y%m%d")

        fetch_attempts = [
            (self.ak.stock_board_industry_hist_em, {
                "symbol": sector_name,
                "period": "日k",
                "start_date": start,
                "end_date": end,
                "adjust": "",
            }),
            (self.ak.stock_board_industry_hist_em, {
                "symbol": sector_name,
                "period": "daily",
                "start_date": start,
                "end_date": end,
                "adjust": "",
            }),
        ]

        for func, kwargs in fetch_attempts:
            try:
                df = self._with_retry(func, **kwargs)
                if df is None or df.empty:
                    continue
                df = df.rename(columns={
                    '日期': 'date', '开盘': 'open', '最高': 'high',
                    '最低': 'low', '收盘': 'close', '成交量': 'volume',
                    '成交额': 'amount', '振幅': 'amplitude',
                    '涨跌幅': 'change_pct', '涨跌额': 'change',
                    '换手率': 'turnover',
                })
                if 'date' not in df.columns or 'close' not in df.columns:
                    continue
                df['date'] = pd.to_datetime(df['date'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                df = df.sort_values('date').tail(period_days).reset_index(drop=True)
                self._set_cached_df(cache_key, df)
                return df
            except Exception as exc:
                logger.debug(f"获取板块历史失败 [{sector_name}]: {exc}")

        logger.warning(f"获取A股板块历史行情失败 [{sector_name}]")
        return pd.DataFrame()
    
    def fetch_stock_history(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        """获取A股个股历史K线（多数据源：akshare→yfinance备用）"""
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        # 方案1：akshare（东方财富）
        try:
            df = self._with_retry(self.ak.stock_zh_a_hist, symbol=stock_code, period="daily",
                                  start_date=start, end_date=end, adjust="qfq")
            if not df.empty:
                df = df.rename(columns={
                    '日期': 'date', '开盘': 'open', '最高': 'high',
                    '最低': 'low', '收盘': 'close', '成交量': 'volume',
                    '成交额': 'amount', '振幅': 'amplitude',
                    '涨跌幅': 'change_pct', '涨跌额': 'change',
                    '换手率': 'turnover',
                })
                df['date'] = pd.to_datetime(df['date'])
                for c in ['open','high','low','close','volume']:
                    if c in df.columns: 
                        df[c] = pd.to_numeric(df[c], errors='coerce')
                return df.sort_values('date').reset_index(drop=True)
        except Exception as e:
            logger.warning(f"akshare获取历史行情失败 [{stock_code}]: {e}，尝试yfinance...")
        
        # 方案2：yfinance备用（A股代码加后缀 .SS / .SZ）
        try:
            import yfinance as yf
            yf_cache_dir = DATA_DIR / "cache" / "yfinance"
            yf_cache_dir.mkdir(parents=True, exist_ok=True)
            if hasattr(yf, "set_tz_cache_location"):
                yf.set_tz_cache_location(str(yf_cache_dir))
            # 判断后缀: 6开头→上海.SS, 其他→深圳.SZ
            suffix = ".SS" if stock_code.startswith("6") else ".SZ"
            yf_code = stock_code + suffix
            
            ticker = yf.Ticker(yf_code)
            df = ticker.history(period=f"{days}d")
            
            if not df.empty and len(df) >= 5:
                df = df.reset_index()
                df = df.rename(columns={
                    'Date': 'date', 'Date': 'date',
                    'Open': 'open', 'High': 'high',
                    'Low': 'low', 'Close': 'close',
                    'Volume': 'volume',
                })
                # 兼容不同列名格式
                if 'Datetime' in df.columns:
                    df = df.rename(columns={'Datetime': 'date'})
                if 'Stock Splits' in df.columns:
                    df = df.drop(columns=['Stock Splits', 'Dividends'], errors='ignore')
                
                df['date'] = pd.to_datetime(df['date'])
                for c in ['open','high','low','close','volume']:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors='coerce')
                
                logger.info(f"yfinance获取 [{yf_code}] 成功: {len(df)} 根K线")
                return df.sort_values('date').reset_index(drop=True)
            else:
                logger.warning(f"yfinance获取 [{yf_code}] 数据不足")
        except Exception as e:
            logger.error(f"yfinance获取历史行情失败 [{stock_code}]: {e}")
        
        return pd.DataFrame()
    
    def check_st_stock(self, stock_code: str) -> bool:
        """检查是否为ST股票"""
        try:
            df = self.ak.stock_zh_a_st_em()
            if not df.empty and '代码' in df.columns:
                return stock_code in df['代码'].values
        except:
            pass
        return False


# ==================== 美股数据获取器（增强版） ====================

class USFetcher:
    """基于yfinance + 新浪的美股数据获取器"""
    
    # 美股行业ETF映射
    SECTOR_ETFS = {
        "半导体": "SMH", "芯片": "SOXX", "科技": "XLK", 
        "软件": "IGV", "互联网": "FDN", "人工智能": "BOTZ",
        "新能源": "TAN", "电动车": "DRIV", "生物科技": "XBI",
        "医药": "XLV", "金融": "XLF", "能源": "XLE",
        "消费": "XLP", "可选消费": "XLY", "工业": "XLI",
        "材料": "XLB", "房地产": "XLRE", "通信": "XLC",
        "公用事业": "XLU", "国防": "ITA", "云计算": "SKYY",
        "航空": "JETS", "零售": "XRT", "银行": "KBE",
        "机器人": "ROBO", "区块链": "BLOK", "半导体(费城)": "SOX",
    }
    
    # 中美板块对照
    CN_MAPPING = {
        "半导体": ["半导体", "电子化学品"],
        "芯片": ["半导体", "电子化学品"],
        "科技": ["计算机应用", "软件开发", "计算机设备", "IT服务"],
        "软件": ["软件开发", "IT服务"], 
        "互联网": ["互联网电商", "传媒"],
        "人工智能": ["计算机应用", "自动化设备", "机器人"],
        "新能源": ["电池", "能源金属", "光伏设备", "风电设备"],
        "电动车": ["汽车整车", "汽车零部件", "电池", "汽车服务及其他"],
        "生物科技": ["生物制品", "医疗服务"],
        "医药": ["化学制药", "中药", "生物制品", "医疗器械", "医疗服务"],
        "金融": ["银行", "证券", "保险", "多元金融"],
        "能源": ["煤炭开采加工", "石油加工贸易", "油气开采"],
        "消费": ["食品加工制造", "饮料制造", "白酒", "食品制造"],
        "可选消费": ["家用轻工", "汽车整车", "服装家纺", "家用电器"],
        "工业": ["通用设备", "专用设备", "仪器仪表", "自动化设备"],
        "材料": ["化学原料", "化学制品", "化工合成材料", "钢铁"],
        "房地产": ["房地产开发", "房地产服务"],
        "通信": ["通信服务", "通信设备", "光学光电子"],
        "公用事业": ["电力", "燃气", "环保"],
        "国防": ["国防军工", "军工装备", "航海装备"],
        "云计算": ["计算机应用", "IT服务", "通信服务"],
        "航空": ["机场航运", "航空装备"],
        "零售": ["零售", "互联网电商"],
        "银行": ["银行"],
        "机器人": ["自动化设备", "机器人", "通用设备"],
        "区块链": ["计算机应用", "软件开发"],
    }
    
    def __init__(self):
        try:
            import yfinance as yf
            yf_cache_dir = DATA_DIR / "cache" / "yfinance"
            yf_cache_dir.mkdir(parents=True, exist_ok=True)
            if hasattr(yf, "set_tz_cache_location"):
                yf.set_tz_cache_location(str(yf_cache_dir))
            self.yf = yf
            self.validator = DataSourceValidator()
            self.session = requests.Session()
            self.session.headers.update(HEADERS)
            self.cache = StockDataCache()
            self.retry_max = int(FILTER_CONFIG.get('request_retry_max', 3))
            self.retry_delay = float(FILTER_CONFIG.get('request_retry_delay', 0.8))
            self.request_delay = float(FILTER_CONFIG.get('request_delay', 0.25))
            self.cache_ttl_hours = int(FILTER_CONFIG.get('sector_cache_ttl_hours', 1))
            self._load_runtime_mappings()
            logger.info("yfinance 加载成功")
        except ImportError:
            raise ImportError("请先安装 yfinance: pip install yfinance")
    
    def _load_runtime_mappings(self):
        """从可编辑映射表补齐运行时 ETF 和 A股板块映射。"""
        for us_name, mapping in SECTOR_MAPPING.items():
            etf_code = mapping.get("us_etf_code")
            cn_name = mapping.get("cn_name")
            if etf_code:
                self.SECTOR_ETFS[us_name] = etf_code
            if cn_name:
                current = self.CN_MAPPING.setdefault(us_name, [])
                if cn_name not in current:
                    current.append(cn_name)
    
    def _sleep(self):
        if self.request_delay > 0:
            time.sleep(self.request_delay)
    
    def _with_retry(self, func, *args, **kwargs):
        """带指数退避的轻量重试包装。"""
        last_error = None
        for attempt in range(1, self.retry_max + 1):
            try:
                self._sleep()
                return func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= self.retry_max:
                    break
                time.sleep(self.retry_delay * attempt)
        raise last_error
    
    @staticmethod
    def _cache_key(prefix: str, *parts: Any) -> str:
        text = "_".join(str(part) for part in parts)
        safe_text = re.sub(r"[^0-9A-Za-z_\-]+", "_", text)
        return f"{prefix}_{safe_text}"
    
    def _get_cached_df(self, key: str) -> pd.DataFrame:
        cached = self.cache.get(key, max_age_hours=self.cache_ttl_hours)
        if not cached:
            return pd.DataFrame()
        try:
            df = pd.DataFrame(cached)
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            return df
        except Exception as exc:
            logger.debug(f"缓存反序列化失败 [{key}]: {exc}")
            return pd.DataFrame()
    
    def _set_cached_df(self, key: str, df: pd.DataFrame):
        if df.empty:
            return
        serializable = df.copy()
        for col in serializable.columns:
            if pd.api.types.is_datetime64_any_dtype(serializable[col]):
                serializable[col] = serializable[col].dt.strftime('%Y-%m-%d')
        self.cache.set(key, serializable.to_dict(orient='records'))
    
    def fetch_us_sectors(self, period_days: int = 5) -> pd.DataFrame:
        """
        获取美股行业ETF数据（多源交叉验证）
        
        Args:
            period_days: 5 或 20
            
        Returns:
            DataFrame 含多源验证信息
        """
        period_str = f"{period_days}d"
        logger.info(f"获取美股行业ETF数据 (周期={period_days}天)")
        
        results = []
        for sector_name, etf_code in self.SECTOR_ETFS.items():
            try:
                # === 数据源1: yfinance ===
                yf_data = self._fetch_yfinance(etf_code, period_str)
                
                # === 数据源2: 新浪美股 ===
                sina_data = self._fetch_sina_us(etf_code, period_days)
                
                # === 交叉验证 ===
                sources = []
                if yf_data:
                    sources.append(yf_data)
                if sina_data:
                    sources.append(sina_data)
                
                if sources:
                    validation = self.validator.validate_price(sources)
                    
                    result = {
                        'sector_name': sector_name,
                        'etf_code': etf_code,
                        'change_pct': validation.get('final_change', 0),
                        'current_price': validation.get('final_price', 0),
                        'confidence': validation.get('confidence', 0),
                        'sources_used': validation.get('sources_used', 0),
                        'market': 'us',
                        'period': period_days,
                    }
                    
                    # 如果使用多个数据源，标记交叉验证信息
                    if validation.get('sources_used', 0) > 1:
                        result['cross_validated'] = True
                        result['discrepancies'] = validation.get('discrepancies', '')
                    else:
                        result['cross_validated'] = False
                    
                    results.append(result)
                    
            except Exception as e:
                logger.debug(f"获取 {etf_code} 失败: {e}")
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values('change_pct', ascending=False).reset_index(drop=True)
            
            # 统计数据源覆盖
            validated_count = df['cross_validated'].sum() if 'cross_validated' in df.columns else 0
            logger.info(f"获取到 {len(df)} 个美股行业ETF (交叉验证: {validated_count}/{len(df)})")
        
        return df
    
    def _fetch_yfinance(self, etf_code: str, period_str: str) -> Optional[Dict]:
        """从yfinance获取数据"""
        try:
            ticker = self.yf.Ticker(etf_code)
            hist = self._with_retry(ticker.history, period=period_str)
            
            if not hist.empty and len(hist) >= 2:
                close_prices = hist['Close']
                change_pct = ((close_prices.iloc[-1] / close_prices.iloc[0]) - 1) * 100
                current_price = close_prices.iloc[-1]
                
                return {
                    'source': 'yfinance',
                    'price': float(current_price),
                    'change_pct': float(change_pct),
                }
        except Exception as e:
            logger.debug(f"yfinance获取 {etf_code} 失败: {e}")
        
        return None
    
    def _fetch_sina_us(self, etf_code: str, period_days: int) -> Optional[Dict]:
        """从新浪财经获取美股数据"""
        try:
            # 新浪美股实时行情
            url = f"https://hq.sinajs.cn/list=gb_{etf_code.lower()}"
            resp = self._with_retry(self.session.get, url, timeout=10)
            
            if resp.status_code == 200 and resp.text:
                # 解析新浪数据格式
                text = resp.text
                if etf_code.lower() in text:
                    parts = text.split('"')[1].split(',') if '"' in text else []
                    if len(parts) >= 3:
                        try:
                            current_price = float(parts[1]) if parts[1] else 0
                            # 新浪没有直接给周期涨跌幅，用开盘价近似
                            open_price = float(parts[2]) if parts[2] else current_price
                            change_pct = ((current_price / open_price) - 1) * 100 if open_price > 0 else 0
                            
                            return {
                                'source': 'sina',
                                'price': current_price,
                                'change_pct': change_pct,
                            }
                        except (ValueError, IndexError):
                            pass
        except Exception as e:
            logger.debug(f"新浪获取 {etf_code} 失败: {e}")
        
        return None
    
    def fetch_us_stock_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        获取美股个股历史数据
        
        Args:
            symbol: 股票代码 (如 'AAPL')
            period: 周期 ('1mo', '3mo', '6mo', '1y', '2y', '5y')
            
        Returns:
            DataFrame with [date, open, high, low, close, volume]
        """
        try:
            ticker = self.yf.Ticker(symbol)
            hist = self._with_retry(ticker.history, period=period)
            
            if not hist.empty:
                df = hist.reset_index()
                df = df.rename(columns={
                    'Date': 'date', 'Open': 'open', 'High': 'high',
                    'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                return df.sort_values('date').reset_index(drop=True)
        except Exception as e:
            logger.error(f"获取美股历史行情失败 [{symbol}]: {e}")
        
        return pd.DataFrame()
    
    def fetch_etf_history(self, etf_code: str, period_days: int = 120) -> pd.DataFrame:
        """
        获取美股行业ETF历史K线，并使用1小时JSON缓存。

        Returns:
            DataFrame with [date, open, high, low, close, volume]
        """
        cache_key = self._cache_key("etf_history", etf_code, period_days)
        cached = self._get_cached_df(cache_key)
        if not cached.empty:
            return cached

        try:
            ticker = self.yf.Ticker(etf_code)
            hist = self._with_retry(ticker.history, period=f"{period_days + 20}d")
            if hist is None or hist.empty:
                return pd.DataFrame()
            df = hist.reset_index().rename(columns={
                'Date': 'date',
                'Datetime': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
            })
            if 'date' not in df.columns or 'close' not in df.columns:
                return pd.DataFrame()
            df = df.drop(columns=['Dividends', 'Stock Splits', 'Capital Gains'], errors='ignore')
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.sort_values('date').tail(period_days).reset_index(drop=True)
            self._set_cached_df(cache_key, df)
            return df
        except Exception as exc:
            logger.warning(f"获取ETF历史行情失败 [{etf_code}]: {exc}")
            return pd.DataFrame()
    
    def get_cn_sector_mapping(self, us_sector_name: str) -> List[str]:
        """获取美股行业对应的A股板块名称列表"""
        return self.CN_MAPPING.get(us_sector_name, [])


DataFetcher = AKShareFetcher
