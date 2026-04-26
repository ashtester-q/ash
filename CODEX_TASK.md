# ASH System Optimization Tasks - Execute All Three

## Context
You are working on the ASH stock analysis system at ~/projects/ash/.
The main entry is `main.py`. The core skill is `skills/weekly_macd_arbitrage.py` (run via `python3 -m skills.weekly_macd_arbitrage`).
Sector mapping is in `data/sector_mapping_data.py`. Config is in `config.py`.
US stock fetcher is in `data/fetcher.py` (USFetcher class).

---

## Task 1: US-Stock/A-Stock Divergence Analysis Module

After `scan_all_sectors()` completes in weekly_macd_arbitrage.py, add a NEW module `analysis/divergence.py` with class `DivergenceAnalyzer`.

### 1.1 Calculate Period Returns
For each scanned sector, fetch both the A-share sector index AND the US corresponding sector ETF:
- A-share: use AKShareFetcher.fetch_sector_history(sector_name, period_days)
- US: use USFetcher.fetch_etf_history(etf_code, period_days)
- Compute cumulative returns for 5-day and 20-day windows

### 1.2 Screen Divergence Candidates
Mark sectors that satisfy:
- US sector 20-day return > X% AND A-stock counterpart 20-day return < Y%
- OR US 5-day return > Z% AND A-stock 5-day return < 0%
- Parameters X/Y/Z must support CLI args: --div-us20 X --div-cn20 Y --div-us5 Z
- Defaults: X=5, Y=2, Z=3
- Also detect dynamic threshold: if historical avg gap > std, auto-adjust

### 1.3 MACD Trend Analysis on Divergent Sectors
For each divergent sector, run DAILY MACD on the A-stock sector index:
- Use MACD(12, 26, 9) from config.FILTER_CONFIG
- Detect: golden_cross, death_cross, DIF vs DEA position, bar color trend
- Detect BOTTOM DIVERGENCE: price making new low but MACD histogram NOT making new low

### 1.4 Opportunity Rating
Combine divergence severity + MACD trend into 3 tiers:
- HIGH: Clear divergence (>5% gap) + MACD bottom divergence OR golden cross imminent
- WATCH: Clear divergence + MACD below zero but green bars shortening
- POTENTIAL: Early divergence signs + MACD still declining

### 1.5 Output Format
Print a TABLE with header "📊 美股映射背离机会" containing:
| Sector | US 20d | CN 20d | Gap | MACD Status | Rating |
Save results to output/divergence_{timestamp}.csv

### Integration
In weekly_macd_arbitrage.py, after scan_all_sectors() completes, call:
```python
from analysis.divergence import DivergenceAnalyzer
div = DivergenceAnalyzer(skill.cn_fetcher, skill.us_fetcher, skill.tech_analyzer)
div.run(sector_results=all_results)
```

---

## Task 2: Editable Sector Mapping Excel File

Create `data/sector_mapping.xlsx` with 3 sheets:

### Sheet 1: US-to-CN Sector Mapping
Columns: US_Sector | US_ETF_Code | CN_Sector | CN_Sector_Code | Description
Populate with data from sector_mapping_data.py
Add at least these extra rows as templates:
- Lean Hogs | COW | 猪肉 | - | US pork futures vs China pork sector
- 瘦肉猪 | - | 猪肉 | - | US lean hogs vs China pork
- 瘦肉猪 | - | - | 牧原股份(sz002714) | Individual stock mapping
- 瘦肉猪 | - | - | 正邦科技(sz002157) | Individual stock mapping

### Sheet 2: Sector-to-Stock Mapping
Columns: US_Sector | CN_Sector | CN_Stock_Code | CN_Stock_Name | Weight
Allow mapping from US sector -> A-stock sector -> individual stocks.

### Sheet 3: Parameters
Columns: Param_Name | Value | Default | Description
Pre-fill all FILTER_CONFIG params, plus new divergence params X/Y/Z.

### Code Changes
Update sector_mapping_data.py to also read from this xlsx file at runtime.
Add `load_mapping_from_excel()` function.
Instruction comment at top of xlsx Sheet 1 explaining format.

---

## Task 3: System Diagnostics & Issues

### 3.1 EastMoney Data Source
Check if EastMoney (东方财富) API can be integrated for cross-validation.
The config already references eastmoney but there is no implementation.
Create `data/fetcher_eastmoney.py` with class `EastMoneyFetcher`:
- Fetch sector list: https://push2.eastmoney.com/api/qt/clist/get
- Fetch stock K-line: https://push2his.eastmoney.com/api/qt/stock/kline/get
- Use proper headers mimicking browser
- Add to DataSourceValidator for cross-validation

### 3.2 Other Issues to Check
- AKShare rate limiting: add proper delays between requests
- Error handling: wrap all fetcher calls in try/except with retry (max 3)
- Cache: implement simple JSON cache for sector data (TTL 1 hour)
- Missing US ETF codes in sector_mapping: add actual ETF tickers where blank
- Verify weekly_macd_arbitrage main() actually runs: test with --stock 600519
- Check if yfinance import handles connection errors gracefully

### 3.3 After Implementation
Run: `cd ~/projects/ash && python3 -c "from skills.weekly_macd_arbitrage import WeeklyMACDArbitrageSkill; s=WeeklyMACDArbitrageSkill(); print('Init OK')"`
If fails, fix and retry until init succeeds.

---

## Execution Order
1. Read all existing code first
2. Implement Task 2 first (Excel mapping - no dependencies)
3. Implement Task 1 (divergence module - depends on understanding existing code)
4. Implement Task 3 (diagnostics - depends on full code understanding)
5. Run the verification command from Task 3.3

## Model
Use the best available model. If codex supports --model gpt-5.5, use it.

## Important
- Write production-quality code with docstrings and type hints
- Keep existing code working - add, don't break
- All new files should be importable without errors
- Test imports after each file creation
