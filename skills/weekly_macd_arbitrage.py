#!/usr/bin/env python3
"""
ASH 核心策略 — 周线MACD套利系统 📈🔥

核心逻辑：
1. 获取板块内个股列表及历史数据
2. 计算周线MACD (12, 26, 9)
3. 检测"绿柱缩短+金叉预期"信号
4. 支撑位/压力位多重共振分析
5. 多数据源交叉验证
6. 综合评分排序输出

使用方法：
    # 作为独立模块运行
    python -m skills.weekly_macd_arbitrage
    
    # 作为技能模块调用
    from skills.weekly_macd_arbitrage import WeeklyMACDArbitrageSkill
    skill = WeeklyMACDArbitrageSkill()
    result = skill.run(sector_name="半导体")
    
    # 批量扫描
    results = skill.scan_all_sectors()

输出文件:
    output/weekly_macd_signals_{timestamp}.csv   — 周线MACD信号汇总
    output/stock_scores_{sector}_{timestamp}.csv — 个股评分明细
    output/arbitrage_report_{timestamp}.txt      — 综合报告
"""
import os
import sys
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# 确保能找到ash模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import FILTER_CONFIG, OUTPUT_DIR
from data.fetcher import AKShareFetcher, USFetcher, DataSourceValidator
from analysis.technical import (
    TechnicalAnalyzer, WeeklyMACDAnalyzer, SupportResistanceAnalyzer,
    WeeklyMACDSignal, SupportResistanceResult, TechAnalysisResult
)
from analysis.stock_filter import StockFilter, StockScore
from utils.helpers import setup_logging, save_results

logger = logging.getLogger(__name__)


@dataclass
class SectorScanResult:
    """板块扫描结果"""
    sector_name: str
    sector_change_pct: float
    stock_count: int
    candidate_count: int
    top_stocks: List[StockScore] = field(default_factory=list)
    best_signal: Optional[WeeklyMACDSignal] = None
    avg_score: float = 0.0
    has_opportunity: bool = False
    opportunity_level: str = "none"  # 'high' | 'medium' | 'low' | 'none'


