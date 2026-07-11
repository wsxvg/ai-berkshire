#!/usr/bin/env python3
"""系统化回测参数优化器 — 顺序执行 + 分阶段搜索"""
import sys, json, os, time, itertools
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BACKTEST_RESULTS = Path(PROJECT_ROOT) / "backtest" / "reports"

BASE_CONFIG = {
    "start_date": "2026-01-05",
    "end_date": "2026-06-30",
    "initial_cash": 100000,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "cost_penalty": 0, "top_n": 0, "top_n_pct": 0, "consensus_priority": False,
    "limit_boost": 0, "rebalance": True,
    "ranking_window": 90, "ranking_fwd_days": 30,
    "ranking_min_buys": 5, "ranking_recalc_days": 30,
    "verbose_ranking": False,
    "fund_type_filter": "all", "sell_consensus": 0, "no_stop_loss": False,
}

def make_config(**kw):
    c = dict(BASE_CONFIG)
    c.update(kw)
    return c

def run_one(label, cfg, quiet=True):
    """Run one backtest and return metrics"""
    try:
        # Suppress print from backtest engine
        if quiet:
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

        from backtest.engine.backtest import run_backtest
        result = run_backtest(cfg)

        if quiet:
            sys.stdout = old_stdout

        tr = float(result.get("total_return", 0))
        dd = float(result.get("max_drawdown", 0))
        bm = float(result.get("benchmark_return", 0))
        trades = int(result.get("trade_count", 0))
        final_val = float(result.get("final_value", 0))
        fees = float(result.get("total_fees", 0))
        bh = float(result.get("buyhold_return", 0))
        holdings = int(result.get("final_holdings", 0))
        calmar = tr / max(dd, 0.01)
        return {
            "label": label,
            "total_return": tr, "max_drawdown": dd,
            "benchmark": bm, "excess": tr - bm,
            "buyhold": bh, "trades": trades,
            "final_value": final_val, "fees": fees,
            "final_holdings": holdings, "calmar": calmar,
            "config": {k: v for k, v in cfg.items() if not isinstance(v, dict)},
            "weights": cfg.get("weights", {}),
        }
    except Exception as e:
        if quiet:
            sys.stdout = old_stdout
        print(f"  ERROR [{label}]: {e}")
        return {"label": label, "error": str(e)}

def print_result(r):
    if r.get("error"):
        return f"  ERROR: {r['error']}"
    return (f"  Return: {r['total_return']:>+7.2f}% | "
            f"DD: {r['max_drawdown']:>5.1f}% | "
            f"Excess: {r['excess']:>+7.2f}% | "
            f"Trades: {r['trades']:3d} | "
            f"Holding: {r.get('final_holdings',0):2d} | "
            f"Calmar: {r['calmar']:>5.2f} | "
            f"{r['label']}")


