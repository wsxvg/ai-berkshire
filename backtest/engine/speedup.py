#!/usr/bin/env python3
"""引擎加速器：预处理 fund_charts + bisect 查找 + detect_sector 缓存

用法：在 run_backtest 之前 import 本模块即可自动加速。
预期效果：17min → 3-5min（3-5x 加速）
"""
import json, bisect, time
from functools import lru_cache
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys_path_hack = True
import sys
sys.path.insert(0, str(PROJECT))

# ── 1. 预处理 fund_charts：构建 dates[] + navs[] 并行数组 ──

_chart_index = {}  # code -> {"dates": [...], "navs": [...]}
_built = False

def build_chart_index(fund_charts):
    """把 {code: [{xAxis, yAxis}, ...]} 转成 {code: {dates: [...], navs: [...]}}"""
    global _chart_index, _built
    _chart_index = {}
    t0 = time.time()
    for code, pts in fund_charts.items():
        if not pts:
            _chart_index[code] = {"dates": [], "navs": []}
            continue
        dates = []
        navs = []
        for p in pts:
            d = p.get("xAxis", "")
            y = p.get("yAxis", 0)
            try:
                nav = (100 + float(y)) / 100
            except:
                nav = 1.0
            dates.append(d)
            navs.append(nav)
        # 确保按日期排序
        paired = sorted(zip(dates, navs), key=lambda x: x[0])
        _chart_index[code] = {
            "dates": [d for d, _ in paired],
            "navs": [n for _, n in paired],
        }
    _built = True
    elapsed = time.time() - t0
    print(f"  [加速器] 索引构建完成: {len(_chart_index)} 只基金 ({elapsed:.1f}s)")

def get_nav_at(code, cutoff_date, fund_charts=None):
    """用 bisect 二分查找某基金在 cutoff_date 当天或之前的净值"""
    if not _built:
        if fund_charts is None:
            return 1.0
        build_chart_index(fund_charts)
    
    idx = _chart_index.get(code)
    if not idx or not idx["dates"]:
        return 1.0
    
    dates = idx["dates"]
    navs = idx["navs"]
    
    # bisect_right 找到第一个 > cutoff_date 的位置
    pos = bisect.bisect_right(dates, cutoff_date)
    if pos == 0:
        return 1.0  # 没有早于 cutoff_date 的数据
    return navs[pos - 1]

def get_nav_series(code, cutoff_date, fund_charts=None):
    """返回某基金截止到 cutoff_date 的所有净值点 [{xAxis, yAxis}, ...] 的等价格式
    用于兼容 score_momentum_backtest 等需要完整序列的函数"""
    if not _built:
        if fund_charts is None:
            return []
        build_chart_index(fund_charts)
    
    idx = _chart_index.get(code)
    if not idx or not idx["dates"]:
        return []
    
    dates = idx["dates"]
    navs = idx["navs"]
    
    pos = bisect.bisect_right(dates, cutoff_date)
    if pos == 0:
        return []
    
    # 返回兼容格式
    return [{"xAxis": dates[i], "yAxis": (navs[i] - 1) * 100} for i in range(pos)]

# ── 2. detect_sector 缓存 ──

_sector_cache = {}

def cached_detect_sector(fund_name, fund_code=None, fund_holdings_cache=None):
    """带缓存的 detect_sector"""
    key = (fund_name, fund_code)
    if key in _sector_cache:
        return _sector_cache[key]
    
    # 调用原始函数
    from backtest.engine.backtest import detect_sector as _orig
    result = _orig(fund_name, fund_code, fund_holdings_cache)
    _sector_cache[key] = result
    return result

# ── 3. 应用 monkey-patch ──

def apply_speedup():
    """在 run_backtest 执行前调用，替换热路径函数"""
    import backtest.engine.backtest as bt
    
    # 保存原始函数
    if not hasattr(bt, '_orig_run_backtest'):
        bt._orig_run_backtest = bt.run_backtest
    
    def fast_run_backtest(config):
        # 预加载 fund_charts 并构建索引
        fund_charts_path = bt.DATA_DIR / "fund_charts.json"
        if fund_charts_path.exists():
            fund_charts = json.loads(fund_charts_path.read_text("utf-8"))
            build_chart_index(fund_charts)
        
        # 缓存 detect_sector
        if not hasattr(bt, '_orig_detect_sector'):
            bt._orig_detect_sector = bt.detect_sector
        bt.detect_sector = cached_detect_sector
        
        # 调用原始 run_backtest
        return bt._orig_run_backtest(config)
    
    bt.run_backtest = fast_run_backtest
    print("  [加速器] monkey-patch 已应用")

# 自动应用
apply_speedup()
