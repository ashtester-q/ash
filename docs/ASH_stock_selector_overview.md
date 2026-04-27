# ASH 选股器专业介绍：跨市场板块轮动与周线 MACD 个股筛选系统

## 1. 项目定位

ASH 是一个面向投资研究场景的跨市场选股器。它不是单纯的行情展示工具，也不是自动交易系统，而是一个“先找板块，再找个股”的研究型筛选系统。

它关注的核心问题是：

> 当美股某个行业或 ETF 已经明显走强，而 A 股对应板块或相关个股尚未充分反应时，是否存在潜在的补涨、轮动或映射背离机会？

系统的选股逻辑分为两层：

1. **跨市场板块机会发现**
   - 对比美股行业 ETF 与 A 股对应行业板块的阶段表现。
   - 找出“美股涨得多、A 股涨得少或滞涨”的方向。
   - 输出可能存在轮动补涨机会的中美板块映射结果。

2. **A 股板块内个股技术筛选**
   - 在候选 A 股板块内部抓取成分股。
   - 对个股进行周线 MACD、支撑压力、趋势状态、风险过滤等分析。
   - 输出综合评分靠前、具备技术形态改善迹象的个股。

因此，ASH 的定位可以概括为：

> 用跨市场映射确定研究方向，用周线技术结构筛选 A 股候选个股，用结构化输出辅助人工复核。

## 2. 一句话说明系统如何选股

ASH 的主流程可以理解为：

> 先看美股哪些行业 ETF 近期强势，再通过映射表找到 A 股对应板块；如果 A 股对应板块涨幅落后，就进入板块内部，筛选周线 MACD 绿柱缩短、接近金叉、靠近支撑位且风险较低的个股。

这个逻辑背后的投资假设是：

- 全球产业链或主题行情可能存在跨市场传导。
- 美股行业 ETF 的强势可能领先于 A 股对应板块。
- A 股板块内部并非所有个股都有机会，需要二次筛选。
- 周线 MACD 比日线更适合捕捉中期趋势拐点和低位修复。
- 支撑位、风险过滤和补涨空间可以降低追高和误判概率。

## 3. 总体架构

ASH 当前由五层组成：

### 3.1 数据层

数据层负责从外部数据源获取板块、ETF、成分股和历史 K 线。

主要数据源包括：

- **同花顺**
  - 获取 A 股行业板块实时行情。
  - 用于板块涨跌幅、上涨家数、下跌家数、领涨股等字段。

- **东方财富**
  - 作为 A 股板块和成分股数据的补充来源。
  - 在部分接口可用时用于交叉验证或成分股获取。

- **新浪财经**
  - 用于部分 A 股行业成分股获取。
  - 用于部分美股行情 fallback。

- **yfinance**
  - 获取美股行业 ETF 行情和历史 K 线。
  - 在 A 股个股历史行情 fallback 中，也可通过 `.SS` / `.SZ` 后缀获取部分 A 股历史数据。

- **AKShare**
  - 作为 Python 侧统一数据接口封装。
  - 对接同花顺、东方财富、A 股历史行情等数据。

### 3.2 映射层

映射层负责维护“美股行业 / ETF”和“A 股板块 / 个股”的关系。

核心文件：

- `data/sector_mapping.xlsx`
- `data/sector_mapping_data.py`
- `data/sector_mapping.py`

映射表的作用是把类似下面的关系固化下来：

| 美股行业 | 美股 ETF | A 股板块 | A 股个股 |
|---|---|---|---|
| Semiconductors / 半导体 | SMH / SOXX | 半导体及元件 / 半导体 | 圣邦股份、士兰微、长电科技等 |
| Lean Hogs / 瘦肉猪 | COW | 猪肉 | 牧原股份、正邦科技等 |
| Energy / 能源 | XLE | 石油天然气 / 能源金属 | 对应能源链个股 |

映射层是整个系统的“桥梁”。如果映射质量高，系统能更准确地发现中美联动；如果映射粗糙，结果里就可能出现重复板块、错配板块或候选股重复。

