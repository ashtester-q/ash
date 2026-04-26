"""
辅助函数模块
"""
import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import LOG_CONFIG, OUTPUT_DIR, DATA_DIR


def setup_logging() -> logging.Logger:
    """
    配置日志系统
    
    Returns:
        root logger
    """
    log_file = LOG_CONFIG.get('file', OUTPUT_DIR / 'ash.log')
    log_level = getattr(logging, LOG_CONFIG.get('level', 'INFO'))
    log_format = LOG_CONFIG.get(
        'format', 
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建日志目录
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)


def save_results(data: Any, filename: str, subdir: str = "") -> str:
    """
    保存结果到文件
    
    Args:
        data: 要保存的数据 (DataFrame, dict, list, 或 str)
        filename: 文件名
        subdir: 子目录名
        
    Returns:
        文件完整路径
    """
    save_dir = OUTPUT_DIR / subdir if subdir else OUTPUT_DIR
    save_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = save_dir / filename
    
    if isinstance(data, pd.DataFrame):
        if filename.endswith('.csv'):
            data.to_csv(filepath, index=False, encoding='utf-8-sig')
        elif filename.endswith('.xlsx'):
            data.to_excel(filepath, index=False)
        elif filename.endswith('.json'):
            data.to_json(filepath, orient='records', force_ascii=False, indent=2)
        else:
            data.to_csv(filepath.with_suffix('.csv'), index=False, encoding='utf-8-sig')
    elif isinstance(data, (dict, list)):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    elif isinstance(data, str):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data)
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(str(data))
    
    logger = logging.getLogger(__name__)
    logger.info(f"结果已保存: {filepath}")
    
    return str(filepath)


def load_results(filename: str, subdir: str = "") -> Any:
    """
    从文件加载结果
    
    Args:
        filename: 文件名
        subdir: 子目录名
        
    Returns:
        加载的数据
    """
    load_dir = OUTPUT_DIR / subdir if subdir else OUTPUT_DIR
    filepath = load_dir / filename
    
    if not filepath.exists():
        logger = logging.getLogger(__name__)
        logger.warning(f"文件不存在: {filepath}")
        return None
    
    suffix = filepath.suffix.lower()
    
    if suffix == '.csv':
        return pd.read_csv(filepath)
    elif suffix == '.json':
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif suffix == '.xlsx':
        return pd.read_excel(filepath)
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()


def format_output(title: str, content: str, width: int = 70) -> str:
    """
    格式化输出
    
    Args:
        title: 标题
        content: 内容
        width: 宽度
        
    Returns:
        格式化后的字符串
    """
    lines = [
        "=" * width,
        f"  {title}",
        f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * width,
        "",
        content,
        "",
        "=" * width,
    ]
    return "\n".join(lines)


class StockDataCache:
    """
    股票数据缓存
    减少重复请求，提高效率
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (DATA_DIR / 'cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    def get(self, key: str, max_age_hours: int = 1) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            key: 缓存键
            max_age_hours: 最大缓存时间(小时)
            
        Returns:
            缓存数据，不存在或过期返回None
        """
        cache_file = self.cache_dir / f"{key}.json"
        
        if not cache_file.exists():
            return None
        
        # 检查过期时间
        file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age = (datetime.now() - file_time).total_seconds() / 3600
        
        if age > max_age_hours:
            self.logger.debug(f"缓存过期: {key} ({age:.1f}小时)")
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.debug(f"缓存命中: {key}")
            return data
        except Exception as e:
            self.logger.warning(f"读取缓存失败: {e}")
            return None
    
    def set(self, key: str, data: Any):
        """设置缓存"""
        cache_file = self.cache_dir / f"{key}.json"
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            self.logger.debug(f"缓存已保存: {key}")
        except Exception as e:
            self.logger.warning(f"保存缓存失败: {e}")
    
    def clear(self, key: Optional[str] = None):
        """清除缓存"""
        if key:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                cache_file.unlink()
        else:
            for f in self.cache_dir.glob("*.json"):
                f.unlink()
        self.logger.info("缓存已清除")