class WeeklyMACDArbitrageSkill:
    """
    周线MACD套利策略 Skill
    
    这是ASH系统的核心策略，专门用于发现和筛选周线MACD金叉预期个股。
    """
    
    def __init__(self, config: dict = None):
        self.config = config or FILTER_CONFIG
        self.cn_fetcher = AKShareFetcher()
        self.us_fetcher = USFetcher()
        self.tech_analyzer = TechnicalAnalyzer()
        self.weekly_macd = WeeklyMACDAnalyzer()
        self.sr_analyzer = SupportResistanceAnalyzer()
        self.stock_filter = StockFilter()
        self.validator = DataSourceValidator()
        
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        logger.info("✅ 周线MACD套利系统初始化完成")
    
    def run(self, sector_name: str = None, 
            us_sector_name: str = None,
            max_stocks: int = 10,
            min_score: float = None) -> Dict[str, Any]:
        """
        运行周线MACD套利分析
        
        Args:
            sector_name: A股板块名称（可选）
            us_sector_name: 美股板块名称（可选，自动映射到A股）
            max_stocks: 最多输出个股数
            min_score: 最低评分阈值
            
        Returns:
            分析结果字典
        """
        print("\n" + "=" * 80)
        print("🚀 ASH 周线MACD套利系统 启动")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # 确定目标板块
        target_sectors = []
        
        if sector_name:
            target_sectors = [sector_name]
            print(f"\n🎯 目标板块: {sector_name}")
        elif us_sector_name:
            cn_mapping = self.us_fetcher.get_cn_sector_mapping(us_sector_name)
            if cn_mapping:
                target_sectors = cn_mapping
                print(f"\n🎯 美股 {us_sector_name} → A股 {', '.join(cn_mapping)}")
            else:
                print(f"⚠️ 未找到美股 {us_sector_name} 对应的A股板块")
                return {'status': 'error', 'message': '板块映射未找到'}
        else:
            # 自动扫描
            return self.scan_all_sectors(max_stocks, min_score)
        
        results = []
        all_stock_scores = []
        
        for sector in target_sectors:
            print(f"\n{'='*60}")
            print(f"📊 分析板块: {sector}")
            print(f"{'='*60}")
            
            sector_result = self._analyze_sector(sector, max_stocks, min_score)
            if sector_result:
                results.append(sector_result)
                all_stock_scores.extend(sector_result.top_stocks)
        
        # 汇总输出
        output = self._generate_output(results, all_stock_scores)
        
        # 保存结果
        self._save_results(results, all_stock_scores)
        
        return output
    
    def scan_all_sectors(self, max_stocks: int = 10, 
                          min_score: float = None) -> Dict[str, Any]:
        """
        扫描所有板块，找出周线MACD机会
        
        流程：
        1. 获取所有A股板块
        2. 对每个板块获取成分股
        3. 筛选有周线MACD信号的个股
        4. 综合评分排序
        """
        print("\n🔍 全市场扫描: 寻找周线MACD套利机会...")
        
        # 获取所有板块
        cn_df = self.cn_fetcher.fetch_cn_sectors(period=5)
        if cn_df.empty:
            print("❌ 获取A股板块数据失败")
            return {'status': 'error', 'message': '获取板块数据失败'}
        
        print(f"✅ 共 {len(cn_df)} 个行业板块")
        
        # 遍历板块
        all_results = []
        all_stocks = []
        sectors_with_signals = 0
        
        for idx, (_, row) in enumerate(cn_df.head(20).iterrows()):  # 前20个板块
            sector_name = row['sector_name']
            sector_change = row.get('change_pct', 0)
            
            try:
                sector_change = float(sector_change) if sector_change else 0
            except:
                sector_change = 0
            
            print(f"\n[{idx+1}/20] 📊 {sector_name} (涨跌幅: {sector_change:+.2f}%)")
            
            sector_result = self._analyze_sector(sector_name, max_stocks, min_score)
            
            if sector_result and sector_result.top_stocks:
                all_results.append(sector_result)
                all_stocks.extend(sector_result.top_stocks)
                sectors_with_signals += 1
                print(f"   ✅ 发现 {len(sector_result.top_stocks)} 个候选")
            else:
                print(f"   ➖ 无候选")
        
        # 全局排序
        all_stocks.sort(key=lambda x: x.score, reverse=True)
        top_global = all_stocks[:max_stocks * 3]
        
        print(f"\n{'='*80}")
        print(f"📊 全市场扫描完成！")
        print(f"   板块总数: {len(cn_df)}")
        print(f"   有信号的板块: {sectors_with_signals}")
        print(f"   候选个股总数: {len(all_stocks)}")
        print(f"   TOP{max_stocks*3} 个股如下:")
        print(f"{'='*80}")
        
        # 打印TOP个股
        self._print_top_stocks(top_global)
        
        # 输出
        output = {
            'status': 'success',
            'timestamp': self.timestamp,
            'total_sectors': len(cn_df),
            'sectors_with_signals': sectors_with_signals,
            'total_candidates': len(all_stocks),
            'results': all_results,
            'top_stocks': top_global,
        }
        
        self._save_results(all_results, top_global)

        try:
            from analysis.divergence import DivergenceAnalyzer
            div = DivergenceAnalyzer(self.cn_fetcher, self.us_fetcher, self.tech_analyzer, self.config)
            divergence_results = div.run(sector_results=all_results)
            output['divergence_results'] = divergence_results
        except Exception as e:
            logger.warning(f"美股映射背离分析失败(非致命): {e}")
        
        return output
    
    def _analyze_sector(self, sector_name: str, max_stocks: int = 10,
                         min_score: float = None) -> Optional[SectorScanResult]:
        """
        分析单个板块
        
        Args:
            sector_name: A股板块名称
            max_stocks: 最多个股数
            min_score: 最低评分
        """
        min_score = min_score or self.config.get('stock_score_threshold', 60)
        
        # 1. 获取板块成分股
        stocks_df = self.cn_fetcher.fetch_sector_stocks(sector_name)
        if stocks_df.empty:
            logger.warning(f"板块 [{sector_name}] 无成分股数据")
            return None
        
        stock_count = len(stocks_df)
        
        # 2. 获取个股历史数据（有限制数量，避免请求过多）
        max_history = min(20, len(stocks_df))  # 最多分析20只
        history_data = {}
        
        for i, (_, stock) in enumerate(stocks_df.head(max_history).iterrows()):
            code = str(stock.get('stock_code', ''))
            name = stock.get('stock_name', '')
            
            if not code:
                continue
            
            # 获取日线数据（需要至少1年数据才能做周线分析）
            hist = self.cn_fetcher.fetch_stock_history(code, days=400)  # 约1.5年日线
            if not hist.empty and len(hist) >= 120:
                history_data[code] = hist
                logger.debug(f"  获取 {name}({code}) 历史数据: {len(hist)} 天")
            
            # 避免过于频繁请求
            if i > 0 and i % 5 == 0:
                import time
                time.sleep(0.5)
        
        # 3. 个股筛选（含周线MACD评分）
        stock_scores = self.stock_filter.filter_stocks(
            sector_name, stocks_df.head(max_history), history_data
        )
        
        if not stock_scores:
            return SectorScanResult(
                sector_name=sector_name,
                sector_change_pct=0,
                stock_count=stock_count,
                candidate_count=0,
            )
        
        # 4. 计算板块平均分
        avg_score = np.mean([s.score for s in stock_scores])
        
        # 5. 判断机会等级
        # 评分>70且有绿柱缩短信号 = 高机会
        has_high = any(s.weekly_macd_score >= 70 and s.weekly_macd_signal and 
                       s.weekly_macd_signal.is_green_shortening for s in stock_scores)
        has_medium = any(s.score >= 65 for s in stock_scores)
        
        if has_high:
            level = "high"
        elif has_medium:
            level = "medium"
        elif stock_scores:
            level = "low"
        else:
            level = "none"
        
        return SectorScanResult(
            sector_name=sector_name,
            sector_change_pct=0,
            stock_count=stock_count,
            candidate_count=len(stock_scores),
            top_stocks=stock_scores[:max_stocks],
            best_signal=stock_scores[0].weekly_macd_signal if stock_scores else None,
            avg_score=round(avg_score, 1),
            has_opportunity=has_high or has_medium,
            opportunity_level=level,
        )
    
    def _generate_output(self, results: List[SectorScanResult],
                          all_stocks: List[StockScore]) -> Dict[str, Any]:
        """生成输出"""
        return {
            'status': 'success',
            'timestamp': self.timestamp,
            'sectors_analyzed': len(results),
            'total_candidates': len(all_stocks),
            'results': results,
            'top_stocks': sorted(all_stocks, key=lambda x: x.score, reverse=True),
        }
    
    def _print_top_stocks(self, stocks: List[StockScore]):
        """打印TOP个股"""
        if not stocks:
            print("  暂无符合条件的个股")
            return
        
        print(f"\n{'#':3s} {'名称':10s} {'代码':8s} {'综合评分':6s} {'周MACD':10s} {'支撑':6s} {'涨幅':7s}")
        print("-" * 55)
        
        for i, s in enumerate(stocks[:20], 1):
            macd_str = ""
            if s.weekly_macd_signal:
                if s.weekly_macd_signal.is_green_shortening:
                    macd_str = f"🔥绿缩{s.weekly_macd_signal.consecutive_green_shorten}周"
                elif s.weekly_macd_signal.has_golden_cross_expectation:
                    macd_str = "🌟金叉预期"
                elif s.weekly_macd_signal.cross_status == 'golden_cross':
                    macd_str = "✅金叉"
                else:
                    macd_str = s.weekly_macd_signal.signal_type
            
            print(f"{i:3d} {s.stock_name:10s} {s.stock_code:8s} {s.score:6.1f} "
                  f"{macd_str:10s} {s.support_score:6.1f} {s.change_pct:>+7.2f}%")
    
    def _save_results(self, results: List[SectorScanResult], 
                       top_stocks: List[StockScore]):
        """保存结果到CSV"""
        timestamp = self.timestamp
        
        # 保存周线MACD信号汇总
        signals_data = []
        for sector_result in results:
            for stock in sector_result.top_stocks:
                if stock.weekly_macd_signal:
                    d = stock.weekly_macd_signal.to_dict()
                    d['sector'] = sector_result.sector_name
                    d['score'] = stock.score
                    signals_data.append(d)
        
        if signals_data:
            df_signals = pd.DataFrame(signals_data)
            save_results(df_signals, f"weekly_macd_signals_{timestamp}.csv")
            print(f"\n📁 周线MACD信号已保存: weekly_macd_signals_{timestamp}.csv")
        
        # 保存个股评分明细
        stock_records = []
        for s in top_stocks:
            d = s.to_dict()
            stock_records.append(d)
        
        if stock_records:
            df_stocks = pd.DataFrame(stock_records)
            save_results(df_stocks, f"stock_scores_all_{timestamp}.csv")
            print(f"📁 个股评分已保存: stock_scores_all_{timestamp}.csv")
        
        # 生成文本报告
        report = self._generate_report(results, top_stocks)
        save_results(report, f"arbitrage_report_{timestamp}.txt")
        print(f"📁 分析报告已保存: arbitrage_report_{timestamp}.txt")
    
    def _generate_report(self, results: List[SectorScanResult],
                          top_stocks: List[StockScore]) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("📊 ASH 周线MACD套利分析报告")
        lines.append(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        lines.append("")
        
        # 总体概况
        high_count = len([r for r in results if r.opportunity_level == 'high'])
        med_count = len([r for r in results if r.opportunity_level == 'medium'])
        
        lines.append(f"📈 总体概况:")
        lines.append(f"   分析板块: {len(results)}")
        lines.append(f"   高机会板块: {high_count}")
        lines.append(f"   中等机会板块: {med_count}")
        lines.append(f"   候选个股: {len(top_stocks)}")
        lines.append("")
        
        # TOP个股详情
        lines.append("🏆 TOP个股推荐:")
        lines.append("-" * 80)
        
        for i, s in enumerate(top_stocks[:20], 1):
            lines.append(f"\n{i}. {s.stock_name}({s.stock_code}) [{s.sector_name}]")
            lines.append(f"   综合评分: {s.score}/100")
            
            if s.weekly_macd_signal:
                w = s.weekly_macd_signal
                lines.append(f"   周线MACD信号: {w.signal_type}(强度:{w.signal_strength:.0f})")
                lines.append(f"   DIF={w.dif:.4f} DEA={w.dea:.4f} BAR={w.macd_bar:.4f}")
                
                if w.is_green_shortening:
                    lines.append(f"   🔥 绿柱缩短{w.consecutive_green_shorten}周 (加速度:{w.bar_acceleration:.4f})")
                if w.has_golden_cross_expectation:
                    lines.append(f"   🌟 周线金叉预期 (DIF-DEA差距:{w.dif_dea_gap:.4f})")
                if w.cross_status == 'golden_cross':
                    lines.append(f"   ✅ 周线MACD已金叉!")
                if w.is_red_lengthening:
                    lines.append(f"   📊 红柱拉长{w.consecutive_red_lengthen}周")
            
            # 支撑位信息
            if s.tech_detail and s.tech_detail.support_resistance:
                sr = s.tech_detail.support_resistance
                lines.append(f"   支撑位: {sr.nearest_support:.2f} (距当前{s.support_distance_pct:+.1f}%)")
                lines.append(f"   压力位: {sr.nearest_resistance:.2f} (距当前{s.resistance_distance_pct:+.1f}%)")
                if sr.support_quality == 'strong':
                    lines.append(f"   💎 强支撑(多重共振)")
                if sr.confluence_supports:
                    lines.append(f"   共振支撑方法数: {len(sr.confluence_supports)}")
            
            lines.append(f"   涨跌幅: {s.change_pct:+.2f}%")
            lines.append(f"   推荐理由: {s.reason}")
            
            if s.warnings:
                lines.append(f"   ⚠️ 风险提示: {'; '.join(s.warnings)}")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("⚠️ 风险提示：本报告仅供参考，不构成投资建议。")
        lines.append("   周线MACD套利策略基于历史数据，过去表现不代表未来收益。")
        lines.append("   建议结合基本面分析和风险控制使用。")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def get_stock_weekly_macd_detail(self, stock_code: str, stock_name: str = "") -> Dict:
        """
        获取单只股票的周线MACD详细分析
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            详细分析结果字典
        """
        # 获取历史数据
        hist = self.cn_fetcher.fetch_stock_history(stock_code, days=400)
        if hist.empty:
            return {'error': '获取数据失败'}
        
        # 周线MACD分析
        signal = self.weekly_macd.analyze(hist, stock_code, stock_name)
        
        # 支撑压力分析
        sr = self.sr_analyzer.analyze(hist, stock_code, stock_name)
        
        # 综合技术分析
        tech = self.tech_analyzer.analyze(hist, stock_name, stock_code)
        
        result = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'data_days': len(hist),
        }
        
        if signal:
            result['weekly_macd'] = signal.to_dict()
        
        if sr:
            result['support_resistance'] = sr.to_dict()
        
        if tech:
            result['tech_summary'] = tech.summary
            result['tech_score'] = tech.score
        
        return result


