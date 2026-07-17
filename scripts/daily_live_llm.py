#!/usr/bin/env python3
"""LLM 混合模式旁路实验 — 机器出 TOP5 + LLM 否决

设计:
1. 复制 daily_live.py 的核心逻辑
2. 在买入前插入 LLM 否决步骤
3. LLM 只能从 TOP5 候选中剔除, 不能加新
4. 跑完后对比纯机器 baseline 的收益差异
"""
import json, sys, os, glob, argparse
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--simulate-date", default=None)
_args, _ = _ap.parse_known_args()

if _args.simulate_date:
    _dt = datetime.strptime(_args.simulate_date, "%Y-%m-%d")
else:
    _dt = datetime.now()

TODAY = _dt.strftime("%Y-%m-%d")
TODAY_CN = _dt.strftime("%Y年%m月%d日")

from tools.jd_finance_api import get_watchlist, FOLLOWED_USERS
from backtest.engine.backtest import (
    Portfolio, score_fund_backtest, detect_market_state, compute_correlation_matrix
)
from tools.technical_indicators import compute_entry_timing_score
from tools.llm_decision import ask_llm, build_veto_prompt

EVO_PATH = PROJECT / "data" / "evolution" / "best_config.json"
if EVO_PATH.exists():
    evo = json.loads(EVO_PATH.read_text("utf-8"))
    GENE = evo["gene"]
else:
    GENE = {"min_score_bull": 2.5, "min_score_neutral": 3.0, "min_score_bear": 3.5,
            "max_correlation": 0.85, "max_position_pct": 20, "cash_reserve_pct": 0.1,
            "cooldown_profit_days": 10, "cooldown_loss_days": 30,
            "slippage_pct": 0.1, "kelly_cap": 0.4,
            "take_profit_pct": 80, "stop_loss_pct": -15}

CACHE = PROJECT / "data" / "fund_cache"
def load_cache(prefix):
    data = {}
    for f in glob.glob(str(CACHE / f"{prefix}_*.json")):
        code = Path(f).stem.replace(f"{prefix}_", "", 1)
        try: data[code] = json.loads(open(f, encoding="utf-8").read())
        except: pass
    return data

fund_rules = load_cache("trade_rules")
fund_managers = load_cache("fund_manager")
fund_profiles = load_cache("fund_profile")
fund_charts = json.loads((PROJECT / "data" / "fund_charts.json").read_text("utf-8"))

tp = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
trading_by_date = json.loads(tp.read_text("utf-8")) if tp.exists() else {}

name_map = json.loads((PROJECT / "data" / "fund_name_map.json").read_text("utf-8"))
code_to_name = {}
for nm, cd in name_map.items():
    if cd not in code_to_name: code_to_name[cd] = nm

LLM_DIR = PROJECT / "reports" / "llm-vs-machine"
LLM_DIR.mkdir(parents=True, exist_ok=True)
LLM_VP = LLM_DIR / "virtual_portfolio.json"
INITIAL_CASH = 100000



def load_vp():
    if LLM_VP.exists():
        return json.loads(LLM_VP.read_text("utf-8"))
    return {"created": TODAY, "initial_cash": INITIAL_CASH,
            "cash": INITIAL_CASH, "total_fees": 0,
            "holdings": {}, "pending": [], "history": [], "snapshots": []}

def save_vp(vp):
    LLM_VP.write_text(json.dumps(vp, ensure_ascii=False, indent=2), encoding="utf-8")


