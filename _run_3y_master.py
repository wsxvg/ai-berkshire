# -*- coding: utf-8 -*-
"""三年全周期策略对比测试 (2023-07-17 ~ 2026-07-17)
保存 daily_values + 自动切分段 A/B/C + 月胜率 + 信号利用率

用法:
  py -3.10 _run_3y_master.py --batch core      # 策略 1,2,4,4.5
  py -3.10 _run_3y_master.py --batch newparams  # 策略 10,10.5,11,13,14,16
  py -3.10 _run_3y_master.py --batch ml         # 策略 12
  py -3.10 _run_3y_master.py --batch variants   # 策略 15a,15b,15c,17a,17c
  py -3.10 _run_3y_master.py --batch all        # 全部(不含已由regime测试覆盖的3,17,17b)

每个策略约 50 分钟(3年/983天)。结果写入 _results_3y/{batch}.json + .txt
"""
import json, sys, time, os, argparse

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

# ── 基础配置 ──
_cfg = json.load(open('data/evolution/best_config.json', 'r', encoding='utf-8'))
BASE = dict(_cfg.get('config', {}))
BASE['start_date'] = '2023-07-17'
BASE['end_date'] = '2026-07-17'
BASE['initial_cash'] = 100000

# ── 分段定义 ──
SEGMENTS = {
    "A_熊市": ("2023-07-17", "2024-06-30"),
    "B_震荡": ("2024-07-01", "2025-06-30"),
    "C_牛市": ("2025-07-01", "2026-07-17"),
}

# ── 结果输出目录 ──
OUT_DIR = '_results_3y'
os.makedirs(OUT_DIR, exist_ok=True)


# ════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════

def calc_segment_returns(daily_values):
    """从 daily_values 切出段 A/B/C 的收益%"""
    if not daily_values:
        return {k: None for k in SEGMENTS}
    results = {}
    for seg_name, (start, end) in SEGMENTS.items():
        start_val = None
        end_val = None
        for dv in daily_values:
            d = dv['date']
            if start_val is None and d >= start:
                start_val = dv['total']
            if d <= end:
                end_val = dv['total']
            else:
                break
        if start_val and end_val and start_val > 0:
            results[seg_name] = round((end_val / start_val - 1) * 100, 2)
        else:
            results[seg_name] = None
    return results


def calc_monthly_win_rate(daily_values):
    """计算月胜率: 盈利月数/总月数"""
    if not daily_values:
        return 0, 0
    # 取每月最后一个交易日的 total
    monthly = {}
    for dv in daily_values:
        ym = dv['date'][:7]  # "2023-07"
        monthly[ym] = dv['total']  # 后出现的覆盖前面的, 得到月末值
    months = sorted(monthly.keys())
    if len(months) < 2:
        return 0, len(months)
    win = 0
    total = 0
    for i in range(1, len(months)):
        if monthly[months[i]] > monthly[months[i - 1]]:
            win += 1
        total += 1
    return round(win / total * 100, 1) if total > 0 else 0, total


def calc_signal_utilization(result):
    """信号利用率: 有交易的天数/总有信号的天数"""
    trades = result.get('trades', [])
    scores = result.get('scores', [])
    trade_days = set()
    for t in trades:
        if 'buy_date' in t:
            trade_days.add(t['buy_date'])
        elif 'date' in t:
            trade_days.add(t['date'])
    score_days = set()
    for s in scores:
        if 'date' in s:
            score_days.add(s['date'])
    if not score_days:
        return 0
    return round(len(trade_days) / len(score_days) * 100, 1)


