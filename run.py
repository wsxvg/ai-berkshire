#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Berkshire 基金监控 — API实时版
用法: py -3.10 run.py

数据来源：京东金融API（实时，不用缓存）
- get_user_holdings(None)  → 你的实盘持仓（带你看到的真实盈亏）
- get_user_holdings(uid)   → 大佬持仓
- get_fund_detail(code)    → 基金详情+净值曲线+费率+经理
"""
import json, sys, math
from pathlib import Path
from datetime import datetime, timedelta

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

def _pct_str(v):
    """格式化百分比"""
    if v > 0: return '+%.2f%%' % v
    if v < 0: return '%.2f%%' % v
    return '0.00%'

def _money(v):
    """格式化金额"""
    if isinstance(v, str):
        v = float(str(v).replace(',', '').replace('+', '').replace('%', ''))
    return '%.2f' % float(v) if abs(v) < 10000 else '%.2fw' % (float(v) / 10000)

def _parse_pct(s):
    """解析百分比字符串 '+16.77%' -> 16.77"""
    if isinstance(s, (int, float)): return float(s)
    return float(str(s).replace(',', '').replace('+', '').replace('%', '').strip())

def compute_rsi_from_chart(pts, period=14):
    """从chart_points计算RSI"""
    if len(pts) < period + 1: return 50.0
    navs = [float(p.get('nav', (100 + float(p.get('yAxis', 0))) / 100)) for p in pts[-period-1:]]
    deltas = [navs[i] - navs[i-1] for i in range(1, len(navs))]
    gains = sum(d for d in deltas if d > 0) / period
    losses = sum(-d for d in deltas if d < 0) / period
    if losses == 0: return 100.0
    rs = gains / losses
    return round(100 - 100 / (1 + rs), 1)

def compute_ma_trend(pts, short=20, long=60):
    """判断均线趋势 1=上升 -1=下降 0=不足"""
    if len(pts) < long: return 0
    navs = [float(p.get('nav', (100 + float(p.get('yAxis', 0))) / 100)) for p in pts]
    ma_short = sum(navs[-short:]) / short
    ma_long = sum(navs[-long:]) / long
    return 1 if ma_short > ma_long else -1

# ====== 风控规则 ======
def risk_check(profit_pct, rsi, trend):
    """根据盈亏+RSI+趋势给出操作建议"""
    if profit_pct <= -15:
        return ('[强卖]', '止损: 亏损超15%%')
    if profit_pct <= -10:
        return ('[减仓]', '预警: 亏损超10%%, 减半防守')
    if rsi > 80:
        return ('[止盈]', '超买: RSI>80, 落袋为安')
    if rsi > 70 and profit_pct > 20:
        return ('[减仓]', '盈利超20%%+RSI>70, 减仓锁利')
    if rsi > 70:
        return ('[观望]', 'RSI>70 偏高, 不加仓')
    if 40 <= rsi <= 55 and profit_pct > 0 and trend > 0:
        return ('[持有]', '健康上涨, 继续持有')
    if 30 <= rsi <= 50 and trend > 0:
        return ('[加仓]', '回调中趋势向上, 可考虑加仓')
    if trend < 0 and profit_pct < -5:
        return ('[减仓]', '趋势破位+亏损, 减仓')
    return ('[持有]', '正常')

def risk_icon(action):
    return {'[强卖]': '!!', '[止盈]': '+ ', '[减仓]': '! ', '[加仓]': '>>', '[持有]': '  ', '[观望]': '..'}.get(action, '??')

def main():
    print()
    print('=' * 75)
    print('  AI Berkshire Fund Monitor — ' + datetime.now().strftime('%Y-%m-%d %H:%M'))
    print('=' * 75)

    # ====== Step 1: 初始化API ======
    try:
        from tools.jd_finance_api import _ensure_cookies, FOLLOWED_USERS
        from tools.jd_finance_api import get_user_holdings, get_fund_detail
        cookies = _ensure_cookies()
        if not cookies:
            print('\n[ERROR] No valid JD cookies. Put cookies in data/jd_auth/cookies.json')
            print('Or run: py -3.10 scripts/auto-pipeline.py to refresh via browser login')
            return
        api_ok = True
    except Exception as e:
        print('\n[ERROR] API init failed: %s' % str(e)[:100])
        return

    # ====== Step 2: 你的实盘持仓 ======
    print('\n' + '─' * 75)
    print('  你的实盘持仓 (京东金融实时数据)')
    print('─' * 75)

    my = get_user_holdings(target_uid=None, cookies=cookies, use_cache=False)
    my_funds = my.get('holdings', []) if my else []
    if not my_funds:
        print('  (无持仓或API返回空)')
    else:
        total_in = 0
        total_out = 0
        my_actions = []

        print('  %-28s %10s %10s %8s %6s  %s' % ('基金', '持仓', '盈亏', 'RSI', '趋势', '建议'))
        print('  ' + '-' * 72)

        for h in my_funds:
            code = h.get('code', '')
            name = h.get('name', '')[:26]
            cur_amount = _parse_pct(h.get('amount', '0'))  # API返回的是当前市值
            profit_pct = _parse_pct(h.get('profit_rate', '0%'))
            profit_amt = _parse_pct(h.get('profit', '0'))
            # 投入 = 当前市值 / (1 + 盈亏%/100)
            invested = cur_amount / (1 + profit_pct / 100) if (1 + profit_pct / 100) != 0 else cur_amount

            total_in += invested
            total_out += cur_amount

            # 获取基金详情（含净值曲线）
            rsi = 50.0
            trend = 0
            detail = get_fund_detail(code, use_cache=False, cookies=cookies)
            if detail and detail.get('chart', {}).get('chart_points'):
                pts = detail['chart']['chart_points']
                if len(pts) >= 20:
                    rsi = compute_rsi_from_chart(pts)
                    trend = compute_ma_trend(pts)

            action, reason = risk_check(profit_pct, rsi, trend)
            my_actions.append(action)

            trend_str = '↑' if trend > 0 else '↓' if trend < 0 else '—'
            print('  %-28s %9s  %9s  %5.0f  %-4s  %s %s' % (
                name, _money(invested), _pct_str(profit_pct), rsi, trend_str,
                risk_icon(action), reason))

        total_pnl = total_out - total_in
        total_pnl_pct = total_pnl / total_in * 100 if total_in > 0 else 0
        print('  ' + '-' * 72)
        print('  合计: %d只  投入=Y%s  现值=Y%s  盈亏=%s' % (
            len(my_funds), _money(total_in), _money(total_out), _pct_str(total_pnl_pct)))
        print()

    # ====== Step 3: 大佬持仓监控 ======
    print('─' * 75)
    print('  大佬持仓监控 (跟投参考)')
    print('─' * 75)

    player_funds = {}
    for uid, name in list(FOLLOWED_USERS.items())[:15]:
        uid_key = 'jimu_user_info-%s' % uid
        try:
            bp = get_user_holdings(target_uid=uid_key, cookies=cookies, use_cache=False)
            if not bp or not bp.get('holdings'):
                continue
            holdings = bp['holdings']
            player_funds[name] = holdings

            # 只显示有买入信号的（最近新增或盈利好的）
            new = [h for h in holdings if _parse_pct(h.get('profit_rate', '0%')) < 5 and _parse_pct(h.get('profit_rate', '0%')) > -5]
            top_win = sorted(holdings, key=lambda h: -_parse_pct(h.get('profit_rate', '0%')))[:3]
            top_loss = sorted(holdings, key=lambda h: _parse_pct(h.get('profit_rate', '0%')))[:1]

            print('  [%s] %d只  盈利Top: %s (+%s)' % (
                name, len(holdings),
                top_win[0].get('name', '')[:14] if top_win else '-',
                _parse_pct(top_win[0].get('profit_rate', '0%')) if top_win else 0))

        except Exception as e:
            continue

    # ====== Step 4: 大佬交叉持仓 ======
    print()
    print('─' * 75)
    print('  大佬重叠持仓 (多人同时持有的基金 → 共识信号)')
    print('─' * 75)

    # 统计每只基金被多少大佬持有
    fund_holders = {}
    for pname, holdings in player_funds.items():
        for h in holdings:
            code = h.get('code', '')
            if not code: continue
            fund_holders.setdefault(code, {'names': [], 'holders': [], 'name': h.get('name', '')})
            fund_holders[code]['holders'].append(pname)

    # 被2+大佬持有的基金
    consensus = [(code, info) for code, info in fund_holders.items() if len(info['holders']) >= 2]
    consensus.sort(key=lambda x: -len(x[1]['holders']))

    print('  %-8s %-24s %4s  %s' % ('Code', 'Name', '人数', '大佬'))
    print('  ' + '-' * 70)
    for code, info in consensus[:10]:
        print('  %-8s %-24s %2d人  %s' % (
            code, info['name'][:22], len(info['holders']),
            ', '.join(info['holders'][:3])))

    # ====== Step 5: 风控摘要 ======
    print()
    print('─' * 75)
    print('  风控建议 (针对你的持仓)')
    print('─' * 75)
    print('  1. [强卖] 亏损>15%% → 立即止损清仓')
    print('  2. [减仓] 亏损>10%%或RSI>70盈利>20%% → 减半仓')
    print('  3. [加仓] RSI在30-50且趋势向上 → 可补仓')
    print('  4. [持有] 耐心持有，不做操作')
    print()
    print('─' * 75)
    print('  实时API测试通过 | 你的持仓: %d只 | 大佬: %d人 | 交叉持有: %d只' % (
        len(my_funds), len(player_funds), len(consensus)))

if __name__ == '__main__':
    main()
