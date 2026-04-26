"""
中美板块映射关系数据
维护美股板块与A股板块之间的对应关系

运行时会优先合并 data/sector_mapping.xlsx 中的可编辑映射；如果 Excel
不存在或读取失败，则使用本文件中的内置映射作为兜底。
"""
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 中美产业链对标板块映射表
# 格式: { "美股板块名称": { "cn_name": "A股板块名称", "related_codes": [...], "description": "..." } }
SECTOR_MAPPING: Dict[str, Dict] = {
    # ========== 科技 ==========
    "半导体": {
        "cn_name": "半导体及元件",
        "related_codes": ["sz300661", "sz300782", "sh603986", "sz002371", "sz300604"],
        "description": "芯片设计、制造、封测",
        "keywords": ["芯片", "半导体", "集成电路", "AI芯片"]
    },
    "人工智能": {
        "cn_name": "计算机应用",
        "related_codes": ["sz300418", "sz300624", "sh603019", "sz002230", "sz300679"],
        "description": "AI、大模型、智能应用",
        "keywords": ["人工智能", "AI", "大模型", "算力"]
    },
    "云计算": {
        "cn_name": "计算机应用",
        "related_codes": ["sz300442", "sh600588", "sh603039", "sz300383"],
        "description": "云服务、SaaS、数据中心",
        "keywords": ["云计算", "云服务", "SaaS", "数据中心"]
    },
    "软件开发": {
        "cn_name": "计算机应用",
        "related_codes": ["sh600536", "sz002230", "sz300454", "sh600588"],
        "description": "软件开发、应用软件",
        "keywords": ["软件", "开发", "应用软件"]
    },
    "互联网": {
        "cn_name": "传媒",
        "related_codes": ["sh600637", "sz300418", "sh603888", "sz002624"],
        "description": "互联网平台、内容",
        "keywords": ["互联网", "平台", "内容"]
    },
    "信息技术服务": {
        "cn_name": "计算机应用",
        "related_codes": ["sh603019", "sz300659", "sz300168"],
        "description": "IT服务、系统集成",
        "keywords": ["IT服务", "系统集成", "信息技术"]
    },
    "电子元器件": {
        "cn_name": "电子",
        "related_codes": ["sz002475", "sh603501", "sz300136", "sz002916"],
        "description": "电子元器件、面板、PCB",
        "keywords": ["电子", "元器件", "面板", "PCB"]
    },
    # ========== 新能源 ==========
    "新能源": {
        "cn_name": "电力设备",
        "related_codes": ["sh601012", "sz300750", "sz002129", "sh600438"],
        "description": "光伏、风电、储能",
        "keywords": ["新能源", "光伏", "风电", "储能", "新能源发电"]
    },
    "电动汽车": {
        "cn_name": "汽车整车",
        "related_codes": ["sz002594", "sh600104", "sh601633", "sz000625"],
        "description": "新能源汽车整车制造",
        "keywords": ["新能源汽车", "电动汽车", "电动车"]
    },
    "锂电池": {
        "cn_name": "电力设备",
        "related_codes": ["sz300750", "sz002074", "sh600884", "sz002709"],
        "description": "锂电池制造、材料",
        "keywords": ["锂电池", "锂电", "电池"]
    },
    "太阳能": {
        "cn_name": "电力设备",
        "related_codes": ["sh601012", "sh600438", "sz300274", "sh688599"],
        "description": "光伏产业链",
        "keywords": ["光伏", "太阳能", "逆变器", "硅片"]
    },
    # ========== 金融 ==========
    "银行": {
        "cn_name": "银行",
        "related_codes": ["sh601398", "sh601939", "sh600036", "sh601166"],
        "description": "商业银行",
        "keywords": ["银行", "商业银行"]
    },
    "保险": {
        "cn_name": "保险及其他",
        "related_codes": ["sh601318", "sh601628", "sh601601", "sh601336"],
        "description": "保险行业",
        "keywords": ["保险"]
    },
    "券商": {
        "cn_name": "证券",
        "related_codes": ["sh600030", "sh601211", "sz002736", "sh600837"],
        "description": "证券行业",
        "keywords": ["证券", "券商"]
    },
    # ========== 医药 ==========
    "生物科技": {
        "cn_name": "医疗器械",
        "related_codes": ["sh688981", "sz300760", "sz300003", "sh603259"],
        "description": "生物技术、创新药",
        "keywords": ["生物", "生物医药", "创新药"]
    },
    "医药": {
        "cn_name": "医药",
        "related_codes": ["sh600276", "sz300015", "sh600196", "sz000538"],
        "description": "制药、医药服务",
        "keywords": ["医药", "制药", "药品"]
    },
    "医疗器械": {
        "cn_name": "医疗器械",
        "related_codes": ["sz300760", "sz300003", "sh688016", "sz002223"],
        "description": "医疗设备、耗材",
        "keywords": ["医疗器械", "医疗设备", "诊断"]
    },
    # ========== 消费 ==========
    "消费零售": {
        "cn_name": "零售",
        "related_codes": ["sh600519", "sh000858", "sz002304", "sh600887"],
        "description": "消费品零售",
        "keywords": ["消费", "零售", "白酒", "食品饮料"]
    },
    "食品饮料": {
        "cn_name": "食品饮料",
        "related_codes": ["sh600519", "sh600887", "sz000858", "sh603288"],
        "description": "食品饮料行业",
        "keywords": ["食品", "饮料", "白酒", "乳制品"]
    },
    "电商": {
        "cn_name": "零售",
        "related_codes": ["sz002024", "sh600827", "sh601933", "sz300413"],
        "description": "电子商务",
        "keywords": ["电商", "电子商务", "互联网零售"]
    },
    # ========== 制造业 ==========
    "航空航天": {
        "cn_name": "国防军工",
        "related_codes": ["sh600760", "sh600893", "sz000768", "sh600862"],
        "description": "航空航天产业链",
        "keywords": ["航空", "航天", "军工"]
    },
    "国防军工": {
        "cn_name": "国防军工",
        "related_codes": ["sh600760", "sh600893", "sz000768", "sh600185"],
        "description": "国防军事工业",
        "keywords": ["军工", "国防", "装备"]
    },
    "机器人": {
        "cn_name": "自动化设备",
        "related_codes": ["sz300124", "sh601100", "sz300024", "sz002747"],
        "description": "工业机器人、自动化",
        "keywords": ["机器人", "自动化", "智能制造"]
    },
    # ========== 资源 ==========
    "石油天然气": {
        "cn_name": "油气",
        "related_codes": ["sh600028", "sh601857", "sh600256", "sh600688"],
        "description": "石油、天然气勘探开发",
        "keywords": ["石油", "天然气", "油气"]
    },
    "有色金属": {
        "cn_name": "有色金属",
        "related_codes": ["sh601600", "sh600362", "sz000630", "sh600547"],
        "description": "有色金属采掘冶炼",
        "keywords": ["有色金属", "铜", "铝", "黄金", "稀土"]
    },
    "钢铁": {
        "cn_name": "钢铁",
        "related_codes": ["sh600019", "sh600010", "sz000708", "sh600808"],
        "description": "钢铁冶炼加工",
        "keywords": ["钢铁", "钢材"]
    },
    "煤炭": {
        "cn_name": "煤炭",
        "related_codes": ["sh601088", "sh600188", "sh600546", "sz000983"],
        "description": "煤炭开采",
        "keywords": ["煤炭", "焦煤", "动力煤"]
    },
    # ========== 基建 ==========
    "基建": {
        "cn_name": "建筑装饰",
        "related_codes": ["sh601668", "sh601186", "sh601390", "sh600585"],
        "description": "基础设施建设",
        "keywords": ["基建", "建筑", "工程", "水泥"]
    },
    "房地产": {
        "cn_name": "房地产",
        "related_codes": ["sh600048", "sz000002", "sh600383", "sh600340"],
        "description": "房地产开发",
        "keywords": ["房地产", "地产", "开发"]
    },
    # ========== 运输 ==========
    "物流运输": {
        "cn_name": "物流",
        "related_codes": ["sh600233", "sz002120", "sh600029", "sh601111"],
        "description": "物流、快递、航运",
        "keywords": ["物流", "快递", "航运", "运输"]
    },
}