# ── LLM veto 离线回放 ──
# 从 reports/llm-decision-review/llm_60day_vetos_v2.json 读每日 veto
# 优先级: v3 > v2 > v1
def load_llm_vetos():
    candidates = [
        PROJECT / "reports" / "llm-decision-review" / "llm_60day_vetos_v3.json",
        PROJECT / "reports" / "llm-decision-review" / "llm_60day_vetos_v2.json",
        PROJECT / "reports" / "llm-decision-review" / "llm_60day_vetos.json",
        PROJECT / "reports" / "llm-decision-review" / "llm_60day_buys.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                d = json.loads(p.read_text("utf-8"))
                if d:
                    print(f"   加载 LLM veto 文件: {p.name} ({len(d)} 天)")
                    return d, p.name
            except Exception:
                continue
    return {}, "(no LLM veto file found)"


# ── 买入金额计算 (已撤回加仓改造) ──
def compute_buy_amount(portfolio, code, name, GENE):
    """计算买入金额 (纯建仓路径, 不加仓).

    2026-07-12 撤回: 加仓触发 7 次但收益仍低于机器 -6.84%,
    因 LLM v2 错杀 013841 延迟建仓 30 天, 加仓补不回.

    Returns:
        amount: 买入金额 (取整到 100)
    """
    available = portfolio.cash * (1 - GENE.get("cash_reserve_pct", 0.1))
    if available < 100:
        return 0
    max_pos = GENE.get("max_position_pct", 20)
    per_position = available * max_pos / 100
    kelly = GENE.get("kelly_cap", 0.4)
    amount = min(per_position, available * kelly)
    amount = round(amount / 100) * 100
    if amount < 100:
        return 0
    return amount


def run():
    print(f"=== LLM混合模式 {TODAY_CN} ===")
    cookies = {}
    cp = PROJECT / "data" / "jd_auth" / "cookies.json"
    if cp.exists():
        cookies = json.loads(cp.read_text("utf-8"))
    if not cookies:
        print("[ERROR] 无 Cookie"); return

    wl = get_watchlist(cookies=cookies, use_cache=True)
    if not wl or not wl.get("funds"):
        print("[ERROR] 自选列表为空"); return
    funds = {f["fund_code"]: f for f in wl["funds"]}
    print(f"   自选 {len(funds)} 只")

    # 合并交易数据
    merged_trades = dict(trading_by_date)
    for d in merged_trades:
        for r in merged_trades[d]:
            if not r.get("fund_code") and r.get("fund_name", "") in name_map:
                r["fund_code"] = name_map[r["fund_name"]]

    # 市场状态
    market = detect_market_state(TODAY, fund_charts)
    min_score = GENE.get(f"min_score_{market}", 3.0)
    print(f"   市场: {market} (门槛={min_score})")

    # 组合
    vp = load_vp()
    portfolio = Portfolio(INITIAL_CASH)
    portfolio.set_fund_rules(fund_rules)
    portfolio._profiles = fund_profiles
    portfolio.slippage_pct = GENE.get("slippage_pct", 0.1)
    for code, h in vp.get("holdings", {}).items():
        cb = h.get("cost_basis", 5000)
        portfolio.holdings[code] = {
            "name": h["name"], "shares": cb, "cost": cb,
            "buy_date": h.get("buy_date", TODAY), "buy_nav": 1.0,
        }
    portfolio.cash = vp.get("cash", INITIAL_CASH)
    portfolio.total_fees = vp.get("total_fees", 0)
    for pb in vp.get("pending", []):
        portfolio.pending_buys.append(pb)
    portfolio.sell_history = vp.get("sell_history", {})

    portfolio.settle_pending(TODAY)
    print(f"   持仓 {len(portfolio.holdings)} 只, 待确认 {len(portfolio.pending_buys)} 笔, 现金 {portfolio.cash:,.0f}")

    # 评分
    candidates = []
    for code, info in funds.items():
        name = info.get("fund_name", code)
        pts = fund_charts.get(code, [])
        if len(pts) >= 60:
            timing = compute_entry_timing_score(pts, TODAY)
            if timing.get("should_warn"):
                continue
        try:
            fs = score_fund_backtest(code, name, fund_charts, None,
                fund_rules.get(code), fund_managers.get(code),
                TODAY, merged_trades, fund_profiles.get(code))
            s = fs.total if hasattr(fs, 'total') else 3.0
            # 公告信号修正 (2026-07-12 接入)
            from backtest.engine.notice_signal import score_notice_signal
            notice = score_notice_signal(code, TODAY, name)
            notice_adj = notice.get("adjust", 0.0)
            if notice_adj != 0:
                s = max(0.5, min(5.0, s + notice_adj))
                ns = notice.get("signals", [])
                if ns:
                    print(f"   NOTICE {name[:20]}: {ns[0]} (adj={notice_adj})")
        except Exception:
            s = 3.0
        if s < min_score: continue
        candidates.append({"code": code, "name": name, "score": s})

    candidates.sort(key=lambda x: -x["score"])
    top5 = candidates[:5]
    print(f"   TOP5 候选: {[c['code'] for c in top5]}")

    # 相关性过滤
    if len(portfolio.holdings) > 0 and len(candidates) > 0:
        held_codes = list(portfolio.holdings.keys()) + [c["code"] for c in candidates]
        corr = compute_correlation_matrix(fund_charts, held_codes, TODAY, lookback=60)
        filtered = []
        for c in candidates:
            add = True
            for hc in portfolio.holdings:
                if corr.get(c["code"], {}).get(hc, 0) > GENE.get("max_correlation", 0.85):
                    add = False
                    break
            if add: filtered.append(c)
        candidates = filtered

    # === LLM 否决环节 (离线回放 v2 JSON) ===
    llm_vetos, llm_file = load_llm_vetos()
    llm_today = llm_vetos.get(TODAY, {})
    if isinstance(llm_today, dict):
        vetoes = llm_today.get("veto", [])
        if vetoes:
            print(f"   LLM veto ({llm_file}): {vetoes} (理由: {llm_today.get('reason','')[:60]})")
            # 过滤掉被 LLM veto 的候选
            before_count = len(candidates)
            candidates = [c for c in candidates if c["code"] not in vetoes]
            print(f"   过滤后候选: {len(candidates)} 只 (过滤 {before_count - len(candidates)})")
        else:
            print(f"   LLM veto ({llm_file}): 无 (机器建议保留)")
    else:
        print(f"   LLM veto ({llm_file}): 当日无决策")

    # 买入 (含建仓/加仓区分)
    max_pos = GENE.get("max_position_pct", 20)
    cash_reserve = GENE.get("cash_reserve_pct", 0.1)
    cooldown_cfg = {"profit_days": GENE.get("cooldown_profit_days", 10),
                    "loss_days": GENE.get("cooldown_loss_days", 30)}

    # 冷却检查 & 标记建仓/加仓
    pending_codes = {p["code"] for p in portfolio.pending_buys}
    eligible = []
    for c in candidates:
        if c["code"] in pending_codes:
            continue  # 已 pending
        if portfolio.is_in_cooldown(c["code"], TODAY, cooldown_cfg):
            print(f"   COOLED {c['name'][:20]}: 冷却期")
            continue
        eligible.append(c)

    buys = []
    for c in eligible:
        amount = compute_buy_amount(portfolio, c["code"], c["name"], GENE)
        if amount < 100:
            continue
        if portfolio.buy(c["code"], c["name"], amount, 1.0, TODAY):
            buys.append({"code": c["code"], "name": c["name"], "amount": amount,
                         "score": c["score"], "action": "BUY"})
            print(f"   BUY {c['name'][:25]}: {amount:,.0f} (评分{c['score']:.1f})")

    # 写持仓
    vp["cash"] = portfolio.cash
    vp["total_fees"] = portfolio.total_fees
    holdings_market_value = 0
    vp_holdings = {}
    for code, h in portfolio.holdings.items():
        cb = h["cost"]
        mv = cb
        pts = fund_charts.get(code, [])
        if pts:
            today_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if today_pts:
                latest_yaxis = float(today_pts[-1].get("yAxis", 0))
                latest_nav = (100 + latest_yaxis) / 100
                buy_pts = [p for p in pts if p.get("xAxis", "")[:10] <= h.get("buy_date", TODAY)]
                if buy_pts:
                    buy_yaxis = float(buy_pts[-1].get("yAxis", 0))
                    buy_nav = (100 + buy_yaxis) / 100
                    if buy_nav > 0:
                        mv = cb * (latest_nav / buy_nav)
        holdings_market_value += mv
        vp_holdings[code] = {
            "name": h["name"], "cost_basis": cb,
            "market_value": round(mv, 2),
            "buy_date": h.get("buy_date", TODAY),
            "pnl_pct": round((mv - cb) / cb * 100, 2) if cb > 0 else 0,
        }
    vp["holdings"] = vp_holdings
    pending_value = sum(p.get("amount", 0) for p in portfolio.pending_buys)
    total_val = portfolio.cash + holdings_market_value + pending_value
    vp["snapshots"].append({"date": TODAY, "total_value": round(total_val, 2),
                            "cash": round(portfolio.cash, 2),
                            "holdings": len(portfolio.holdings),
                            "pending": len(portfolio.pending_buys)})
    vp["sell_history"] = portfolio.sell_history
    vp["pending"] = list(portfolio.pending_buys)
    save_vp(vp)
    print(f"=== 完成: 总资产 {total_val:,.0f} ({((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%) ===")


if __name__ == "__main__":
    run()