### 3.3 分析层

分析层负责把原始行情转化为研究信号。

主要模块包括：

- `main.py`
  - 执行跨市场板块筛选。

- `analysis/technical.py`
  - 计算日线 MACD、周线 MACD、趋势、支撑压力、斐波那契、均线支撑等技术指标。

- `analysis/stock_filter.py`
  - 对板块内个股进行多维评分。

- `analysis/divergence.py`
  - 对美股 ETF 与 A 股映射板块做背离分析。

- `skills/weekly_macd_arbitrage.py`
  - 执行全市场或指定板块的周线 MACD 个股筛选。

### 3.4 配置层

配置层集中在 `config.py`。

它定义了：

- 输出目录。
- 日志配置。
- 数据源 URL。
- 请求重试次数与延迟。
- 中美背离阈值。
- 个股筛选阈值。
- MACD 参数。
- 支撑压力参数。
- 风险过滤参数。

典型参数包括：

| 参数 | 含义 |
|---|---|
| `us_min_gain_5d` | 美股 5 日最小涨幅阈值 |
| `cn_max_gain_5d` | A 股 5 日最大涨幅阈值，低于此值视为滞涨 |
| `min_gap_5d` | 中美 5 日最小涨幅差 |
| `stock_score_threshold` | 个股综合评分最低阈值 |
| `weekly_green_shorten_weeks` | 周线绿柱连续缩短周数阈值 |
| `support_confluence_tolerance` | 多重支撑共振容忍度 |
| `exclude_st_stocks` | 是否排除 ST 股票 |

### 3.5 输出层

输出层负责把分析结果保存为 CSV、TXT 和日志。

主要输出目录是：

```text
output/
```

当前典型输出包括：

- `cn_sectors_*.csv`
- `us_sectors_*.csv`
- `opportunities_*.csv`
- `weekly_macd_signals_*.csv`
- `stock_scores_all_*.csv`
- `arbitrage_report_*.txt`
- `divergence_*.csv`，仅在有背离机会时生成
- `ash.log`

## 4. 程序 1：`main.py` 跨市场板块筛选器

`main.py` 是第一层筛选器，重点回答：

> 哪些美股行业已经明显走强，而 A 股对应板块仍然滞涨？

### 4.1 程序目的

`main.py` 的目标不是直接选个股，而是筛选“值得进一步研究的板块方向”。

它完成三件事：

1. 获取 A 股行业板块涨跌幅。
2. 获取美股行业 ETF 涨跌幅。
3. 根据中美映射关系，找出涨幅差较大的板块机会。

### 4.2 运行命令

在 `ash` conda / mamba 环境中运行：

```bash
/home/freebird/.local/share/mamba/envs/ash/bin/python main.py
```

也可以指定参数：

```bash
/home/freebird/.local/share/mamba/envs/ash/bin/python main.py --period 5
/home/freebird/.local/share/mamba/envs/ash/bin/python main.py -v
```

当前代码里 `--period` 参数存在，但主流程中 A 股和美股主要仍按 5 日与 20 日逻辑执行。

### 4.3 输入

`main.py` 的输入来自三类数据。

#### A 股板块行情

来源：

- `AKShareFetcher.fetch_cn_sectors(period=5)`

主要字段：

| 字段 | 含义 |
|---|---|
| `sector_name` | A 股行业板块名称 |
| `change_pct` | 板块涨跌幅 |
| `up_count` | 板块内上涨家数 |
| `down_count` | 板块内下跌家数 |
| `lead_stock` | 领涨股 |
| `avg_price` | 板块均价 |
| `total_volume` | 总成交量 |
| `total_amount` | 总成交额 |
| `data_source` | 数据源标记 |

#### 美股行业 ETF 行情

来源：

- `USFetcher.fetch_us_sectors(period_days=5)`
- `USFetcher.fetch_us_sectors(period_days=20)`

主要字段：