def main():
    print("=" * 70)
    print("系统化回测参数优化器 · 尽最大努力搜索最大收益率")
    print("=" * 70)

    all_results = []
    start_time = time.time()

    # ── PHASE 1: Core threshold scan ──
    print("\n[Phase 1] 核心阈值扫描: min_score × min_consensus × take_profit × stop_loss")
    print("-" * 70)

    phase1_params = []
    for ms in [1.5, 2.0, 2.5, 3.0]:
        for mc in [1, 2]:
            for tp in [10, 20, 50]:
                for sl in [-5, -15, -50]:
                    phase1_params.append((ms, mc, tp, sl))

    for i, (ms, mc, tp, sl) in enumerate(phase1_params):
        label = f"1_{ms}_{mc}_{tp}_{abs(sl)}"
        cfg = make_config(min_score=ms, min_consensus=mc,
                          take_profit_pct=tp, stop_loss_pct=sl,
                          momentum_sell=1.0, kelly_cap=0.5,
                          cash_reserve_pct=0.10, max_position_pct=40,
                          max_holdings=8, max_sector_pct=50, max_qdii_pct=50,
                          dynamic_ranking=True, profit_mode="half",
                          monthly_injection=10000)
        r = run_one(label, cfg)
        all_results.append(r)
        print(f"  [{i+1:2d}/{len(phase1_params)}] {print_result(r)}")

    # Phase 1 results
    good = [r for r in all_results if not r.get("error")]
    good.sort(key=lambda x: -x["total_return"])
    print(f"\n--- Phase 1 Best (top 5) ---")
    for r in good[:5]:
        print(print_result(r))

    # ── PHASE 2: Fine tune around best ──
    if good:
        best = good[0]
        b_ms = best["config"]["min_score"]
        b_mc = best["config"]["min_consensus"]
        b_tp = best["config"]["take_profit_pct"]
        b_sl = best["config"]["stop_loss_pct"]

        print(f"\n[Phase 2] 精调: momentum_sell × kelly_cap × cash_reserve × max_position")
        print(f"  固定: ms={b_ms}, mc={b_mc}, tp={b_tp}, sl={b_sl}")
        print("-" * 70)

        phase2_params = []
        for mom in [0.5, 1.0, 1.5, 2.0, 3.0]:
            for kc in [0.2, 0.3, 0.5, 0.7]:
                for cr in [0.05, 0.10, 0.15, 0.20]:
                    for mp in [20, 30, 40, 60]:
                        phase2_params.append((mom, kc, cr, mp))

        for i, (mom, kc, cr, mp) in enumerate(phase2_params):
            label = f"2_{mom}_{kc}_{cr}_{mp}"
            cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                              take_profit_pct=b_tp, stop_loss_pct=b_sl,
                              momentum_sell=mom, kelly_cap=kc,
                              cash_reserve_pct=cr, max_position_pct=mp,
                              max_holdings=8, max_sector_pct=50, max_qdii_pct=50,
                              dynamic_ranking=True, profit_mode="half",
                              monthly_injection=10000)
            r = run_one(label, cfg)
            all_results.append(r)
            if (i+1) % 20 == 0:
                print(f"  [{i+1:3d}/{len(phase2_params)}] best so far: {max([x['total_return'] for x in all_results if not x.get('error')], default=0):+.2f}%")

        good = [r for r in all_results if not r.get("error")]
        good.sort(key=lambda x: -x["total_return"])
        print(f"\n--- Phase 2 Best (top 5) ---")
        for r in good[:5]:
            print(print_result(r))

        # ── PHASE 3: Extreme + fine details ──
        best = good[0]
        b_ms = best["config"]["min_score"]
        b_mc = best["config"]["min_consensus"]
        b_tp = best["config"]["take_profit_pct"]
        b_sl = best["config"]["stop_loss_pct"]
        b_mom = best["config"]["momentum_sell"]
        b_kc = best["config"]["kelly_cap"]
        b_cr = best["config"]["cash_reserve_pct"]
        b_mp = best["config"]["max_position_pct"]

        print(f"\n[Phase 3] 极端配置 + 细节优化")
        print(f"  基于: ms={b_ms}, mc={b_mc}, tp={b_tp}, sl={b_sl}, "
              f"mom={b_mom}, kc={b_kc}, cr={b_cr}, mp={b_mp}")
        print("-" * 70)

        # Profit modes
        for pm in ["half", "all", "quarter", "step"]:
            label = f"3_pm_{pm}"
            cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                              take_profit_pct=b_tp, stop_loss_pct=b_sl,
                              momentum_sell=b_mom, kelly_cap=b_kc,
                              cash_reserve_pct=b_cr, max_position_pct=b_mp,
                              max_holdings=8, max_sector_pct=50, max_qdii_pct=50,
                              dynamic_ranking=True, profit_mode=pm,
                              monthly_injection=10000)
            r = run_one(label, cfg)
            all_results.append(r)
            print(f"  {print_result(r)}")

        # Max holdings
        for mh in [2, 3, 5, 10, 20, 0]:
            label = f"3_mh_{mh}"
            cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                              take_profit_pct=b_tp, stop_loss_pct=b_sl,
                              momentum_sell=b_mom, kelly_cap=b_kc,
                              cash_reserve_pct=b_cr, max_position_pct=b_mp,
                              max_holdings=mh, max_sector_pct=50, max_qdii_pct=50,
                              dynamic_ranking=True, profit_mode="half",
                              monthly_injection=10000)
            r = run_one(label, cfg)
            all_results.append(r)
            print(f"  {print_result(r)}")

        # Monthly injection
        for inj in [0, 5000, 15000, 20000, 50000]:
            label = f"3_inj_{inj}"
            cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                              take_profit_pct=b_tp, stop_loss_pct=b_sl,
                              momentum_sell=b_mom, kelly_cap=b_kc,
                              cash_reserve_pct=b_cr, max_position_pct=b_mp,
                              max_holdings=8, max_sector_pct=50, max_qdii_pct=50,
                              dynamic_ranking=True, profit_mode="half",
                              monthly_injection=inj)
            r = run_one(label, cfg)
            all_results.append(r)
            print(f"  {print_result(r)}")

        # Sector limits
        for sp, qp in [(20, 20), (30, 30), (50, 50), (100, 100)]:
            label = f"3_sp{sp}_qp{qp}"
            cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                              take_profit_pct=b_tp, stop_loss_pct=b_sl,
                              momentum_sell=b_mom, kelly_cap=b_kc,
                              cash_reserve_pct=b_cr, max_position_pct=b_mp,
                              max_holdings=8, max_sector_pct=sp, max_qdii_pct=qp,
                              dynamic_ranking=True, profit_mode="half",
                              monthly_injection=10000)
            r = run_one(label, cfg)
            all_results.append(r)
            print(f"  {print_result(r)}")

        # Special flags
        for ns, uw, nets, tag in [
            (True, False, False, "noSL"),
            (False, True, False, "weighted"),
            (False, False, True, "netSig"),
            (True, True, False, "noSL_wei"),
            (False, True, True, "wei_net"),
            (True, False, True, "noSL_net"),
            (False, False, False, "baseline"),
        ]:
            label = f"3_flag_{tag}"
            cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                              take_profit_pct=b_tp, stop_loss_pct=b_sl,
                              momentum_sell=b_mom, kelly_cap=b_kc,
                              cash_reserve_pct=b_cr, max_position_pct=b_mp,
                              max_holdings=8, max_sector_pct=50, max_qdii_pct=50,
                              dynamic_ranking=True, profit_mode="half",
                              monthly_injection=10000, no_stop_loss=ns,
                              use_weighted_consensus=uw)
            cfg["net_signal"] = nets
            r = run_one(label, cfg)
            all_results.append(r)
            print(f"  {print_result(r)}")

        # Dynamic ranking on/off
        label = "3_dr_False"
        cfg = make_config(min_score=b_ms, min_consensus=b_mc,
                          take_profit_pct=b_tp, stop_loss_pct=b_sl,
                          momentum_sell=b_mom, kelly_cap=b_kc,
                          cash_reserve_pct=b_cr, max_position_pct=b_mp,
                          max_holdings=8, max_sector_pct=50, max_qdii_pct=50,
                          dynamic_ranking=False, profit_mode="half",
                          monthly_injection=10000)
        r = run_one(label, cfg)
        all_results.append(r)
        print(f"  {print_result(r)}")

    # ── FINAL ──
    good = [r for r in all_results if not r.get("error")]
    good.sort(key=lambda x: -x["total_return"])

    print("\n" + "=" * 70)
    print("🏆 最终排名 TOP 10（按总收益率）")
    print("=" * 70)
    for i, r in enumerate(good[:10]):
        print(f"\n  #{i+1}: {r['label']}")
        print(f"      总收益率: {r['total_return']:>+7.2f}%")
        print(f"      最大回撤: {r['max_drawdown']:>5.1f}%")
        print(f"      基准收益: {r['benchmark']:>+7.2f}%")
        print(f"      超额收益: {r['excess']:>+7.2f}%")
        print(f"      交易次数: {r['trades']}")
        print(f"      最终持仓: {r.get('final_holdings', 0)}")
        print(f"      最终价值: ¥{r['final_value']:,.0f}")
        print(f"      总手续费: ¥{r.get('fees', 0):,.0f}")
        print(f"      Calmar比: {r['calmar']:.2f}")

    # By Calmar
    by_calmar = sorted(good, key=lambda x: -x["calmar"])
    print(f"\n{'='*70}")
    print("🏆 TOP 10 BY CALMAR（风险调整后）")
    print("=" * 70)
    for i, r in enumerate(by_calmar[:10]):
        print(f"  #{i+1}: Return: {r['total_return']:>+7.2f}% | "
              f"DD: {r['max_drawdown']:>5.1f}% | Calmar: {r['calmar']:.2f} | "
              f"Trades: {r['trades']:3d} | {r['label']}")

    # Save
    if good:
        best = good[0]
        output = {
            "best_total_return": best["total_return"],
            "best_drawdown": best["max_drawdown"],
            "best_excess": best["excess"],
            "best_trades": best["trades"],
            "best_config": best.get("config", {}),
            "best_weights": best.get("weights", {}),
            "top10": [{k: v for k, v in r.items() if k not in ('config', 'weights')}
                     for r in good[:10]],
            "top10_calmar": [{k: v for k, v in r.items() if k not in ('config', 'weights')}
                           for r in by_calmar[:10]],
            "total_tested": len(good),
            "total_time": time.time() - start_time,
        }
        out_path = BACKTEST_RESULTS / "optimization_results.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {out_path}")
    else:
        print("\n所有配置均失败!")

    total_time = time.time() - start_time
    print(f"总耗时: {total_time:.0f}s ({total_time/60:.1f}分钟)")


if __name__ == "__main__":
    main()