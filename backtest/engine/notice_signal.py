"""公告信号评分 - 把基金公告转为机器可读的修正项

接入位置: backtest/engine/backtest.py score_fund_backtest
2026-07-12 新增, LLM 公告增强是 0 否决模式的关键补充

评分规则 (v3 硬风控, 跟 LLM 心法一致):
- 基金经理变更 (< 6 个月): -1.5 (严重不稳, 必拦截)
- 基金经理变更 (6-12 个月): -0.5 (警告)
- 高级管理人员变更 (董事长/副总): 0 (不影响基金, 噪音)
- 基金分红配送: 0 (中性事件)
- 定期报告发布: 0 (无信号)
- 估值方法调整: -0.5 (持仓变动信号)
- 持仓估值方法调整 (如 013841 长盈通): -0.5
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).resolve().parent.parent.parent
CACHE = PROJECT / "data" / "fund_cache"


def load_notices(fund_code, notice_type="manager"):
    """加载指定基金的指定类型公告 (manager/dividend/report/all)"""
    p = CACHE / f"fund_notices_{fund_code}_{notice_type}.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("notices", [])
    except Exception:
        return []


def _has_keyword(title, keywords):
    return any(kw in title for kw in keywords)


def score_notice_signal(fund_code, cutoff_date, fund_name=""):
    """公告信号评分 — 截止 cutoff_date 之前的公告 (反未来函数)

    返回: dict {adjust: 修正值, signals: [信号描述], details: [...]}
    """
    cutoff = cutoff_date[:10] if cutoff_date else ""
    adjust = 0.0
    signals = []
    details = []

    # 1) 经理变更信号
    mgr_notices = load_notices(fund_code, "manager")
    for n in mgr_notices:
        date = n.get("date", "")[:10]
        if not date or date > cutoff:
            continue
        title = n.get("title", "")
        is_fund_manager = "基金经理" in title and ("变更" in title or "增聘" in title or "离任" in title or "解聘" in title or "调整" in title)
        is_senior_exec = "高级管理人员" in title or "董事长" in title or "首席" in title or "副总" in title
        if is_fund_manager:
            days_ago = (datetime.strptime(cutoff, "%Y-%m-%d") - datetime.strptime(date, "%Y-%m-%d")).days
            if days_ago < 180:
                adjust += -1.5
                signals.append(f"基金经理变更 {date} ({days_ago}天前) 严重")
                details.append({"type": "manager_change", "date": date, "days_ago": days_ago, "severity": "high"})
            elif days_ago < 365:
                adjust += -0.5
                signals.append(f"基金经理变更 {date} ({days_ago}天前) 警告")
                details.append({"type": "manager_change", "date": date, "days_ago": days_ago, "severity": "medium"})
        elif is_senior_exec:
            # 高管变更不影响基金操作, 噪音
            pass

    # 2) 估值方法调整 / 持仓重大变动
    all_notices = load_notices(fund_code, "all")
    for n in all_notices:
        date = n.get("date", "")[:10]
        if not date or date > cutoff:
            continue
        title = n.get("title", "")
        # 估值方法调整 (持仓变动信号)
        if "估值方法" in title and "调整" in title:
            days_ago = (datetime.strptime(cutoff, "%Y-%m-%d") - datetime.strptime(date, "%Y-%m-%d")).days
            if days_ago < 90:
                adjust += -0.5
                signals.append(f"估值方法调整 {date} ({days_ago}天前)")
                details.append({"type": "valuation_adjust", "date": date, "days_ago": days_ago})
        # 基金合同重大变更 / 投资范围调整
        if ("投资范围" in title or "基金合同" in title) and "修订" in title:
            days_ago = (datetime.strptime(cutoff, "%Y-%m-%d") - datetime.strptime(date, "%Y-%m-%d")).days
            if days_ago < 90:
                adjust += -0.5
                signals.append(f"合同/范围调整 {date} ({days_ago}天前)")
                details.append({"type": "contract_change", "date": date, "days_ago": days_ago})

    return {"adjust": round(adjust, 2), "signals": signals, "details": details}


def test_coverage(fund_codes, cutoff_date="2026-04-15"):
    """测试公告覆盖率"""
    triggered = 0
    for c in fund_codes:
        r = score_notice_signal(c, cutoff_date)
        if r["adjust"] != 0:
            print(f"  {c}: adjust={r['adjust']} signals={r['signals'][:2]}")
            triggered += 1
    print(f"\n{triggered}/{len(fund_codes)} 只触发公告信号 (cutoff={cutoff_date})")


if __name__ == "__main__":
    # 测试 13 只自选
    WATCHLIST = ["013841", "016664", "022184", "024239", "024663", "017731",
                 "501226", "539002", "018147", "012922", "012920", "021511", "023851"]
    print("=== 公告信号测试 (5 个关键建仓日) ===")
    for d in ["2026-04-15", "2026-04-28", "2026-05-19", "2026-05-29", "2026-06-22"]:
        print(f"\n--- cutoff {d} ---")
        test_coverage(WATCHLIST, d)
