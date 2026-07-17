"""
SKILL A/B 实验 V3 (8 组对照) - 2026-07-13
=========================================
A0: V2 baseline (P1 止盈, 无 SKILL)
B1: + RSI 拦截
B2: + 集中度过滤
B3: + 经理筛选
B4: + 5 维评分门槛 (修复后)
B5: + 评分仓位调节
B6: B1+B2+B3 组合 (排除型)
B7: B1+B4 组合 (拦截型)

每组跑 full/train/val 3 段, 输出 JSON 报告
"""
import sys, json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"C:\项目\A基金\基金")
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

# 强制 reload
import importlib
if "backtest_v2" in sys.modules:
    importlib.reload(sys.modules["backtest_v2"])
from backtest_v2 import run_backtest

OUT = PROJECT_ROOT / "reports" / "skill_ab_test"
OUT.mkdir(parents=True, exist_ok=True)


def run_exp(name, **overrides):
    base = dict(
        start="2024-03-11", end="2026-07-01", initial_cash=100000,
        max_holdings=3, min_buyers=1,
        use_tp=True, use_trail=True, use_time_tp=True,
        use_dynamic=False, use_scorer=False,
        tp_pct=15.0, trail_pct=8.0, hold_days=60,
    )
    base.update(overrides)

    def call(s, e):
        return run_backtest(
            start_date=s, end_date=e, initial_cash=base["initial_cash"],
            max_holdings=base["max_holdings"], min_buyers=base["min_buyers"],
            use_tp=base["use_tp"], use_trail=base["use_trail"],
            use_time_tp=base["use_time_tp"], use_dynamic=base["use_dynamic"],
            use_scorer=base["use_scorer"],
            tp_pct=base["tp_pct"], trail_pct=base["trail_pct"],
            hold_days=base["hold_days"],
            # SKILL 参数
            use_rsi_filter=base.get("use_rsi_filter", False),
            rsi_threshold=base.get("rsi_threshold", 75),
            use_concentration_filter=base.get("use_concentration_filter", False),
            concentration_max=base.get("concentration_max", 0.6),
            use_manager_filter=base.get("use_manager_filter", False),
            min_tenure_years=base.get("min_tenure_years", 1.0),
            use_score_threshold=base.get("use_score_threshold", False),
            score_threshold=base.get("score_threshold", 3.0),
            use_score_position=base.get("use_score_position", False),
        )

    r_full = call(base["start"], base["end"])
    r_tr = call("2024-03-11", "2026-03-11")
    r_vl = call("2026-03-11", "2026-07-01")

    def sumr(r, period):
        if not r: return {"period": period, "annualized": 0, "sharpe": 0,
                          "max_drawdown": 0, "win_rate": 0, "n_buys": 0,
                          "n_sells": 0, "alpha": 0}
        x = r["result"]
        return {
            "period": period,
            "annualized": round(x["annualized"], 2),
            "sharpe": round(x["sharpe"], 2),
            "max_drawdown": round(x["max_drawdown"], 2),
            "win_rate": round(x["win_rate"], 1),
            "n_buys": x["n_buys"],
            "n_sells": x["n_sells"],
            "alpha": round(x["alpha"], 2),
        }

    return {
        "name": name,
        "config": {k: v for k, v in base.items() if k != "initial_cash"},
        "full": sumr(r_full, "full"),
        "train": sumr(r_tr, "train"),
        "val": sumr(r_vl, "val"),
    }


EXPERIMENTS = [
    # ── A0: V2 baseline ──
    {"name": "A0_V2_baseline", "desc": "V2 baseline (P1 止盈, 无 SKILL)", "kwargs": {}},

    # ── B1: RSI 拦截 (避免追高) ──
    {"name": "B1_RSI_75", "desc": "+ RSI>75 不买 (防追高)", "kwargs": {
        "use_rsi_filter": True, "rsi_threshold": 75,
    }},
    {"name": "B1b_RSI_80", "desc": "+ RSI>80 不买 (更严)", "kwargs": {
        "use_rsi_filter": True, "rsi_threshold": 80,
    }},

    # ── B2: 集中度过滤 (行业集中度>60% 减仓) ──
    {"name": "B2_concentration_60", "desc": "+ 持仓行业集中度>60% 减仓", "kwargs": {
        "use_concentration_filter": True, "concentration_max": 0.6,
    }},

    # ── B3: 经理筛选 (经理<1年不买) ──
    {"name": "B3_manager_1y", "desc": "+ 经理任职<1年 不买", "kwargs": {
        "use_manager_filter": True, "min_tenure_years": 1.0,
    }},
    {"name": "B3b_manager_2y", "desc": "+ 经理任职<2年 不买 (更严)", "kwargs": {
        "use_manager_filter": True, "min_tenure_years": 2.0,
    }},

    # ── B4: 5 维评分门槛 (修复后) ──
    {"name": "B4_score_12.5", "desc": "+ score<12.5 不买 (中性门槛)", "kwargs": {
        "use_score_threshold": True, "score_threshold": 12.5,
    }},
    {"name": "B4b_score_15.0", "desc": "+ score<15.0 不买 (高质量)", "kwargs": {
        "use_score_threshold": True, "score_threshold": 15.0,
    }},

    # ── B5: 评分仓位调节 ──
    {"name": "B5_score_position", "desc": "+ 评分做仓位调节 (score高多买)", "kwargs": {
        "use_score_position": True,
    }},

    # ── B6: 排除型组合 (B1+B2+B3) ──
    {"name": "B6_filter_combo", "desc": "B1+B2+B3 三层过滤", "kwargs": {
        "use_rsi_filter": True, "rsi_threshold": 75,
        "use_concentration_filter": True, "concentration_max": 0.6,
        "use_manager_filter": True, "min_tenure_years": 1.0,
    }},

    # ── B7: 拦截型组合 (B1+B4) ──
    {"name": "B7_RSI_score", "desc": "B1 RSI + B4 评分门槛", "kwargs": {
        "use_rsi_filter": True, "rsi_threshold": 75,
        "use_score_threshold": True, "score_threshold": 12.5,
    }},
]


def main():
    results = []
    print(f"SKILL A/B V3 - {len(EXPERIMENTS)} 组实验")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 70)

    for exp in EXPERIMENTS:
        print(f"\n>>> {exp['name']}: {exp['desc']}")
        try:
            r = run_exp(exp["name"], **exp["kwargs"])
            r["desc"] = exp["desc"]
            results.append(r)
            f, v = r["full"], r["val"]
            print(f"  Full: 年化 {f['annualized']:+.2f}% | 夏普 {f['sharpe']:.2f} | "
                  f"回撤 {f['max_drawdown']:+.2f}% | 胜率 {f['win_rate']:.1f}% | "
                  f"买/卖 {f['n_buys']}/{f['n_sells']} | Alpha {f['alpha']:+.2f}%")
            print(f"  Val:  年化 {v['annualized']:+.2f}% | 夏普 {v['sharpe']:.2f} | "
                  f"回撤 {v['max_drawdown']:+.2f}% | 胜率 {v['win_rate']:.1f}%")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            results.append({"name": exp["name"], "desc": exp["desc"], "error": str(e)})

    out_file = OUT / f"skill_ab_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"experiments": results, "ts": datetime.now().isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"\n\n保存: {out_file}")
    return out_file


if __name__ == "__main__":
    main()
