"""
ASH Skills - 策略技能模块
"""

__all__ = ['WeeklyMACDArbitrageSkill']


def __getattr__(name):
    """懒加载技能类，避免 python -m 执行子模块时重复导入。"""
    if name == 'WeeklyMACDArbitrageSkill':
        from .weekly_macd_arbitrage import WeeklyMACDArbitrageSkill
        return WeeklyMACDArbitrageSkill
    raise AttributeError(name)