DEFAULT_US_ETFS: Dict[str, str] = {
    "半导体": "SMH",
    "人工智能": "BOTZ",
    "云计算": "SKYY",
    "软件开发": "IGV",
    "互联网": "FDN",
    "信息技术服务": "XLK",
    "电子元器件": "SOXX",
    "新能源": "TAN",
    "电动汽车": "DRIV",
    "锂电池": "LIT",
    "太阳能": "TAN",
    "银行": "KBE",
    "保险": "KIE",
    "券商": "IAI",
    "生物科技": "XBI",
    "医药": "XLV",
    "医疗器械": "IHI",
    "消费零售": "XRT",
    "食品饮料": "XLP",
    "电商": "IBUY",
    "航空航天": "ITA",
    "国防军工": "ITA",
    "机器人": "ROBO",
    "石油天然气": "XLE",
    "有色金属": "XME",
    "钢铁": "SLX",
    "煤炭": "KOL",
    "基建": "PAVE",
    "房地产": "XLRE",
    "物流运输": "IYT",
    "Lean Hogs": "COW",
    "瘦肉猪": "COW",
}


def _normalize_cell(value) -> str:
    """将 Excel 单元格值标准化为空字符串或去空格文本。"""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text in {"-", "nan", "None"} else text


def _extract_stock_code(value: str) -> str:
    """从 '牧原股份(sz002714)' 等文本中提取 sh/sz/bj 股票代码。"""
    match = re.search(r"\b((?:sh|sz|bj)\d{6})\b", value, flags=re.IGNORECASE)
    return match.group(1).lower() if match else value