| 字段 | 含义 |
|---|---|
| `sector_name` | 美股行业名称 |
| `etf_code` | 对应 ETF |
| `change_pct` | ETF 阶段涨跌幅 |
| `current_price` | 当前价格 |
| `confidence` | 多源验证置信度 |
| `sources_used` | 使用的数据源数量 |
| `cross_validated` | 是否完成交叉验证 |
| `discrepancies` | 多源差异说明 |

#### 中美板块映射

来源：

- `data/sector_mapping.xlsx`
- `data/sector_mapping_data.py`
- `USFetcher.get_cn_sector_mapping(us_sector_name)`

示例：

```text
美股半导体 ETF -> A 股半导体板块
美股能源 ETF -> A 股能源、石油、有色或能源金属板块
美股猪肉/农产品相关 ETF -> A 股猪肉或养殖链个股
```

### 4.4 处理逻辑

核心函数是：

```python
compare_markets(cn_df, us_df_5d, us_df_20d)
```

处理步骤：

1. 遍历美股 5 日 ETF 涨跌幅表。
2. 对每个美股行业，查找对应 A 股板块名称。
3. 在 A 股板块表中找到映射板块。
4. 计算 A 股映射板块平均涨幅。
5. 计算 5 日中美涨幅差：

```text
gap_5d = 美股行业 5 日涨幅 - A 股映射板块平均涨幅
```

6. 如果满足条件，则纳入机会列表：

```text
美股 5 日涨幅 > 2%
且
中美 5 日涨幅差 > 2%
```

7. 计算机会评分：

```text
score = 美股涨幅 * 0.6 + 涨幅差 * 0.4
```

8. 根据涨幅差划分机会等级：

| 条件 | 等级 |
|---|---|
| `gap_5d > 5` | 大机会 |
| `gap_5d > 3` | 机会 |
| 其他入选情况 | 关注 |

### 4.5 输出

`main.py` 会输出三类文件。

#### `cn_sectors_*.csv`

用途：

- 保存 A 股行业板块行情。
- 用于观察 A 股当前最强和最弱板块。

当前示例：

```text
output/cn_sectors_20260426_002100.csv
行数: 90
```

关键字段：

| 字段 | 解释 |
|---|---|
| `sector_name` | A 股板块 |
| `change_pct` | 板块涨跌幅 |
| `up_count` / `down_count` | 上涨 / 下跌家数 |
| `lead_stock` | 领涨股 |
| `data_source` | 数据源 |

#### `us_sectors_*.csv`

用途：

- 保存美股行业 ETF 阶段行情。
- 用于判断哪些美股行业已经走强。

当前示例：

```text
output/us_sectors_20260426_002100.csv
行数: 46
```

关键字段：

| 字段 | 解释 |
|---|---|
| `sector_name` | 美股行业 |
| `etf_code` | ETF 代码 |
| `change_pct` | 阶段涨跌幅 |
| `current_price` | ETF 当前价格 |
| `confidence` | 数据置信度 |
| `cross_validated` | 是否交叉验证 |

#### `opportunities_*.csv`

用途：

- 保存中美板块映射后的机会结果。
- 是 `main.py` 最核心的输出。

当前示例：

```text
output/opportunities_20260426_002100.csv
行数: 18
```

关键字段：

| 字段 | 解释 |
|---|---|
| `等级` | 机会等级 |
| `美股行业` | 走强的美股行业 |
| `ETF` | 美股行业 ETF |
| `美股涨幅` | 美股阶段涨幅 |
| `A股板块` | 映射到的 A 股板块 |
| `A股涨幅` | A 股板块平均涨幅 |
| `差距` | 美股涨幅 - A 股涨幅 |
| `评分` | 机会评分 |

### 4.6 如何解读 `main.py` 结果

`main.py` 的结果适合回答：

- 最近哪些美股行业最强？
- 哪些 A 股板块可能落后于美股映射方向？
- 哪些主题值得进入第二层个股筛选？

但它不适合直接回答：

- 哪只股票可以买？
- 什么价格买？
- 什么时候卖？

因为它只做板块层面判断，还没有对个股技术结构、风险状态、支撑压力进行完整筛选。