def run_one(label, config):
    """跑单个策略, 返回汇总dict"""
    print(f'=== {label} ===', flush=True)
    t0 = time.time()
    r = run_backtest(config)
    elapsed = time.time() - t0

    ret = r.get('total_return', 0)
    dd = r.get('max_drawdown', 0)
    tc = r.get('trade_count', 0)
    sharpe = r.get('sharpe_ratio', 0)
    calmar = r.get('calmar_ratio', 0)
    ann = r.get('annualized_return', 0)
    vol = r.get('annualized_volatility', 0)
    fees = r.get('total_fees', 0)

    dv = r.get('daily_values', [])
    seg = calc_segment_returns(dv)
    win_rate, total_months = calc_monthly_win_rate(dv)
    sig_util = calc_signal_utilization(r)

    summary = {
        "label": label,
        "total_return": round(ret, 2),
        "max_drawdown": round(dd, 2),
        "trade_count": tc,
        "sharpe": sharpe,
        "calmar": calmar,
        "annualized": ann,
        "volatility": vol,
        "fees": fees,
        "segments": seg,
        "monthly_win_rate": win_rate,
        "total_months": total_months,
        "signal_utilization": sig_util,
        "time_seconds": round(elapsed, 0),
        "final_value": r.get('final_value', 0),
    }

    seg_str = "  ".join(f"{k}={v}%" if v is not None else f"{k}=N/A"
                        for k, v in seg.items())
    print(f'  收益: {ret:.2f}%  回撤: {dd:.2f}%  交易: {tc}笔  夏普: {sharpe}  卡玛: {calmar}', flush=True)
    print(f'  分段: {seg_str}', flush=True)
    print(f'  月胜率: {win_rate}% ({total_months}月)  信号利用: {sig_util}%  耗时: {elapsed:.0f}s', flush=True)
    print(flush=True)
    return summary