def _with_default_etfs(mapping: Dict[str, Dict]) -> Dict[str, Dict]:
    """为内置映射补齐默认 ETF 代码。"""
    enriched = deepcopy(mapping)
    for us_name, item in enriched.items():
        item.setdefault("us_etf_code", DEFAULT_US_ETFS.get(us_name, ""))
        item.setdefault("cn_sector_code", "")
    return enriched


def load_mapping_from_excel(excel_path: Optional[Path] = None) -> Dict[str, Dict]:
    """
    从可编辑 Excel 读取并合并中美板块映射。

    Sheet 1 需包含列:
    US_Sector | US_ETF_Code | CN_Sector | CN_Sector_Code | Description
    """
    excel_path = excel_path or (Path(__file__).resolve().parent / "sector_mapping.xlsx")
    mapping = _with_default_etfs(SECTOR_MAPPING)

    if not excel_path.exists():
        return mapping

    try:
        df = pd.read_excel(excel_path, sheet_name="US-to-CN Sector Mapping")
    except Exception as exc:
        logger.warning("读取板块映射 Excel 失败，使用内置映射: %s", exc)
        return mapping

    required = {"US_Sector", "US_ETF_Code", "CN_Sector", "CN_Sector_Code", "Description"}
    missing = required - set(df.columns)
    if missing:
        logger.warning("板块映射 Excel 缺少列 %s，使用内置映射", sorted(missing))
        return mapping

    for _, row in df.iterrows():
        us_sector = _normalize_cell(row.get("US_Sector"))
        if not us_sector:
            continue

        etf_code = _normalize_cell(row.get("US_ETF_Code")) or DEFAULT_US_ETFS.get(us_sector, "")
        cn_sector = _normalize_cell(row.get("CN_Sector"))
        cn_code = _normalize_cell(row.get("CN_Sector_Code"))
        description = _normalize_cell(row.get("Description"))

        current = mapping.get(us_sector, {
            "cn_name": cn_sector,
            "related_codes": [],
            "description": description,
            "keywords": [us_sector, cn_sector] if cn_sector else [us_sector],
        })

        if cn_sector:
            current["cn_name"] = cn_sector
        if description and (cn_sector or not current.get("description")):
            current["description"] = description
        if etf_code:
            current["us_etf_code"] = etf_code
        if cn_code:
            parsed_code = _extract_stock_code(cn_code)
            related_codes = current.setdefault("related_codes", [])
            if parsed_code.lower().startswith(("sh", "sz", "bj")):
                if parsed_code not in related_codes:
                    related_codes.append(parsed_code)
            else:
                current["cn_sector_code"] = parsed_code

        keywords = set(current.get("keywords", []))
        keywords.update(x for x in [us_sector, cn_sector] if x)
        current["keywords"] = sorted(keywords)
        mapping[us_sector] = current

    return mapping


SECTOR_MAPPING = load_mapping_from_excel()


def get_mapped_sectors(us_sector_name: str) -> Optional[Dict]:
    """根据美股板块名称获取对应的A股板块信息"""
    for us_name, mapping in SECTOR_MAPPING.items():
        if us_name.lower() in us_sector_name.lower() or us_sector_name.lower() in us_name.lower():
            return mapping
    return None


def find_related_sectors(keyword: str) -> List[str]:
    """根据关键词查找相关美股板块"""
    results = []
    for us_name in SECTOR_MAPPING:
        if keyword.lower() in us_name.lower():
            results.append(us_name)
        elif keyword.lower() in SECTOR_MAPPING[us_name].get("description", "").lower():
            results.append(us_name)
    return results


def get_all_cn_sector_names() -> List[str]:
    """获取所有A股板块名称（去重）"""
    names = set()
    for mapping in SECTOR_MAPPING.values():
        names.add(mapping["cn_name"])
    return sorted(names)


def get_all_us_sector_names() -> List[str]:
    """获取所有美股板块名称"""
    return sorted(SECTOR_MAPPING.keys())