## 5. 程序 2：`skills.weekly_macd_arbitrage` 周线 MACD 个股筛选器

`skills.weekly_macd_arbitrage` 是第二层筛选器，重点回答：

> 在 A 股板块内部，哪些个股的中期技术结构正在改善？

### 5.1 程序目的

该程序的目标是从 A 股板块成分股中筛选出：

- 周线 MACD 绿柱缩短。
- 周线 MACD 有金叉预期。
- 已出现周线金叉或红柱拉长。
- 靠近支撑位。
- 多重支撑共振。
- 风险评分较高。
- 综合评分超过阈值。

它是 ASH 系统里更接近“选股”的部分。

### 5.2 运行命令

全市场扫描：

```bash
/home/freebird/.local/share/mamba/envs/ash/bin/python -m skills.weekly_macd_arbitrage
```

指定 A 股板块：

```bash
/home/freebird/.local/share/mamba/envs/ash/bin/python -m skills.weekly_macd_arbitrage --sector 半导体
```

指定美股行业并映射到 A 股：

```bash
/home/freebird/.local/share/mamba/envs/ash/bin/python -m skills.weekly_macd_arbitrage --us-sector 半导体
```

分析单只股票：

```bash
/home/freebird/.local/share/mamba/envs/ash/bin/python -m skills.weekly_macd_arbitrage --stock 600519
```

### 5.3 输入

该程序的输入包括：

#### A 股行业板块列表

来源：

- `AKShareFetcher.fetch_cn_sectors(period=5)`

全市场扫描时，当前代码默认取涨跌幅靠前的前 20 个行业板块进行详细分析。

#### 板块成分股

来源：

- `AKShareFetcher.fetch_sector_stocks(sector_name)`

优先级：

1. 东方财富行业成分股。
2. 新浪行业成分股。
3. 同花顺概念板块 fallback。

如果多个数据源可用，系统会选择更完整的数据源，并按股票代码去重。

#### 个股历史 K 线

来源：

- `AKShareFetcher.fetch_stock_history(stock_code, days=400)`

主要字段：

| 字段 | 含义 |
|---|---|
| `date` | 日期 |
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `volume` | 成交量 |

400 天日线数据会被转换为周线，用于周线 MACD 分析。

### 5.4 处理逻辑

核心类是：

```python
WeeklyMACDArbitrageSkill
```

主要流程：

1. 获取 A 股行业板块。
2. 取前 20 个板块进入详细扫描。
3. 对每个板块获取成分股。
4. 每个板块最多抓取前 20 只股票的历史行情。
5. 对每只股票执行技术分析。
6. 计算多维评分。
7. 每个板块保留最多 10 只评分达标个股。
8. 汇总全局 TOP 个股。
9. 保存周线信号、个股评分和文本报告。
10. 调用背离分析模块做美股映射背离检查。

### 5.5 周线 MACD 信号

核心数据结构是：

```python
WeeklyMACDSignal
```

它关注以下信号：

| 信号 | 含义 |
|---|---|
| `is_green_shortening` | MACD 绿柱连续缩短，表示空头动能减弱 |
| `has_golden_cross_expectation` | DIF 正接近 DEA，存在金叉预期 |
| `cross_status = golden_cross` | 周线 MACD 已金叉 |
| `is_red_lengthening` | 红柱拉长，表示多头动能增强 |
| `bar_acceleration` | MACD 柱变化加速度 |
| `dif_dea_gap` | DIF 与 DEA 的距离 |

为什么使用周线 MACD：

- 周线比日线更稳定，过滤短期噪声。
- 绿柱缩短通常代表下跌动能减弱。
- 金叉预期常用于捕捉趋势反转前段。
- 适合中期轮动和补涨研究。

### 5.6 支撑压力分析

支撑压力分析由 `SupportResistanceAnalyzer` 完成。

它会综合：

- 斐波那契回撤位。
- 近期波段高低点。
- 周期均线支撑。
- 成交量确认。
- 多个支撑方法的共振。

输出包括：

