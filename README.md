# ASH - AI股票板块筛选器 (AI Stock Hedge Finder)

## 项目简介
ASH 是一个AI驱动的跨市场股票板块筛选工具，用于发现**美股涨得多但A股对应板块/个股涨得少甚至下跌**的跨市场套利/轮动机会。

## 功能特性
- 📊 数据获取：对接新浪财经、同花顺等数据源，获取板块与个股数据
- 🔍 跨市场筛选：找出美股涨幅大而A股对应板块滞涨的板块
- 📈 技术分析：MACD、波浪理论、支撑位/压力位分析
- 🎯 二次筛选个股：在板块基础上进一步筛选优质个股

## 环境配置

### 使用 conda/mamba 创建环境

```bash
# 使用 mamba（推荐，更快）
mamba env create -f environment.yml

# 或使用 conda
conda env create -f environment.yml

# 激活环境
conda activate ash
```

### 手动创建环境
```bash
conda create -n ash python=3.10
conda activate ash
pip install -r requirements.txt
```

### 使用 Docker
```bash
# 构建镜像
docker build -t ash:latest .

# 运行分析，输出结果会保存到宿主机 ./output
docker run --rm \
  -v "$PWD/output:/app/output" \
  -v "$PWD/data/cache:/app/data/cache" \
  ash:latest

# 传入参数，例如开启详细日志或调整周期
docker run --rm \
  -v "$PWD/output:/app/output" \
  -v "$PWD/data/cache:/app/data/cache" \
  ash:latest --period 20 -v

# 也可以使用 compose
docker compose run --rm ash
```

## 项目结构
```
ash/
├── README.md                 # 项目说明
├── environment.yml           # conda 环境配置
├── requirements.txt          # pip 依赖
├── config.py                 # 全局配置
├── main.py                   # 主程序入口
├── data/
│   ├── __init__.py
│   ├── fetcher.py            # 数据获取模块
│   ├── sector_mapping.py     # 中美板块映射关系
│   └── sector_mapping_data.py # 板块映射数据
├── analysis/
│   ├── __init__.py
│   ├── cross_market.py       # 跨市场筛选逻辑
│   ├── technical.py          # 技术分析（MACD, 波浪理论, 支撑压力）
│   └── stock_filter.py       # 个股筛选
├── utils/
│   ├── __init__.py
│   └── helpers.py            # 辅助函数
└── output/                   # 输出结果目录
```

## 使用方法

### 基本使用
```bash
# 运行全流程分析
python main.py

# 仅获取数据
python main.py --fetch-only

# 仅分析已有数据
python main.py --analyze-only

# 指定输出目录
python main.py --output ./my_results
```

### 作为模块导入
```python
from ash.data.fetcher import DataFetcher
from ash.analysis.cross_market import CrossMarketAnalyzer
from ash.analysis.technical import TechnicalAnalyzer

# 获取数据
fetcher = DataFetcher()
us_data = fetcher.fetch_us_sectors()
cn_data = fetcher.fetch_cn_sectors()

# 跨市场分析
analyzer = CrossMarketAnalyzer()
results = analyzer.find_opportunities(us_data, cn_data)

# 技术分析
tech = TechnicalAnalyzer()
for sector in results:
    tech.analyze(sector)
```

## 数据说明
- 美股板块数据来源：新浪财经美股板块
- A股板块数据来源：新浪财经/同花顺板块
- 个股数据来源：新浪财经个股行情
- 板块映射：人工维护的中美对标板块关系

## 注意事项
⚠️ **风险提示**：本工具仅供研究和参考，不构成任何投资建议。历史数据不代表未来表现，投资需谨慎。
⚠️ 用户需要自行承担使用本工具进行投资决策的风险。
