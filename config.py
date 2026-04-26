"""
ASH 全局配置文件
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 数据缓存目录
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ==================== 数据源配置 ====================

# 新浪财经API
SINA_API = {
    "us_sector": "https://vip.stock.finance.sina.com.cn/q/go.php/vIndustryRank/kind/usstock/p/1/s/-{period}d/num/100.html",
    "cn_sector": "https://vip.stock.finance.sina.com.cn/q/go.php/vIndustryRank/kind/ss/p/1/s/-{period}d/num/100.html",
    "stock_detail": "https://hq.sinajs.cn/list={codes}",
    "sector_stocks": "https://vip.stock.finance.sina.com.cn/q/go.php/vIndustry_StockList/kind/{market}/id/{sector_id}/p/1/s/-{period}d/num/200.html",
}

# 同花顺数据接口
THS_API = {
    "sector_list": "http://q.10jqka.com.cn/thshy/client/",
    "sector_detail": "http://q.10jqka.com.cn/thshy/{sector_code}/",
}

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://vip.stock.finance.sina.com.cn/",
}

# ==================== 筛选参数配置 ====================

FILTER_CONFIG = {
    # 涨幅阈值
    "us_min_gain_5d": 3.0,       # 美股5日最小涨幅(%)
    "us_min_gain_20d": 5.0,      # 美股20日最小涨幅(%)
    "cn_max_gain_5d": 1.0,       # A股5日最大涨幅(%) - 低于此值视为滞涨
    "cn_max_gain_20d": 2.0,      # A股20日最大涨幅(%)
    
    # 差异阈值
    "min_gap_5d": 3.0,           # 5日最小涨幅差异(%)
    "min_gap_20d": 5.0,          # 20日最小涨幅差异(%)
    "div_us20": 5.0,             # 美股映射背离：美股20日最低涨幅(%)
    "div_cn20": 2.0,             # 美股映射背离：A股20日最高涨幅(%)
    "div_us5": 3.0,              # 美股映射背离：美股5日最低涨幅(%)
    "request_retry_max": 3,      # 数据源请求最大重试次数
    "request_retry_delay": 0.8,  # 数据源请求重试基础延迟(秒)
    "request_delay": 0.25,       # AKShare/yfinance请求间隔(秒)
    "sector_cache_ttl_hours": 1, # 板块历史数据缓存TTL(小时)
    
    # 个股筛选
    "stock_score_threshold": 60,  # 个股综合评分阈值
    "max_stocks_per_sector": 10,  # 每个板块最多选出的个股数
    
    # 技术分析参数 (日线)
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "support_resistance_lookback": 60,  # 支撑压力位回溯周期数
    
    # ========== 周线MACD套利参数 ==========
    "weekly_macd_fast": 12,       # 周线MACD快线周期
    "weekly_macd_slow": 26,       # 周线MACD慢线周期
    "weekly_macd_signal": 9,      # 周线MACD信号线周期
    "weekly_green_shorten_weeks": 2,    # 绿柱连续缩短周数阈值
    "weekly_red_lengthen_weeks": 2,     # 红柱连续拉长周数阈值
    "weekly_min_history_weeks": 52,     # 最少需要的历史周K线数
    
    # ========== 支撑位/压力位参数 ==========
    "fib_levels": [0.236, 0.382, 0.5, 0.618, 0.786],  # 斐波那契回撤位
    "pivot_lookback_weeks": 20,    # 波段高低点回溯周数
    "ma_support_periods": [20, 60],  # 均线支撑周期（周线）
    "volume_confirmation_days": 5,  # 成交量确认天数
    "support_confluence_tolerance": 0.02,  # 多重支撑共振容忍度(2%)
    
    # ========== 多数据源交叉验证 ==========
    "confidence_weight_yfinance": 0.4,    # yfinance置信度权重
    "confidence_weight_sina": 0.3,        # 新浪财经置信度权重
    "confidence_weight_eastmoney": 0.3,   # 东方财富置信度权重
    "min_confidence_score": 0.6,          # 最低置信度阈值
    "cross_validate_tolerance": 0.05,     # 多源数据差异容忍度(5%)
    
    # ========== 风险排除 ==========
    "exclude_st_stocks": True,      # 排除ST股票
    "exclude_new_stocks_days": 60,  # 排除上市不足60天的新股
    "max_decline_ratio": -0.15,     # 最大允许近期跌幅(-15%)
    "min_volume_ratio": 0.3,        # 最低成交量比率(相对20日均量)
}

# ==================== 板块映射配置 ====================

# 中美板块映射文件路径
SECTOR_MAPPING_FILE = DATA_DIR / "sector_mapping_data.py"

# ==================== 日志配置 ====================

LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": OUTPUT_DIR / "ash.log",
}