| 字段 | 含义 |
|---|---|
| `nearest_support` | 最近支撑位 |
| `nearest_resistance` | 最近压力位 |
| `support_distance_pct` | 当前价距支撑位百分比 |
| `resistance_distance_pct` | 当前价距压力位百分比 |
| `support_quality` | 支撑质量：strong / moderate / weak |
| `confluence_supports` | 共振支撑列表 |

支撑分析的用途是避免只看 MACD，而忽略价格所处位置。

### 5.7 个股综合评分

个股评分由 `StockFilter` 完成。

最终综合评分公式：

```text
综合评分 =
  趋势评分 * 20%
+ 技术评分 * 15%
+ 周线 MACD 评分 * 30%
+ 支撑位评分 * 15%
+ 补涨潜力评分 * 10%
+ 风险评分 * 10%
```

各项评分含义：

| 评分 | 权重 | 含义 |
|---|---:|---|
| 趋势评分 | 20% | 偏好微涨、横盘、未过度拉升的股票 |
| 技术评分 | 15% | 日线 MACD、趋势、周线信号综合判断 |
| 周线 MACD 评分 | 30% | 核心权重，重点看绿柱缩短、金叉预期、已金叉 |
| 支撑位评分 | 15% | 看是否接近支撑、多重支撑共振 |
| 补涨潜力评分 | 10% | 看短期是否仍有补涨空间 |
| 风险评分 | 10% | 排除 ST、异常价格、过大跌幅、过高涨幅等风险 |

当前默认筛选阈值：

```text
stock_score_threshold = 60
```

即综合评分低于 60 的股票不会进入最终候选。

### 5.8 输出

#### `weekly_macd_signals_*.csv`

用途：

- 保存所有候选股的周线 MACD 信号明细。
- 适合技术复盘和进一步排序。

当前示例：

```text
output/weekly_macd_signals_20260426_115650.csv
行数: 170
```

关键字段：

| 字段 | 解释 |
|---|---|
| `symbol` | 股票代码 |
| `name` | 股票名称 |
| `dif` | MACD 快线 |
| `dea` | MACD 慢线 |
| `macd_bar` | MACD 柱 |
| `signal_type` | 信号类型 |
| `signal_strength` | 信号强度 |
| `cross_status` | MACD 交叉状态 |
| `is_green_shortening` | 是否绿柱缩短 |
| `has_golden_cross_expectation` | 是否有金叉预期 |
| `consecutive_green_shorten` | 连续绿柱缩短周数 |
| `sector` | 所属板块 |
| `score` | 个股综合评分 |

#### `stock_scores_all_*.csv`

用途：

- 保存全局 TOP 个股评分结果。
- 更适合投资研究人员直接查看。

当前示例：

```text
output/stock_scores_all_20260426_115650.csv
行数: 30
```

关键字段：

| 字段 | 解释 |
|---|---|
| `stock_code` | 股票代码 |
| `stock_name` | 股票名称 |
| `sector_name` | 所属板块 |
| `综合评分` | 最终综合评分 |
| `趋势评分` | 价格趋势得分 |
| `技术评分` | 综合技术得分 |
| `周线MACD评分` | 周线 MACD 专项评分 |
| `支撑位评分` | 支撑位专项评分 |
| `风险评分` | 风险过滤得分 |
| `补涨潜力评分` | 补涨空间得分 |
| `当前价` | 当前价格 |
| `涨跌幅%` | 当前涨跌幅 |
| `推荐理由` | 系统生成的入选原因 |
| `风险警告` | 风险提示 |

#### `arbitrage_report_*.txt`

用途：

- 保存人类可读的完整分析报告。
- 包含总体概况、TOP 个股、周线 MACD 明细、支撑压力、推荐理由和风险提示。

当前示例：

```text
output/arbitrage_report_20260426_115650.txt
```

## 6. 附加模块：`analysis.divergence` 美股映射背离分析

背离分析模块用于回答：

> 美股对应 ETF 已经上涨，但 A 股映射板块在 5 日或 20 日维度仍然落后，并且 A 股板块日线 MACD 是否出现改善？

