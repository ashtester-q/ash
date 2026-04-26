#!/usr/bin/env python3
"""
ASH - AI股票板块筛选器 🚀

核心逻辑：
1. 获取A股行业板块实时行情（同花顺）
2. 获取美股行业ETF行情（yfinance）
3. 中美板块对照分析：找出美股涨得多、A股滞涨的板块
4. 技术分析 + 个股二次筛选

使用:
    python main.py              # 全流程运行
    python main.py -v           # 详细日志
    python main.py --period 20  # 20日周期
"""
import os
import sys
import argparse
import logging
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import OUTPUT_DIR
from utils.helpers import setup_logging, save_results
from data.fetcher import AKShareFetcher, USFetcher

logger = logging.getLogger(__name__)


def compare_markets(cn_df: pd.DataFrame, us_df_5d: pd.DataFrame, us_df_20d: pd.DataFrame = None):
    """
    中美板块对照分析核心逻辑
    """
    us_fetcher = USFetcher()
    results = []
    
    print("\n" + "=" * 75)
    print("🎯 中美板块联动分析")
    print("=" * 75)
    
    for _, us_row in us_df_5d.iterrows():
        us_name = us_row['sector_name']
        us_chg_5d = us_row['change_pct']
        
        # 找对应的A股板块
        cn_names = us_fetcher.get_cn_sector_mapping(us_name)
        if not cn_names:
            continue
        
        cn_match = cn_df[cn_df['sector_name'].isin(cn_names)]
        if cn_match.empty:
            continue
        
        # A股平均涨幅
        avg_cn_chg = cn_match['change_pct'].mean()
        gap_5d = round(us_chg_5d - avg_cn_chg, 2)
        
        # 20日差距
        gap_20d = None
        if us_df_20d is not None:
            us_row_20 = us_df_20d[us_df_20d['sector_name'] == us_name]
            if not us_row_20.empty:
                us_chg_20d = us_row_20.iloc[0]['change_pct']
                cn_match_20 = None  # A股20日数据暂缺
                gap_20d = us_chg_20d  # 仅美股方向
        
        # 评分：美股涨得越多 + A股涨得越少 = 机会越大
        if us_chg_5d > 2 and gap_5d > 2:
            score = us_chg_5d * 0.6 + gap_5d * 0.4
            
            # 判断机会等级
            if gap_5d > 5:
                level = "🔥🔥 大机会"
            elif gap_5d > 3:
                level = "🔥 机会"
            else:
                level = "⭐ 关注"
            
            results.append({
                'us_sector': us_name,
                'us_etf': us_row['etf_code'],
                'us_chg_5d': us_chg_5d,
                'cn_sectors': ' / '.join(cn_names),
                'cn_avg_chg': round(avg_cn_chg, 2),
                'gap_5d': gap_5d,
                'score': round(score, 1),
                'level': level,
                'details': cn_match[['sector_name', 'change_pct', 'up_count', 'down_count']].to_dict('records'),
            })
    
    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 打印结果
    if results:
        print(f"\f{'等级':12s} {'美股行业':8s} {'涨幅':>6s} {'→':4s} {'A股板块':16s} {'涨幅':>6s} {'差距':>6s} {'评分':>4s}")
        print("-" * 75)
        for r in results:
            print(f"{r['level']:12s} {r['us_sector']:8s} {r['us_chg_5d']:+.2f}% {'→':4s} {r['cn_sectors']:16s} {r['cn_avg_chg']:+.2f}% {r['gap_5d']:+.2f}% {r['score']:5.1f}")
        
        print("\n📋 各板块详细数据:")
        for r in results[:5]:  # 只看前5个
            print(f"\n  📌 {r['us_sector']} ({r['us_etf']}): 美股{r['us_chg_5d']:+.2f}%")
            for d in r['details'][:3]:
                print(f"     ├ A股 {d['sector_name']}: {d['change_pct']:+.2f}% (↑{d['up_count']} ↓{d['down_count']})")
    else:
        print("\n📊 当前未发现明显的中美板块轮动机会")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="ASH - AI股票板块筛选器")
    parser.add_argument('--period', type=int, default=5, help='分析周期天数')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细日志')
    args = parser.parse_args()
    
    if args.verbose:
        os.environ['ASH_LOG_LEVEL'] = 'DEBUG'
    setup_logging()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 75)
    print("🚀 ASH - AI股票板块筛选器 启动")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)
    
    # 初始化
    cn_fetcher = AKShareFetcher()
    us_fetcher = USFetcher()
    
    # ===== 1. 获取A股板块 =====
    print("\n📡 [1/3] 获取A股行业板块数据...")
    cn_df = cn_fetcher.fetch_cn_sectors(period=5)
    if cn_df.empty:
        print("❌ 获取A股数据失败")
        return
    print(f"✅ 获取到 {len(cn_df)} 个行业板块")
    
    # A股涨幅排名
    print(f"\n📊 A股行业板块涨跌幅 TOP 10:")
    print(f"{'排名':4s} {'板块名称':12s} {'涨跌幅':>7s} {'↑家数':>6s} {'↓家数':>6s} {'领涨股':12s}")
    print("-" * 55)
    for i, (_, row) in enumerate(cn_df.head(10).iterrows()):
        print(f"{i+1:4d} {row['sector_name']:12s} {row['change_pct']:>+7.2f}% {row['up_count']:>6d} {row['down_count']:>6d} {str(row.get('lead_stock','')):12s}")
    
    # ===== 2. 获取美股板块 =====
    print("\n📡 [2/3] 获取美股行业ETF数据...")
    us_df_5d = us_fetcher.fetch_us_sectors(period_days=5)
    if us_df_5d.empty:
        print("❌ 获取美股数据失败，尝试安装: pip install yfinance")
        return
    print(f"✅ 获取到 {len(us_df_5d)} 个行业ETF")
    
    print(f"\n📊 美股行业ETF涨跌幅 TOP 10:")
    print(f"{'排名':4s} {'行业':10s} {'ETF':6s} {'涨跌幅':>7s}")
    print("-" * 30)
    for i, (_, row) in enumerate(us_df_5d.head(10).iterrows()):
        print(f"{i+1:4d} {row['sector_name']:10s} {row['etf_code']:6s} {row['change_pct']:>+7.2f}%")
    
    # 获取20日数据
    us_df_20d = us_fetcher.fetch_us_sectors(period_days=20)
    
    # ===== 3. 中美对照分析 =====
    print("\n📡 [3/3] 中美板块联动分析...")
    opportunities = compare_markets(cn_df, us_df_5d, us_df_20d)
    
    # ===== 4. 保存结果 =====
    save_results(cn_df, f"cn_sectors_{timestamp}.csv")
    save_results(us_df_5d, f"us_sectors_{timestamp}.csv")
    
    if opportunities:
        opp_df = pd.DataFrame([{
            '等级': r['level'],
            '美股行业': r['us_sector'],
            'ETF': r['us_etf'],
            '美股涨幅': f"{r['us_chg_5d']:+.2f}%",
            'A股板块': r['cn_sectors'],
            'A股涨幅': f"{r['cn_avg_chg']:+.2f}%",
            '差距': f"{r['gap_5d']:+.2f}%",
            '评分': r['score'],
        } for r in opportunities])
        save_results(opp_df, f"opportunities_{timestamp}.csv")
    
    print(f"\n{'='*75}")
    print(f"✅ 分析完成！结果已保存至: {OUTPUT_DIR}")
    print(f"{'='*75}")
    
    logger.info("ASH 分析流程完成")


if __name__ == "__main__":
    main()
