"""5 策略集中化回测器：机器基线 / 跟单大佬 / 核心+卫星 / 共识重仓 / 加权共识
使用统一 Portfolio + 净值数据，分 5 个 strategy_type 实现。
"""
import sys, json
import time
from pathlib import Path
from datetime import datetime
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from backtest.engine.backtest import Portfolio, _float, score_fund_backtest, score_momentum_backtest, kelly_allocate, RISK_FREE_RATE
DATA_DIR = PROJECT_DIR / 'backtest' / 'data'
CACHE_DIR = PROJECT_DIR / 'data' / 'fund_cache'


def load_data():
    """加载回测所需的所有数据"""
    with open(DATA_DIR / 'fund_charts.json', 'r', encoding='utf-8') as f:
        fund_charts = json.load(f)
    with open(PROJECT_DIR / 'data' / 'fund_name_map.json', 'r', encoding='utf-8') as f:
        fund_name_map = json.load(f)
    # 反向: code→name
    code_to_name = {}
    for name, code in fund_name_map.items():
        if code not in code_to_name:
            code_to_name[code] = name
    # watchlist
    with open(PROJECT_DIR / 'data' / 'watchlist.json', 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    # 加载 fund_rules
    fund_rules = {}
    for f in CACHE_DIR.glob('trade_rules_*.json'):
        code = f.stem.replace('trade_rules_', '')
        try:
            fund_rules[code] = json.loads(f.read_text(encoding='utf-8'))
        except: pass
    # 加载 holdings_snapshot
    holdings_snapshot = {}
    if (PROJECT_DIR / 'data' / 'holdings_snapshot.json').exists():
        with open(PROJECT_DIR / 'data' / 'holdings_snapshot.json', 'r', encoding='utf-8') as f:
            holdings_snapshot = json.load(f)
    return {
        'fund_charts': fund_charts,
        'fund_name_map': fund_name_map,
        'code_to_name': code_to_name,
        'watchlist': watchlist,
        'fund_rules': fund_rules,
        'holdings_snapshot': holdings_snapshot,
    }


def get_backtest_dates(start_date, end_date):
    """生成回测日期列表（用 fund_charts 里所有有数据的日期的并集，按日期排序）"""
    charts = json.loads((DATA_DIR / 'fund_charts.json').read_text(encoding='utf-8'))
    all_dates = set()
    for pts in charts.values():
        for p in pts:
            d = p.get('xAxis', '')[:10]
            if start_date <= d <= end_date:
                all_dates.add(d)
    return sorted(all_dates)


def calc_metrics(portfolio, initial_cash):
    """计算回测指标"""
    if not portfolio.daily_values:
        return None
    final = portfolio.daily_values[-1]['total']
    total_invested = initial_cash + portfolio.monthly_injections
    total_return = (final - total_invested) / total_invested * 100
    values = [d['total'] for d in portfolio.daily_values]
    peak = values[0]
    max_dd = 0
    for v in values[1:]:
        if v > peak: peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd: max_dd = dd
    daily_returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values)) if values[i-1] > 0]
    n = len(values)
    if n > 1 and total_invested > 0:
        annualized = ((final / total_invested) ** (252.0 / n) - 1) * 100
    else:
        annualized = 0
    if len(daily_returns) > 1:
        avg = sum(daily_returns) / len(daily_returns)
        var = sum((r - avg) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        vol = (var ** 0.5) * (252 ** 0.5) * 100
        sharpe = (annualized - RISK_FREE_RATE * 100) / vol if vol > 0 else 0
    else:
        sharpe = 0
    return {
        'final_value': round(final, 2),
        'total_return': round(total_return, 2),
        'annualized': round(annualized, 2),
        'max_dd': round(max_dd, 2),
        'sharpe': round(sharpe, 2),
        'trades': len([t for t in portfolio.trades if t.get('action') == 'buy']),
    }


def get_benchmark_return(chart_pts, start_date, end_date):
    """计算基准（沪深 300 = 110020）的同期收益"""
    valid = [p for p in chart_pts if start_date <= p.get('xAxis', '')[:10] <= end_date]
    if not valid:
        return 0.0
    sorted_pts = sorted(valid, key=lambda x: x.get('xAxis', ''))
    start_y = _float(sorted_pts[0].get('yAxis', 0))
    end_y = _float(sorted_pts[-1].get('yAxis', 0))
    return (end_y - start_y) / (100 + start_y) * 100  # 累计收益率% → 期间收益率%


# ============================================================
# 策略 0: 机器基线（直接调用现有 backtest）
# ============================================================
def run_baseline(config):
    from backtest.engine.backtest import run_backtest
    return run_backtest(config)


# ============================================================
# 策略 A: 集中跟单 TOP 5 大佬
# ============================================================
def run_follow_leaders(config):
    """等权跟单 5 位高收益大佬最新持仓，每周调仓"""
    data = load_data()
    holdings_snapshot = data['holdings_snapshot'].get('holdings', {})

    # 选 TOP 5 大佬（按持仓 profit_rate 平均值排序）
    leader_scores = []
    for user, funds in holdings_snapshot.items():
        if not isinstance(funds, list) or len(funds) < 3:
            continue
        profits = []
        for f in funds:
            try:
                p = float(str(f.get('profit_rate', '0%')).replace('%', '').replace('+', ''))
                profits.append(p)
            except: pass
        if profits:
            avg = sum(profits) / len(profits)
            leader_scores.append((user, avg, len(funds)))
    leader_scores.sort(key=lambda x: x[1], reverse=True)
    top_leaders = [l[0] for l in leader_scores[:5]]
    print(f"  [A] TOP 5 大佬: {top_leaders}")

    # 聚合 TOP 5 大佬的当前持仓（等权）
    target_funds = {}  # code → 权重
    for user in top_leaders:
        funds = holdings_snapshot.get(user, [])
        if not isinstance(funds, list): continue
        for f in funds:
            code = f.get('code', '')
            if code and code in data['fund_charts']:
                target_funds[code] = target_funds.get(code, 0) + 1
    # 归一化
    total = sum(target_funds.values())
    target_weights = {c: w/total for c, w in target_funds.items()}
    print(f"  [A] 跟单基金数: {len(target_funds)}")

    # 回测：每周调仓一次
    start = config['start_date']
    end = config['end_date']
    dates = get_backtest_dates(start, end)
    portfolio = Portfolio(config['initial_cash'])
    portfolio.set_fund_rules(data['fund_rules'])
    portfolio.slippage_pct = config.get('slippage_pct', 0.1)

    last_rebalance = None
    for i, day in enumerate(dates):
        portfolio.settle_pending(day)
        # 周频调仓（每 5 个交易日）
        if last_rebalance is None or i - last_rebalance >= 5:
            _rebalance_to_weights(portfolio, target_weights, day, data)
            last_rebalance = i
        # 记录净值
        prices = {}
        for code in portfolio.holdings:
            pts = data['fund_charts'].get(code, [])
            valid = [p for p in pts if p.get('xAxis', '')[:10] <= day]
            if valid:
                prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
        portfolio.snapshot(day, prices)

    metrics = calc_metrics(portfolio, config['initial_cash'])
    metrics['strategy'] = 'A.集中跟单TOP5'
    metrics['leader_count'] = len(top_leaders)
    metrics['fund_count'] = len(target_funds)
    return metrics


def _rebalance_to_weights(portfolio, target_weights, day, data):
    """调整 portfolio 到目标权重"""
    prices = {}
    for code in target_weights:
        pts = data['fund_charts'].get(code, [])
        valid = [p for p in pts if p.get('xAxis', '')[:10] <= day]
        if valid:
            prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
    total_value = portfolio.value(prices)
    # 卖出所有不符合 target 的
    for code in list(portfolio.holdings.keys()):
        if code not in target_weights:
            h = portfolio.holdings[code]
            sp = prices.get(code, h.get('buy_nav', 1))
            portfolio.sell(code, h['shares'] * sp, sp, day, sell_reason='rebalance_out')
    # 调整每个 target 的权重
    for code, target_w in target_weights.items():
        target_val = total_value * target_w
        sp = prices.get(code, 1)
        if sp <= 0: continue
        current_val = portfolio.holdings.get(code, {}).get('shares', 0) * sp
        diff = target_val - current_val
        if abs(diff) < 100: continue
        if diff > 0:
            # 买
            portfolio.buy(code, data['code_to_name'].get(code, code), diff, price=sp, day_str=day)
        else:
            portfolio.sell(code, -diff, sp, day, sell_reason='rebalance_down')


# ============================================================
# 策略 B: 核心+卫星（50% 板块 + 50% 大佬信号）
# ============================================================
def run_core_satellite(config):
    """50% 按 watchlist 板块固定持有，50% 按大佬信号调仓"""
    data = load_data()
    watchlist = data['watchlist']
    holdings_snapshot = data['holdings_snapshot'].get('holdings', {})

    # 核心仓：watchlist 板块分配 50%
    core_pct = 0.5
    core_weight = {}
    if watchlist:
        sectors = list(watchlist.keys())[:4]  # 取前 4 个板块
        sector_w = core_pct / len(sectors)
        # 板块没有直接映射到基金，需要近似：取板块的关键词在 fund_name 里的
        for sec in sectors:
            keywords = watchlist[sec]
            if isinstance(keywords, list):
                # 没有"us_ai_chip"对应的基金，需要在 273 只里找含科技/AI/纳指/标普 关键词的
                # 简单近似：取包含 keywords[0] 关键词的基金
                k0 = keywords[0] if keywords else ''
                for code, name in data['code_to_name'].items():
                    if k0 in name or k0.replace('_', '') in name:
                        core_weight[code] = sector_w / 5  # 每板块 5 只基金
    # 归一化核心仓
    if core_weight:
        s = sum(core_weight.values())
        core_weight = {c: w/s*core_pct for c, w in core_weight.items()}

    # 卫星仓：从 holdings_snapshot 选 TOP 大佬最新持仓 50%
    sat_pct = 0.5
    sat_funds = {}
    for user, funds in holdings_snapshot.items():
        if not isinstance(funds, list): continue
        for f in funds[:5]:  # 每个大佬取前 5
            code = f.get('code', '')
            if code in data['fund_charts']:
                sat_funds[code] = sat_funds.get(code, 0) + 1
    if sat_funds:
        total = sum(sat_funds.values())
        sat_weight = {c: w/total*sat_pct for c, w in sat_funds.items()}
    else:
        sat_weight = {}

    target_weights = {**core_weight, **sat_weight}
    print(f"  [B] 核心板块 {len(core_weight)} 只基金 + 卫星 {len(sat_weight)} 只基金")

    # 回测：月频调仓
    start = config['start_date']
    end = config['end_date']
    dates = get_backtest_dates(start, end)
    portfolio = Portfolio(config['initial_cash'])
    portfolio.set_fund_rules(data['fund_rules'])
    portfolio.slippage_pct = config.get('slippage_pct', 0.1)

    last_rebalance = None
    for i, day in enumerate(dates):
        portfolio.settle_pending(day)
        if last_rebalance is None or i - last_rebalance >= 20:  # 月频 20 个交易日
            _rebalance_to_weights(portfolio, target_weights, day, data)
            last_rebalance = i
        prices = {}
        for code in portfolio.holdings:
            pts = data['fund_charts'].get(code, [])
            valid = [p for p in pts if p.get('xAxis', '')[:10] <= day]
            if valid:
                prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
        portfolio.snapshot(day, prices)

    metrics = calc_metrics(portfolio, config['initial_cash'])
    metrics['strategy'] = 'B.核心+卫星'
    metrics['core_funds'] = len(core_weight)
    metrics['sat_funds'] = len(sat_weight)
    return metrics


# ============================================================
# 策略 C: 共识重仓股（穿透 top_stocks）
# ============================================================
def run_consensus_stocks(config):
    """从 fund_holdings 抽取共识 TOP 股票，回测用 consensus 基金组合近似"""
    data = load_data()

    # 读取所有 fund_holdings 找共识股票
    stock_freq = Counter()
    for f in CACHE_DIR.glob('fund_holdings_*_latest.json'):
        try:
            h = json.loads(f.read_text(encoding='utf-8'))
            for s in h.get('top_stocks', []):
                code = s.get('code', '')
                if code:
                    stock_freq[code] += 1
        except: pass

    if not stock_freq:
        print("  [C] 无 fund_holdings 数据")
        return None
    # TOP 20 共识股票 → 找持有这些股票最多的基金
    top_stocks = [s for s, _ in stock_freq.most_common(20)]
    # 反向：哪些基金持有这些股票？
    fund_match = {}
    for f in CACHE_DIR.glob('fund_holdings_*_latest.json'):
        try:
            h = json.loads(f.read_text(encoding='utf-8'))
            code = f.stem.replace('fund_holdings_', '').replace('_latest', '')
            matches = sum(1 for s in h.get('top_stocks', []) if s.get('code', '') in top_stocks)
            if matches >= 3:  # 至少持有 3 只共识股
                fund_match[code] = matches
        except: pass
    # 取 TOP 20 共识基金
    target_funds = dict(sorted(fund_match.items(), key=lambda x: x[1], reverse=True)[:20])
    if not target_funds:
        print("  [C] 无共识基金")
        return None
    total = sum(target_funds.values())
    target_weights = {c: w/total for c, w in target_funds.items()}
    print(f"  [C] TOP 20 共识基金, 共识股覆盖 {len(top_stocks)} 只")

    # 季度调仓
    start = config['start_date']
    end = config['end_date']
    dates = get_backtest_dates(start, end)
    portfolio = Portfolio(config['initial_cash'])
    portfolio.set_fund_rules(data['fund_rules'])
    portfolio.slippage_pct = config.get('slippage_pct', 0.1)

    last_rebalance = None
    for i, day in enumerate(dates):
        portfolio.settle_pending(day)
        if last_rebalance is None or i - last_rebalance >= 60:  # 季度 60 个交易日
            _rebalance_to_weights(portfolio, target_weights, day, data)
            last_rebalance = i
        prices = {}
        for code in portfolio.holdings:
            pts = data['fund_charts'].get(code, [])
            valid = [p for p in pts if p.get('xAxis', '')[:10] <= day]
            if valid:
                prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
        portfolio.snapshot(day, prices)

    metrics = calc_metrics(portfolio, config['initial_cash'])
    metrics['strategy'] = 'C.共识重仓股'
    metrics['consensus_stocks'] = len(top_stocks)
    metrics['consensus_funds'] = len(target_funds)
    return metrics


# ============================================================
# 策略 D: 加权共识（按交易金额聚合大佬共识）
# ============================================================
def run_weighted_consensus(config):
    """用 trading_history_fixed 按金额聚合大佬共识基金"""
    data = load_data()
    trades_file = DATA_DIR / 'trading_history_fixed.json'
    if not trades_file.exists():
        print("  [D] 无 trading_history_fixed.json")
        return None

    with open(trades_file, 'r', encoding='utf-8') as f:
        trades = json.load(f)

    # 聚合：每位大佬的净买入金额（买入 - 卖出）作为权重
    name_to_code = data['fund_name_map']
    user_weight = {}  # code → 总净买入金额
    for t in trades:
        fn = t.get('fund_name', '')
        code = name_to_code.get(fn, '')
        if not code: continue
        amt_str = str(t.get('amount', '0')).replace(',', '').replace('元', '')
        try:
            amt = float(amt_str)
        except (ValueError, TypeError):
            continue
        if '买入' in str(t.get('transactionType', t.get('action', ''))):
            user_weight[code] = user_weight.get(code, 0) + amt
        else:
            user_weight[code] = user_weight.get(code, 0) - amt

    # 取 TOP 30 净买入基金
    top_funds = dict(sorted(user_weight.items(), key=lambda x: x[1], reverse=True)[:30])
    top_funds = {c: max(w, 0) for c, w in top_funds.items()}  # 负数置零
    if not top_funds:
        print("  [D] 无共识基金")
        return None
    total = sum(top_funds.values())
    target_weights = {c: w/total for c, w in top_funds.items()}
    print(f"  [D] TOP 30 加权共识基金")

    # 月频调仓
    start = config['start_date']
    end = config['end_date']
    dates = get_backtest_dates(start, end)
    portfolio = Portfolio(config['initial_cash'])
    portfolio.set_fund_rules(data['fund_rules'])
    portfolio.slippage_pct = config.get('slippage_pct', 0.1)

    last_rebalance = None
    for i, day in enumerate(dates):
        portfolio.settle_pending(day)
        if last_rebalance is None or i - last_rebalance >= 20:
            _rebalance_to_weights(portfolio, target_weights, day, data)
            last_rebalance = i
        prices = {}
        for code in portfolio.holdings:
            pts = data['fund_charts'].get(code, [])
            valid = [p for p in pts if p.get('xAxis', '')[:10] <= day]
            if valid:
                prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
        portfolio.snapshot(day, prices)

    metrics = calc_metrics(portfolio, config['initial_cash'])
    metrics['strategy'] = 'D.加权共识'
    metrics['fund_count'] = len(target_funds)
    return metrics




# ============================================================
# 策略 E: 滚动窗口聚合（动态大佬跟单 + 动态排行）
# ============================================================
def _get_r3m_at(pts, day, n=63):
    """计算 day 截止的近 n 日累计收益率%"""
    valid = [p for p in pts if p.get('xAxis','')[:10] <= day]
    if len(valid) < n + 1: return None
    end = (100 + _float(valid[-1].get('yAxis', 0))) / 100
    start = (100 + _float(valid[-n].get('yAxis', 0))) / 100
    if start <= 0: return None
    return (end - start) / start * 100


def _nav_at(code, date, charts):
    """查 code 在 date 当天或之前的最近净值（折算成单位净值 1.0 = 成立时）"""
    pts = charts.get(code, [])
    valid = [p for p in pts if p.get('xAxis','')[:10] <= date]
    if not valid: return None
    return (100 + _float(valid[-1].get('yAxis', 0))) / 100


def _code_of(fn, nm):
    """基金名 → code（带 C/A/D 后缀去除的模糊匹配）"""
    c = nm.get(fn, '')
    if c: return c
    s = re.sub(r'[CAID]$', '', fn)
    return nm.get(s, '')


def _compute_user_history_returns(trading_by_date, days_list, charts, nm, eval_day, lookback_days=365):
    """算每个大佬"历史上所有买入→今日"的加权收益率
    - 仅看 lookback_days 内的买入
    - 用 chart 反推买入日净值、当日净值
    - 份额 = amount / buy_nav
    Returns: {user: (return_rate, total_buy, profit, n_trades, active_in_window)}
    """
    from collections import defaultdict
    user_profit = defaultdict(float)
    user_buy = defaultdict(float)
    user_cnt = defaultdict(int)
    # eval_day 的位置
    if eval_day in days_list:
        eval_idx = days_list.index(eval_day)
    else:
        eval_idx = 0
        for i, d in enumerate(days_list):
            if d > eval_day: break
            eval_idx = i
    start_idx = max(0, eval_idx - lookback_days)
    eval_days = days_list[start_idx:eval_idx + 1]
    for d in eval_days:
        for t in trading_by_date.get(d, []):
            u = t.get('_user', '')
            if not u: continue
            if t.get('action') != '买入': continue
            try:
                amt = float(str(t.get('amount','0')).replace(',','').replace('元',''))
            except (ValueError, TypeError):
                continue
            if amt <= 0: continue
            code = _code_of(t.get('fund_name', ''), nm)
            if not code or code not in charts: continue
            buy_nav = _nav_at(code, d, charts)
            cur_nav = _nav_at(code, eval_day, charts)
            if buy_nav is None or cur_nav is None or buy_nav <= 0: continue
            shares = amt / buy_nav
            cur_val = shares * cur_nav
            user_profit[u] += cur_val - amt
            user_buy[u] += amt
            user_cnt[u] += 1
    # 算收益率
    res = {}
    for u in user_buy:
        if user_buy[u] < 10000: continue  # 至少 1 万
        rate = user_profit[u] / user_buy[u] * 100
        res[u] = (rate, user_buy[u], user_profit[u], user_cnt[u])
    return res


def _compute_dynamic_targets(day, trading_by_date, days_list, data, window=60, top_users=5, top_r3m=20, leader_score_mode='return'):
    """在 day 截止处，按 window 滚动窗口计算跟单目标 + 排行目标，返回 (target_weights, info)

    leader_score_mode:
      'return'   - 按大佬历史综合收益率排名（推荐）
      'netbuy'   - 按窗口内净买入额排名
      'blend'    - 两者各占 50% 标准化加和
    """
    nm = data['fund_name_map']
    charts = data['fund_charts']

    # 1. 窗口内的交易日
    if day in days_list:
        end_idx = days_list.index(day)
    else:
        end_idx = 0
        for i, d in enumerate(days_list):
            if d > day: break
            end_idx = i
    start_idx = max(0, end_idx - window)
    window_days = days_list[start_idx:end_idx + 1]

    # 2. 窗口内 大佬净买入
    from collections import defaultdict, Counter
    user_buy_win = defaultdict(float)
    user_sell_win = defaultdict(float)
    for d in window_days:
        for t in trading_by_date.get(d, []):
            u = t.get('_user', '')
            if not u: continue
            try:
                amt = float(str(t.get('amount','0')).replace(',','').replace('元',''))
            except (ValueError, TypeError):
                continue
            if t.get('action') == '买入':
                user_buy_win[u] += amt
            else:
                user_sell_win[u] += amt
    user_net_win = {u: user_buy_win[u] - user_sell_win.get(u, 0) for u in user_buy_win}
    user_net_win = {u: v for u, v in user_net_win.items() if v > 0}

    # 3. 大佬历史综合收益率（lookback 1 年）
    user_return = _compute_user_history_returns(trading_by_date, days_list, charts, nm, day, lookback_days=365)

    # 4. 窗口内活跃的候选大佬（窗口内净买入>0 且 历史收益率数据可用）
    active_users = set(u for u in user_net_win if u in user_return)
    if not active_users:
        # fallback: 用所有有 return 数据的
        active_users = set(user_return.keys())

    # 5. 给候选大佬打分
    if leader_score_mode == 'return':
        # 纯按收益率
        scored = [(u, user_return[u][0]) for u in active_users]
        scored.sort(key=lambda x: -x[1])
    elif leader_score_mode == 'netbuy':
        scored = [(u, user_net_win.get(u, 0)) for u in active_users]
        scored.sort(key=lambda x: -x[1])
    else:  # blend
        def norm(d, key=lambda x: x[1]):
            if not d: return {}
            vals = [v for _, v in d]
            mn, mx = min(vals), max(vals)
            if mx == mn: return {k: 0.5 for k, _ in d}
            return {k: (v - mn) / (mx - mn) for k, v in d}
        ret_dict = {u: user_return[u][0] for u in active_users}
        nb_dict = {u: user_net_win.get(u, 0) for u in active_users}
        ret_n = norm(list(ret_dict.items()))
        nb_n = norm(list(nb_dict.items()))
        scored = [(u, ret_n.get(u, 0) + nb_n.get(u, 0)) for u in active_users]
        scored.sort(key=lambda x: -x[1])

    top_user_list = scored[:top_users]
    top_user_set = set(u for u, _ in top_user_list)

    # 6. TOP 大佬在窗口内买的基金 -> code
    leader_fund_codes = Counter()
    leader_fund_amt = Counter()
    for d in window_days:
        for t in trading_by_date.get(d, []):
            if t.get('_user') in top_user_set and t.get('action') == '买入':
                code = _code_of(t.get('fund_name', ''), nm)
                if not code or code not in charts: continue
                try: amt = float(str(t.get('amount','0')).replace(',','').replace('元',''))
                except: continue
                leader_fund_codes[code] += 1
                leader_fund_amt[code] += amt

    # 7. 当日 r3m TOP N
    r3m_scores = []
    for code, pts in charts.items():
        r = _get_r3m_at(pts, day, n=63)
        if r is not None:
            r3m_scores.append((code, r))
    r3m_scores.sort(key=lambda x: -x[1])
    rank_codes = [c for c, _ in r3m_scores[:top_r3m]]
    rank_set = set(rank_codes)

    # 8. 融合：交集 x2，并集各 50%
    leader_set = set(leader_fund_codes.keys())
    overlap = leader_set & rank_set
    union = leader_set | rank_set
    target_weights = {}
    for c in union:
        w = 0.0
        if c in leader_set: w += 0.5
        if c in rank_set: w += 0.5
        if c in overlap: w *= 2.0
        target_weights[c] = w
    total = sum(target_weights.values())
    if total > 0:
        target_weights = {c: w/total for c, w in target_weights.items()}

    return target_weights, {
        'top_users': [u for u, _ in top_user_list],
        'top_user_scores': {u: round(s, 2) for u, s in top_user_list},
        'leader_funds': list(leader_set),
        'rank_funds': rank_codes,
        'overlap': list(overlap),
        'union_size': len(union),
    }


def run_dynamic_aggregation(config):
    """策略 E: 滚动窗口聚合动态跟单
    - 每 10 个交易日重新计算目标权重（双周频）
    - 窗口 = 60 个交易日
    - 大佬信号：候选=窗口内净买入>0 的大佬，按"历史综合收益率"排名取 TOP5
    - 排行信号：截止当日 r3m TOP20
    - 共识基金权重 x2
    """
    data = load_data()
    charts = data['fund_charts']
    tbf = json.loads((DATA_DIR / 'trading_by_date_fixed.json').read_text(encoding='utf-8'))

    start = config['start_date']
    end = config['end_date']
    days = get_backtest_dates(start, end)
    days_list = sorted(tbf.keys())

    portfolio = Portfolio(config['initial_cash'])
    portfolio.set_fund_rules(data['fund_rules'])
    portfolio.slippage_pct = config.get('slippage_pct', 0.1)

    rebalance_freq = 10
    leader_mode = config.get('leader_score_mode', 'return')
    last_info = None
    rebalance_count = 0
    for i, day in enumerate(days):
        portfolio.settle_pending(day)
        if i % rebalance_freq == 0:
            target_weights, info = _compute_dynamic_targets(
                day, tbf, days_list, data,
                window=60, top_users=5, top_r3m=20,
                leader_score_mode=leader_mode
            )
            if target_weights:
                _rebalance_to_weights(portfolio, target_weights, day, data)
                last_info = info
                rebalance_count += 1
        prices = {}
        for code in portfolio.holdings:
            pts = charts.get(code, [])
            valid = [p for p in pts if p.get('xAxis','')[:10] <= day]
            if valid:
                prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
        portfolio.snapshot(day, prices)

    metrics = calc_metrics(portfolio, config['initial_cash'])
    metrics['strategy'] = f'E.滚动窗口聚合({leader_mode})'
    metrics['rebalances'] = rebalance_count
    metrics['leader_mode'] = leader_mode
    if last_info:
        metrics['top_users'] = last_info['top_users']
        metrics['top_user_scores'] = last_info['top_user_scores']
        metrics['leader_funds_count'] = len(last_info['leader_funds'])
        metrics['rank_funds_count'] = len(last_info['rank_funds'])
        metrics['overlap_count'] = len(last_info['overlap'])
    return metrics


# ============================================================
# 策略 E2: 核心仓 + 跟单 + 熊市切换（ABC全开）
# ============================================================
def _detect_market_state(charts, day, lookback=20):
    """熊市检测：沪深300 滚动 20 日跌幅 < -5%"""
    pts = sorted([p for p in charts.get('110020', []) if p.get('xAxis','')[:10] <= day],
                 key=lambda x: x['xAxis'])
    if len(pts) < lookback + 1: return 'normal'
    end = (100 + _float(pts[-1].get('yAxis', 0))) / 100
    start = (100 + _float(pts[-lookback].get('yAxis', 0))) / 100
    if start <= 0: return 'normal'
    ret = (end - start) / start * 100
    if ret < -5: return 'bear'
    return 'normal'


def _rebalance_with_threshold(portfolio, target_weights, day, data, threshold=0.2, max_positions=10):
    """带阈值的再平衡：仅当差异 > threshold 或超出 max_positions 才动"""
    prices = {}
    for code in set(list(target_weights.keys()) + list(portfolio.holdings.keys())):
        pts = data['fund_charts'].get(code, [])
        valid = [p for p in pts if p.get('xAxis','')[:10] <= day]
        if valid:
            prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
    total_value = portfolio.value(prices)
    if total_value <= 0: return
    if len(target_weights) > max_positions:
        sorted_w = sorted(target_weights.items(), key=lambda x: -x[1])[:max_positions]
        target_weights = {c: w/sum(v for _, v in sorted_w) for c, w in sorted_w}
    for code in list(portfolio.holdings.keys()):
        h = portfolio.holdings[code]
        sp = prices.get(code, h.get('buy_nav', 1))
        if code not in target_weights:
            portfolio.sell(code, h['shares'] * sp, sp, day, sell_reason='not_in_target')
            continue
        cur_w = (h['shares'] * sp) / total_value
        tgt_w = target_weights[code]
        if abs(cur_w - tgt_w) / max(tgt_w, 0.01) > threshold:
            portfolio.sell(code, h['shares'] * sp, sp, day, sell_reason='threshold_rebalance')
    for code, tgt_w in target_weights.items():
        sp = prices.get(code, 1)
        if sp <= 0: continue
        target_val = total_value * tgt_w
        current_val = portfolio.holdings.get(code, {}).get('shares', 0) * sp
        diff = target_val - current_val
        if abs(diff) < 100: continue
        if diff > 0:
            portfolio.buy(code, data['code_to_name'].get(code, code), diff, price=sp, day_str=day)


def run_dynamic_v2(config):
    """策略 E2: ABC 全开
    - 核心仓 50%（沪深300 60% + 纳指 40%）
    - 跟单池 50%（最多 10 只，月频调，调仓阈值 20%）
    - 熊市切换：核心仓 → 纳指 60% + 货基 40%
    """
    data = load_data()
    charts = data['fund_charts']
    tbf = json.loads((DATA_DIR / 'trading_by_date_fixed.json').read_text(encoding='utf-8'))

    start = config['start_date']
    end = config['end_date']
    days = get_backtest_dates(start, end)
    days_list = sorted(tbf.keys())

    portfolio = Portfolio(config['initial_cash'])
    portfolio.set_fund_rules(data['fund_rules'])
    portfolio.slippage_pct = config.get('slippage_pct', 0.1)

    rebalance_freq = config.get('rebalance_freq', 20)
    leader_mode = config.get('leader_score_mode', 'return')
    core_pct = config.get('core_pct', 0.5)
    max_positions = config.get('max_positions', 10)
    threshold = config.get('rebalance_threshold', 0.2)
    last_info = None
    rebalance_count = 0
    for i, day in enumerate(days):
        portfolio.settle_pending(day)
        if i % rebalance_freq == 0:
            market = _detect_market_state(charts, day)
            # 检查窗口内是否真有交易数据（防 2024-03 前的空信号）
            if day in days_list:
                end_idx = days_list.index(day)
            else:
                end_idx = 0
                for k2, d2 in enumerate(days_list):
                    if d2 > day: break
                    end_idx = k2
            win_start = max(0, end_idx - 60)
            win_days = days_list[win_start:end_idx + 1]
            has_data = sum(len(tbf.get(d, [])) for d in win_days) > 0
            if not has_data:
                # 窗口内无交易数据 → 100% 货基保本
                target_weights = {'004972': 1.0}
                info = {'market': 'no_data', 'top_users': [], 'pool': []}
                _rebalance_with_threshold(portfolio, target_weights, day, data,
                                          threshold=threshold, max_positions=max_positions)
                last_info = info
                rebalance_count += 1
                prices = {}
                for code in portfolio.holdings:
                    pts = charts.get(code, [])
                    valid = [p for p in pts if p.get('xAxis','')[:10] <= day]
                    if valid:
                        prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
                portfolio.snapshot(day, prices)
                continue
            if market == 'bear':
                target_weights = {
                    '270042': core_pct * 0.6,
                    '004972': core_pct * 0.4,
                }
                info = {'market': 'bear', 'top_users': [], 'pool': []}
            else:
                pool, info = _compute_dynamic_targets(
                    day, tbf, days_list, data,
                    window=60, top_users=5, top_r3m=20,
                    leader_score_mode=leader_mode
                )
                if pool:
                    pool_total = sum(pool.values())
                    pool = {c: w * (1 - core_pct) / pool_total for c, w in pool.items()}
                core = {'110020': core_pct * 0.6, '270042': core_pct * 0.4}
                target_weights = {**core, **pool}
                info['market'] = market
            if target_weights:
                _rebalance_with_threshold(portfolio, target_weights, day, data,
                                          threshold=threshold, max_positions=max_positions)
                last_info = info
                rebalance_count += 1
        prices = {}
        for code in portfolio.holdings:
            pts = charts.get(code, [])
            valid = [p for p in pts if p.get('xAxis','')[:10] <= day]
            if valid:
                prices[code] = (100 + _float(valid[-1].get('yAxis', 0))) / 100
        portfolio.snapshot(day, prices)

    metrics = calc_metrics(portfolio, config['initial_cash'])
    metrics['strategy'] = 'E2.核心+跟单+熊市切换'
    metrics['rebalances'] = rebalance_count
    metrics['core_pct'] = core_pct
    metrics['max_positions'] = max_positions
    if last_info:
        metrics['top_users'] = last_info.get('top_users', [])
        metrics['final_market'] = last_info.get('market')
    return metrics


# 延迟导入
from collections import Counter
import re