### 6.1 输入

输入包括：

- `scan_all_sectors()` 的板块扫描结果。
- A 股板块历史 K 线。
- 美股 ETF 历史 K 线。
- 中美映射表。
- 背离阈值参数。

### 6.2 筛选条件

候选条件包括：

```text
美股 20 日涨幅 > div_us20
且
A 股 20 日涨幅 < div_cn20
```

或：

```text
美股 5 日涨幅 > div_us5
且
A 股 5 日涨幅 < 0
```

或：

```text
中美 20 日涨幅差 > 动态背离阈值
且
美股 20 日涨幅 > 0
且
A 股 20 日涨幅 < div_cn20
```

### 6.3 MACD 状态分析

背离模块会对 A 股板块指数做日线 MACD 分析，判断：

- DIF 是否大于 DEA。
- 是否金叉。
- MACD 柱是红柱还是绿柱。
- 柱体是否缩短或拉长。
- 是否存在底背离。
- 是否存在金叉临近。

### 6.4 评级

输出评级包括：

| 评级 | 含义 |
|---|---|
| `HIGH` | 背离明显，且 A 股 MACD 出现底背离、金叉临近或已金叉 |
| `WATCH` | 背离明显，绿柱缩短，值得观察 |
| `POTENTIAL` | 有早期背离迹象，但技术确认度较弱 |

### 6.5 输出

如果有符合条件的背离机会，会生成：

```text
output/divergence_{timestamp}.csv
```

字段包括：

| 字段 | 解释 |
|---|---|
| `sector` | A 股板块 |
| `us_sector` | 美股行业 |
| `us_etf` | 美股 ETF |
| `us_20d` | 美股 20 日涨幅 |
| `cn_20d` | A 股 20 日涨幅 |
| `us_5d` | 美股 5 日涨幅 |
| `cn_5d` | A 股 5 日涨幅 |
| `gap` | 中美 20 日涨幅差 |
| `macd_status` | A 股板块 MACD 状态 |
| `rating` | 背离机会评级 |

本次运行结果显示：

```text
暂无符合条件的背离机会
```

因此没有新的背离机会 CSV 生成。

## 7. 映射表格式与维护方式

映射表文件：

```text
data/sector_mapping.xlsx
```

它有三张 sheet。

### 7.1 Sheet 1：`US-to-CN Sector Mapping`

列结构：

| 列 | 含义 |
|---|---|
| `US_Sector` | 美股行业名称 |
| `US_ETF_Code` | 美股 ETF 代码 |
| `CN_Sector` | A 股对应板块 |
| `CN_Sector_Code` | A 股板块代码或个股代码 |
| `Description` | 说明 |

示例：

```text
半导体 | SMH | 半导体及元件 | - | 芯片设计、制造、封测
Lean Hogs | COW | 猪肉 | - | US pork futures vs China pork sector
瘦肉猪 | COW | 猪肉 | sz002714 | Individual stock mapping
```

### 7.2 Sheet 2：`Sector-to-Stock Mapping`

列结构：

| 列 | 含义 |
|---|---|
| `US_Sector` | 美股行业 |
| `CN_Sector` | A 股板块 |
| `CN_Stock_Code` | A 股个股代码 |
| `CN_Stock_Name` | A 股个股名称 |
| `Weight` | 权重 |

用途：

- 维护更细粒度的“美股行业 -> A 股板块 -> A 股个股”映射。
- 可用于未来做个股级映射权重分析。

### 7.3 Sheet 3：`Parameters`

列结构：

| 列 | 含义 |
|---|---|
| `Param_Name` | 参数名 |
| `Value` | 当前值 |
| `Default` | 默认值 |
| `Description` | 参数说明 |

用途：

- 维护筛选阈值。
- 例如 `div_us20`、`div_cn20`、`div_us5`。

当前代码会优先合并 Excel 中的映射关系；如果 Excel 不存在或格式错误，则回退到 `sector_mapping_data.py` 的内置映射。

## 8. 本次运行结果概览

