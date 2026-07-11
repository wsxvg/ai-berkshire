#!/usr/bin/env python3
"""策略D · 每日持仓报告 — 综合仓位预警、大师标签、减仓建议"""
import sys, json, os
os.environ["AKSHARE_QUIET"] = "1"
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def calculate_strategy_drift(holdings_data):
    """Calculate how far current portfolio deviates from Strategy D ideal state.
    Returns 0-100, higher = more dangerous.
    """
    total = 0
    holdings = []
    for h in holdings_data.get("holdings", []):
        if isinstance(h, dict):
            try:
                amt = float(str(h.get("amount", "0")).replace(",","").replace("元","").replace("¥","").strip())
                profit = float(str(h.get("profit", "0")).replace(",","").replace("元","").replace("¥","").replace("+","").strip())
                mv = amt + profit
                total += mv
                holdings.append({"code": h.get("code",""), "name": h.get("name","?"), "market_value": max(mv, 0)})
            except:
                pass
    
    if total == 0 or not holdings:
        return {"score": 0, "status": "empty"}
    
    # 1. Concentration drift (weight 40%)
    max_pct = max(h["market_value"] for h in holdings) / total
    concentration_drift = max(0, (max_pct - 0.25) / 0.75 * 100)
    
    # 2. Equity drift (weight 35%) - all funds treated as equity
    equity_drift = max(0, (1.0 - 0.70) / 0.30 * 100)
    
    # 3. Defense drift (weight 25%) - no bond/cash funds
    defense_drift = 100.0
    
    total_drift = concentration_drift * 0.40 + equity_drift * 0.35 + defense_drift * 0.25
    total_drift = min(100, total_drift)
    
    status = "normal"
    if total_drift > 60: status = "critical"
    elif total_drift > 30: status = "warning"
    elif total_drift > 10: status = "mild"
    
    return {
        "score": round(total_drift, 1),
        "concentration": round(concentration_drift, 1),
        "equity": round(equity_drift, 1),
        "defense": round(defense_drift, 1),
        "status": status
    }

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print("# 策略D · 每日持仓报告")
    print(f"日期: {today}")
    print()

    # ═════════ 1. 仓位预警 ═════════
    print("---")
    print()
    print("## 一、仓位扫描")
    print()
    try:
        from tools.position_alert import check_portfolio
        alerts = check_portfolio()
    except Exception as e:
        alerts = [f"[ERROR] {e}"]
    print()

    # ═════════ 1.5 策略偏离度 ═════════
    print("---")
    print()
    print("## 策略偏离度")
    print()
    try:
        from tools.jd_finance_api import get_user_holdings
        hdata = get_user_holdings(use_cache=False)
        drift = calculate_strategy_drift(hdata)
        drift_labels = {"critical": "🔴", "warning": "🟡", "mild": "🟠", "normal": "🟢"}
        label = drift_labels.get(drift["status"], "⚪")
        print(f"| 维度 | 偏离度 | 说明 |")
        print(f"|------|--------|------|")
        print(f"| 综合偏离 | **{drift['score']:.0f}%** | {label} {drift['status']} |")
        print(f"| 集中度 | {drift['concentration']:.0f}% | 单基上限25% |")
        print(f"| 权益仓位 | {drift['equity']:.0f}% | 建议≤70% |")
        print(f"| 防守仓位 | {drift['defense']:.0f}% | 建议≥30%债基/现金 |")
        print()
        if drift["score"] > 60:
            print("⚠️ **策略严重偏离！建议暂停所有权益加仓，先修复持仓结构。**")
        print()
    except Exception as e:
        print(f'策略偏离度: {e}')
    print()

    # ═════════ 2. 024239 减仓倒计时 ═════════
    print("---")
    print()
    print("## 二、024239 减仓计划")
    print()

    buy_date = datetime(2026, 6, 22)
    release_date = buy_date + timedelta(days=30)
    remaining = (release_date - datetime.now()).days
    cost_per_share = 4.1983
    current_nav = 3.5319
    hard_stop_nav = cost_per_share * 0.80  # -20%
    loss_pct = (current_nav / cost_per_share - 1) * 100

    print(f"| 指标 | 数值 |")
    print(f"|------|------|")
    print(f"| 已持有 | {(datetime.now()-buy_date).days} 天 |")
    print(f"| 满30天 | {release_date.strftime('%Y-%m-%d')} |")
    print(f"| 距免赎回费 | {'⚠️ ' if remaining > 0 else '✅ '}{remaining} 天 |")
    print(f"| 当前亏损 | {'🔴 ' if loss_pct < -10 else '🟡 '}{loss_pct:.2f}% |")
    print(f"| 距-20%硬止损 | {max(0, (current_nav - hard_stop_nav) / hard_stop_nav * 100):.1f}% |")
    print(f"| 硬止损价 | ¥{hard_stop_nav:.4f} |")
    print()

    # 建议
    if remaining > 0:
        print(f"**⏳ 等待期: {remaining}天**")
        if current_nav <= hard_stop_nav:
            print(f"🔴 **触发硬止损！** 净值¥{current_nav:.4f}跌破¥{hard_stop_nav:.4f}，**立即卖出！**")
        else:
            print(f"🟢 继续持有，设硬止损¥{hard_stop_nav:.4f}")
        print()

    # ═════════ 3. 四大师标签 ═════════
    print("---")
    print()
    print("## 三、大师风险标签")
    print()

    from tools.master_analysis import load_data, load_code_names, get_sector_performance_60d, analyze, load_akshare_managers
    try:
        fc, rules, hdata, profs, mgrs = load_data()
        cnames = load_code_names()
        sector_perf_val = get_sector_performance_60d(fc, cnames)
        akshare_mgr = load_akshare_managers(list(cnames.keys()))
        from tools.jd_finance_api import get_user_holdings
        hdata_user = get_user_holdings(use_cache=False)
        for h in hdata_user.get('holdings', []):
            if isinstance(h, dict):
                code = h.get('code','')
                name = h.get('name','?')[:30]
                tags = analyze(code, name, fc, rules, hdata, profs, mgrs, sector_perf_val, akshare_mgr)
                print(f'**{name} ({code})**')
                for master, (label, desc, _) in tags.items():
                    desc_clean = desc[:50]
                    print(f'- {master}: {label}')
                print()
    except Exception as e:
        print(f'大师标签: {e}')
    print()

    # ═════════ 4. 最终建议 ═════════
    print("---")
    print()
    print("## 四、最终操作建议")
    print()

    # 综合所有因素给出决策
    if current_nav <= hard_stop_nav:
        decision = "🔴 强制卖出"
        reason = "024239 触发 -20% 硬止损线"
        action = "不等到期，立刻卖出全部 595.48 份，保住剩余本金"
    elif remaining > 0:
        if loss_pct < -15:
            decision = "🟡 等满30天，准备减仓"
            reason = "亏损超过15%，但未到20%硬止损"
            action = f"等 {release_date.strftime('%m-%d')} 免赎回费后，卖一半（约¥1,000）"
        elif loss_pct < -10:
            decision = "🟡 持有观察"
            reason = "亏损在10%-15%之间"
            action = f"等 {release_date.strftime('%m-%d')} 再看，如果还在亏10%+就减1/3"
        else:
            decision = "🟢 继续持有"
            reason = "亏损在10%以内，属正常波动"
            action = "核心仓位不动，季度检视再评估"
    else:
        # 已满30天
        if loss_pct < -10:
            decision = "🔴 建议减仓"
            reason = "满30天且仍亏损超过10%"
            action = "卖一半（约¥1,000），留一半观察"
        else:
            decision = "🟢 继续持有"
            reason = "满30天且亏损在可控范围"
            action = "核心仓位不动，季度检视再评估"

    print(f"**决策: {decision}**")
    print(f"理由: {reason}")
    print(f"操作: {action}")
    print()

    # 其他基金建议
    print("**其他持仓:**")
    print("- 013841 银华集成电路（¥88）: 金额太小，放着不动")
    print("- 012922 易方达全球成长（¥37）: 金额太小，放着不动")
    print()

    # 仓位结构建议
    print("**仓位结构调整建议:**")
    print("- 当前权益占比: 100% → 建议降至 60-70%")
    print("- 建议补充债基/货基作为防守仓位")
    print("- 后续建仓用分批（`python tools/dca_planner.py 金额`）")
    print()

    print("---")
    print(f"*报告自动生成于 {today}*")


if __name__ == "__main__":
    main()