def save_results(batch, results):
    """保存结果到 JSON + TXT"""
    json_path = os.path.join(OUT_DIR, f'{batch}.json')
    txt_path = os.path.join(OUT_DIR, f'{batch}.txt')

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f'三年全周期策略对比 — 批次: {batch}\n')
        f.write(f'数据期: 2023-07-17 ~ 2026-07-17 | initial_cash=100,000\n')
        f.write(f'生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write('=' * 80 + '\n\n')
        for s in results:
            if 'error' in s:
                f.write(f'=== {s["label"]} ===\n  ERROR: {s["error"]}\n\n')
                continue
            seg = s.get("segments", {})
            a = seg.get("A_熊市")
            b = seg.get("B_震荡")
            c = seg.get("C_牛市")
            f.write(f'=== {s["label"]} ===\n')
            f.write(f'  全周期收益: {s["total_return"]:.2f}%  回撤: {s["max_drawdown"]:.2f}%  '
                    f'交易: {s["trade_count"]}笔  夏普: {s["sharpe"]}  卡玛: {s["calmar"]}\n')
            f.write(f'  段A(熊市): {a if a is not None else "N/A"}%  '
                    f'段B(震荡): {b if b is not None else "N/A"}%  '
                    f'段C(牛市): {c if c is not None else "N/A"}%\n')
            f.write(f'  月胜率: {s["monthly_win_rate"]}%  信号利用: {s["signal_utilization"]}%  '
                    f'耗时: {s["time_seconds"]:.0f}s\n\n')
        # 汇总排名表
        f.write('=' * 80 + '\n')
        f.write('汇总排名表\n')
        f.write('=' * 80 + '\n')
        f.write(f'{"策略":<35} {"全周期":>8} {"段A":>8} {"段B":>8} {"段C":>8} '
               f'{"回撤":>6} {"月胜率":>6} {"夏普":>5} {"卡玛":>5}\n')
        f.write('-' * 100 + '\n')
        for s in sorted(results, key=lambda x: x.get('total_return', -999), reverse=True):
            if 'error' in s:
                f.write(f'{s["label"]:<35} ERROR: {s["error"][:30]}\n')
                continue
            seg = s.get("segments", {})
            a = seg.get("A_熊市")
            b = seg.get("B_震荡")
            c = seg.get("C_牛市")
            f.write(f'{s["label"]:<35} {s["total_return"]:>7.2f}% '
                    f'{str(a) if a is not None else "—":>7}% {str(b) if b is not None else "—":>7}% '
                    f'{str(c) if c is not None else "—":>7}% {s["max_drawdown"]:>5.1f}% '
                    f'{s["monthly_win_rate"]:>5}% {s["sharpe"]:>5} {s["calmar"]:>5}\n')

    print(f'[已保存] {json_path} + {txt_path}', flush=True)


# ════════════════════════════════════════════════
#  策略定义 (19个, 不含已由 _test_regime_3y.py 覆盖的 3,17,17b)
# ════════════════════════════════════════════════

STRATEGIES = {
    # ── 批次: core (核心基线对比) ──
    "策略1_K_baseline": dict(BASE,
        min_score=0, min_consensus=2,
        fund_type_filter='all', exclude_uids=[],
        max_sector_pct=100, max_qdii_pct=100,
        dynamic_stop_loss=False, pyramiding_enabled=False),

    "策略2_Champion": dict(BASE,
        dynamic_stop_loss=False, pyramiding_enabled=False),

    "策略4_Champion+pyramid": dict(BASE,
        dynamic_stop_loss=False, pyramiding_enabled=True),

    "策略4.5_Champion+pyramid+dynSL": dict(BASE,
        pyramiding_enabled=True),

    # ── 批次: newparams (新参数, 从未测试) ──
    "策略10_PE过滤": dict(BASE,
        sector_valuation=True),

    "策略10.5_PE+pyramid": dict(BASE,
        sector_valuation=True, pyramiding_enabled=True),

    "策略11_RSI拦截": dict(BASE,
        timing_filter=True, block_overbought=True),

    "策略13_移动止盈": dict(BASE,
        trailing_tp_activate=15, trailing_tp_drawdown=8),

    "策略14_熊市不买": dict(BASE,
        bear_market_no_buy=True),

    "策略16_大佬卖出跟单": dict(BASE,
        sell_consensus=2),

    # ── 批次: ml (机器学习) ──
    "策略12_ML信号": dict(BASE,
        ml_signal=True, ml_weight=1.0, ml_retrain_days=30),

    # ── 批次: variants (凯利变体 + regime变体) ──
    "策略15a_kelly0.25": dict(BASE, kelly_cap=0.25),
    "策略15b_kelly0.30": dict(BASE, kelly_cap=0.30),
    "策略15c_kelly0.35": dict(BASE, kelly_cap=0.35),

    "策略17a_regime保守": dict(BASE, regime_specific=True,
        take_profit_pct_bull=50, take_profit_pct_neutral=40, take_profit_pct_bear=20,
        stop_loss_pct_bull=-25, stop_loss_pct_neutral=-30, stop_loss_pct_bear=-15,
        kelly_cap_bull=0.20, kelly_cap_neutral=0.15, kelly_cap_bear=0.05,
        pyramiding_enabled_bull=False, pyramiding_enabled_neutral=False, pyramiding_enabled_bear=True,
        trailing_tp_activate_bull=25, trailing_tp_activate_neutral=20, trailing_tp_activate_bear=8,
        trailing_tp_drawdown_bull=10, trailing_tp_drawdown_neutral=10, trailing_tp_drawdown_bear=6),

    "策略17c_regime仅牛熊": dict(BASE, regime_specific=True,
        take_profit_pct_bull=60, take_profit_pct_bear=25,
        stop_loss_pct_bear=-15,
        kelly_cap_bull=0.30, kelly_cap_bear=0.08,
        pyramiding_enabled_bull=False, pyramiding_enabled_bear=True),
    # 17c 震荡不设参数, _rc() 回退到通用值

    # ── 批次: regime_recover (补跑策略3,17,17b的分段数据) ──
    "策略3_Champion+dynSL": dict(BASE),  # base 本身就是策略3

    "策略17_regime默认": dict(BASE, regime_specific=True,
        take_profit_pct_bull=60, take_profit_pct_neutral=50, take_profit_pct_bear=30,
        stop_loss_pct_bull=-25, stop_loss_pct_neutral=-30, stop_loss_pct_bear=-20,
        kelly_cap_bull=0.25, kelly_cap_neutral=0.20, kelly_cap_bear=0.10,
        pyramiding_enabled_bull=False, pyramiding_enabled_neutral=False, pyramiding_enabled_bear=True,
        trailing_tp_activate_bull=20, trailing_tp_activate_neutral=15, trailing_tp_activate_bear=10,
        trailing_tp_drawdown_bull=8, trailing_tp_drawdown_neutral=10, trailing_tp_drawdown_bear=6),

    "策略17b_regime激进": dict(BASE, regime_specific=True,
        take_profit_pct_bull=80, take_profit_pct_neutral=60, take_profit_pct_bear=40,
        stop_loss_pct_bull=-30, stop_loss_pct_neutral=-25, stop_loss_pct_bear=-25,
        kelly_cap_bull=0.35, kelly_cap_neutral=0.25, kelly_cap_bear=0.15,
        pyramiding_enabled_bull=False, pyramiding_enabled_neutral=False, pyramiding_enabled_bear=True,
        trailing_tp_activate_bull=15, trailing_tp_activate_neutral=12, trailing_tp_activate_bear=8,
        trailing_tp_drawdown_bull=10, trailing_tp_drawdown_neutral=8, trailing_tp_drawdown_bear=6),

    # ── 批次: longcycle (长周期辅助策略，需先选出baseline再加参数) ──
    # 策略18-21 用 baseline 配置 + 长周期参数对跑
    # baseline 会从 _results_3y 最优策略动态读取，这里先用 BASE 作为占位
    "策略18_周线MACD背离": dict(BASE,
        weekly_macd_divergence=True),

    "策略19_年线牛熊过滤": dict(BASE,
        yearly_ma_filter=True),

    "策略20_周线布林带仓位": dict(BASE,
        weekly_bollinger_adjust=True),

    "策略21_三合一": dict(BASE,
        weekly_macd_divergence=True,
        yearly_ma_filter=True,
        weekly_bollinger_adjust=True),
}

BATCH_MAP = {
    "core": ["策略1_K_baseline", "策略2_Champion", "策略4_Champion+pyramid", "策略4.5_Champion+pyramid+dynSL"],
    "newparams": ["策略10_PE过滤", "策略10.5_PE+pyramid", "策略11_RSI拦截",
                  "策略13_移动止盈", "策略14_熊市不买", "策略16_大佬卖出跟单"],
    "ml": ["策略12_ML信号"],
    "variants": ["策略15a_kelly0.25", "策略15b_kelly0.30", "策略15c_kelly0.35",
                 "策略17a_regime保守", "策略17c_regime仅牛熊"],
    "regime_recover": ["策略3_Champion+dynSL", "策略17_regime默认", "策略17b_regime激进"],
    "longcycle": ["策略18_周线MACD背离", "策略19_年线牛熊过滤", "策略20_周线布林带仓位", "策略21_三合一"],
    "all": list(STRATEGIES.keys()),
}


def main():
    parser = argparse.ArgumentParser(description='三年全周期策略对比测试')
    parser.add_argument('--batch', required=True, choices=list(BATCH_MAP.keys()),
                        help='批次名称')
    args = parser.parse_args()

    labels = BATCH_MAP[args.batch]
    print(f'三年全周期策略对比 — 批次: {args.batch}', flush=True)
    print(f'策略数: {len(labels)}  数据期: 2023-07-17 ~ 2026-07-17', flush=True)
    print(f'策略列表: {labels}', flush=True)
    print('=' * 80, flush=True)

    # 加载已有结果(支持断点续跑)
    json_path = os.path.join(OUT_DIR, f'{args.batch}.json')
    results = []
    done_labels = set()
    if os.path.exists(json_path):
        try:
            results = json.load(open(json_path, 'r', encoding='utf-8'))
            done_labels = {r['label'] for r in results}
            print(f'[断点续跑] 已完成 {len(done_labels)} 个: {done_labels}', flush=True)
        except Exception:
            pass

    for label in labels:
        if label in done_labels:
            print(f'[跳过] {label} (已完成)', flush=True)
            continue
        cfg = STRATEGIES[label]
        try:
            s = run_one(label, cfg)
            results.append(s)
            save_results(args.batch, results)  # 每跑完一个立即保存
        except Exception as e:
            print(f'[错误] {label}: {e}', flush=True)
            import traceback
            traceback.print_exc()
            results.append({"label": label, "error": str(e)})
            save_results(args.batch, results)

    save_results(args.batch, results)
    print('\n=== 全部完成 ===', flush=True)
    for s in sorted(results, key=lambda x: x.get('total_return', -999), reverse=True):
        if 'error' in s:
            print(f'  {s["label"]}: ERROR', flush=True)
        else:
            seg = s.get("segments", {})
            print(f'  {s["label"]}: {s["total_return"]:.2f}%  '
                  f'A={seg.get("A_熊市","?")}% B={seg.get("B_震荡","?")}% C={seg.get("C_牛市","?")}%  '
                  f'回撤{s["max_drawdown"]:.1f}%  夏普{s["sharpe"]}', flush=True)


if __name__ == '__main__':
    main()