本次已经在 `ash` 环境中运行过两个程序。

### 8.1 板块筛选器结果

生成文件：

```text
output/cn_sectors_20260426_002100.csv
output/us_sectors_20260426_002100.csv
output/opportunities_20260426_002100.csv
```

结果规模：

| 文件 | 行数 | 含义 |
|---|---:|---|
| `cn_sectors_20260426_002100.csv` | 90 | A 股行业板块 |
| `us_sectors_20260426_002100.csv` | 46 | 美股行业 ETF |
| `opportunities_20260426_002100.csv` | 18 | 中美板块机会 |

### 8.2 周线 MACD 个股筛选结果

生成文件：

```text
output/weekly_macd_signals_20260426_115650.csv
output/stock_scores_all_20260426_115650.csv
output/arbitrage_report_20260426_115650.txt
```

结果规模：

| 指标 | 数值 |
|---|---:|
| A 股板块总数 | 90 |
| 实际扫描前 20 个板块 | 20 |
| 有信号板块 | 17 |
| 候选个股总数 | 170 |
| 全局 TOP 个股输出 | 30 |

输出中的 TOP 个股示例包括：

- 哈空调 `600202`
- 国发股份 `600538`
- 伟星股份 `002003`
- S 佳通 `600182`
- 士兰微 `600460`
- 全柴动力 `600218`
- 长电科技 `600584`

需要注意，部分个股重复出现，是因为不同板块映射到了相同或相近的新浪行业池。

## 9. 如何阅读最终选股结果

建议按以下顺序阅读：

### 第一步：看 `opportunities_*.csv`

先判断中美板块方向。

重点看：

- `美股行业`
- `ETF`
- `美股涨幅`
- `A股板块`
- `A股涨幅`
- `差距`
- `评分`

如果某个方向的美股涨幅显著领先，而 A 股对应板块涨幅较小，可以进入第二步。

### 第二步：看 `stock_scores_all_*.csv`

再判断具体个股。

重点看：

- `综合评分`
- `周线MACD评分`
- `支撑位评分`
- `风险评分`
- `推荐理由`
- `风险警告`

优先关注：

- 综合评分高。
- 周线 MACD 评分高。
- 风险警告少。
- 推荐理由中包含“绿柱缩短”“金叉预期”“强支撑”等描述。

### 第三步：看 `weekly_macd_signals_*.csv`

做技术复核。

重点看：

- `is_green_shortening`
- `has_golden_cross_expectation`
- `consecutive_green_shorten`
- `dif`
- `dea`
- `macd_bar`
- `signal_strength`

如果一个股票同时具备：

- 绿柱连续缩短。
- DIF 与 DEA 距离缩小。
- 信号强度较高。
- 综合评分靠前。

则它更符合该系统定义的“周线修复型候选”。

### 第四步：看 `arbitrage_report_*.txt`

最后看文本报告。

报告更适合人工阅读，会把每只股票的：

- 综合评分。
- 周线 MACD 状态。
- 支撑位。
- 压力位。
- 推荐理由。
- 风险提示。

集中展示出来。

## 10. 当前系统的优势

### 10.1 不是只看单市场

系统把美股行业 ETF 与 A 股行业板块连接起来，适合研究跨市场传导和主题轮动。

### 10.2 不是只看板块

板块机会只是第一层，最终还会进入板块内部做个股筛选。

### 10.3 周线信号权重较高

周线 MACD 在综合评分中占 30%，是最高权重因子，体现了系统对中期趋势修复的偏好。

### 10.4 加入支撑位和风险过滤

系统不只看 MACD，还会检查价格是否接近支撑、是否有多重支撑共振、是否存在 ST 或异常价格风险。

### 10.5 输出结构化

CSV 适合二次处理，TXT 报告适合人工阅读，日志适合排查数据源问题。

## 11. 当前系统的限制和风险

### 11.1 数据源可能不稳定

实际运行中出现过：

- 东方财富接口断连。
- AKShare 获取失败。
- 部分股票被 yfinance 判断为无数据或可能退市。
- 板块历史行情获取失败。