# ==================== 命令行入口 ====================

def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="ASH 周线MACD套利系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                          # 全市场扫描
  %(prog)s --sector 半导体          # 分析指定板块
  %(prog)s --us-sector 半导体       # 从美股映射到A股
  %(prog)s --stock 600519           # 分析单只股票
  %(prog)s -v                       # 详细日志
        """
    )
    parser.add_argument('--sector', type=str, help='A股板块名称')
    parser.add_argument('--us-sector', type=str, help='美股板块名称')
    parser.add_argument('--stock', type=str, help='股票代码（单只分析）')
    parser.add_argument('--max-stocks', type=int, default=10, help='最多输出个股数')
    parser.add_argument('--min-score', type=float, default=None, help='最低评分阈值')
    parser.add_argument('--div-us20', type=float, default=FILTER_CONFIG.get('div_us20', 5.0),
                        help='背离筛选：美股20日最低涨幅(默认5)')
    parser.add_argument('--div-cn20', type=float, default=FILTER_CONFIG.get('div_cn20', 2.0),
                        help='背离筛选：A股20日最高涨幅(默认2)')
    parser.add_argument('--div-us5', type=float, default=FILTER_CONFIG.get('div_us5', 3.0),
                        help='背离筛选：美股5日最低涨幅(默认3)')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细日志')
    
    args = parser.parse_args()
    
    if args.verbose:
        os.environ['ASH_LOG_LEVEL'] = 'DEBUG'
    setup_logging()

    FILTER_CONFIG['div_us20'] = args.div_us20
    FILTER_CONFIG['div_cn20'] = args.div_cn20
    FILTER_CONFIG['div_us5'] = args.div_us5
    
    skill = WeeklyMACDArbitrageSkill()
    
    if args.stock:
        # 单只股票分析
        result = skill.get_stock_weekly_macd_detail(args.stock)
        print(f"\n📊 个股周线MACD分析: {args.stock}")
        print("=" * 60)
        
        if 'weekly_macd' in result:
            w = result['weekly_macd']
            print(f"  信号类型: {w.get('signal_type', 'N/A')}")
            print(f"  信号强度: {w.get('signal_strength', 0)}")
            print(f"  DIF: {w.get('dif', 0)}")
            print(f"  DEA: {w.get('dea', 0)}")
            print(f"  MACD BAR: {w.get('macd_bar', 0)}")
            print(f"  绿柱缩短: {w.get('is_green_shortening', False)}")
            print(f"  金叉预期: {w.get('has_golden_cross_expectation', False)}")
            print(f"  连续缩短周数: {w.get('consecutive_green_shorten', 0)}")
            print(f"  交叉状态: {w.get('cross_status', 'none')}")
        
        if 'support_resistance' in result:
            sr = result['support_resistance']
            print(f"\n  支撑位: {sr.get('nearest_support', 0)}")
            print(f"  压力位: {sr.get('nearest_resistance', 0)}")
            print(f"  支撑质量: {sr.get('support_quality', 'unknown')}")
        
        if 'tech_summary' in result:
            print(f"\n  综合评语: {result['tech_summary']}")
        
        # 保存结果
        save_results(pd.DataFrame([result]), f"stock_detail_{args.stock}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        
    elif args.sector or args.us_sector:
        # 板块分析
        result = skill.run(
            sector_name=args.sector,
            us_sector_name=args.us_sector,
            max_stocks=args.max_stocks,
            min_score=args.min_score,
        )
        if result.get('status') == 'success':
            top_stocks = result.get('top_stocks', [])
            skill._print_top_stocks(top_stocks)
    else:
        # 全市场扫描
        result = skill.scan_all_sectors(args.max_stocks, args.min_score)


if __name__ == "__main__":
    main()