系统具备 fallback 机制，但 fallback 不等于数据一定准确。

### 11.2 美股 ETF 涨跌幅存在数据质量风险

本次运行中，`main.py` 的美股 ETF 涨跌幅出现过异常大数值，例如数万百分比级别的涨幅。

这很可能来自新浪美股 fallback 解析或字段校验不足。

因此，在修复该问题前：

- `us_sectors_*.csv` 中的异常涨跌幅需要人工复核。
- `opportunities_*.csv` 中基于异常美股涨幅计算出的机会评分不能直接用于投资判断。

### 11.3 板块映射还需要持续维护

部分 A 股板块可能映射到相同新浪行业代码，例如：

- `半导体` 与 `电子化学品`
- `轨交设备` 与 `工程机械`

这会导致：

- 成分股池重复。
- TOP 个股重复。
- 板块归因不够精确。

后续应优化映射表，提高行业和成分股匹配质量。

### 11.4 策略信号不是买卖指令

ASH 输出的是研究候选，不是交易建议。

最终决策仍需要结合：

- 基本面。
- 估值。
- 资金面。
- 市场环境。
- 事件催化。
- 仓位管理。
- 止损规则。

### 11.5 周线信号可能滞后

周线 MACD 更稳定，但也更滞后。

它适合捕捉中期修复，不适合高频交易或极短线追涨。

## 12. 建议的工作流

一个更完整的使用流程如下：

1. 运行 `main.py`。
2. 查看 `opportunities_*.csv`，确定跨市场强弱差方向。
3. 运行 `skills.weekly_macd_arbitrage`。
4. 查看 `stock_scores_all_*.csv`，选出综合评分靠前的股票。
5. 查看 `weekly_macd_signals_*.csv`，复核周线 MACD 状态。
6. 查看 `arbitrage_report_*.txt`，阅读支撑压力和风险提示。
7. 人工复核：
   - 行业逻辑是否成立。
   - 个股是否真属于该产业链。
   - 是否存在财务、公告、停牌、ST、退市等风险。
   - 成交量和流动性是否足够。
8. 再决定是否进入自选池或进一步研究。

## 13. 后续优化方向

### 13.1 修复美股 ETF 数据校验

应增加对美股涨跌幅的合理性校验，例如：

- 单周期涨跌幅超过合理范围时剔除。
- yfinance 与新浪差异过大时优先使用 yfinance。
- 保存异常数据源警告。

### 13.2 改善板块映射质量

建议持续维护 `sector_mapping.xlsx`：

- 补齐 ETF。
- 精细化 A 股板块。
- 增加个股级映射。
- 避免多个板块误映射到同一个成分池。

### 13.3 去重和归因优化

当前 TOP 个股可能因板块重叠而重复出现。

可以增加：

- 全局股票代码去重。
- 多板块归因字段。
- 重复出现次数作为热度指标。

### 13.4 引入基本面过滤

当前主要是行情和技术面。

可加入：

- 市值。
- PE / PB。
- 营收增长。
- 利润增长。
- 机构持仓。
- 业绩预告。

### 13.5 增加可视化报告

后续可以把结果转成：

- HTML Dashboard。
- Streamlit 页面。
- Plotly 交互图。
- Excel 多 sheet 报告。

## 14. 总结

ASH 的核心价值在于把“跨市场板块轮动”和“A 股个股技术筛选”串成一条完整研究链路。

它不是简单地问“今天哪个股票涨了”，而是按以下逻辑工作：

```text
美股行业强势
    ↓
映射到 A 股板块
    ↓
寻找 A 股滞涨或背离
    ↓
进入板块成分股
    ↓
计算周线 MACD 和支撑压力
    ↓
综合评分和风险过滤
    ↓
输出候选股票与研究报告
```

从投资研究角度看，它更适合作为：

- 主题轮动扫描器。
- 中美映射机会发现器。
- A 股板块内技术候选股筛选器。
- 自选池生成工具。

最终输出应被视为“研究线索”，而不是“自动买卖结论”。

