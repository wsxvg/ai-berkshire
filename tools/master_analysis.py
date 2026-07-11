#!/usr/bin/env python3
"""四大师风险标签 — 分析持仓并输出风险标签（不改分，只提醒）"""
import sys, json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.fund_scorer import _float

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_data():
    """加载所需数据"""
    fc_path = PROJECT_ROOT / "backtest" / "data" / "fund_charts.json"
    with open(fc_path, encoding='utf-8') as f:
        fund_charts = json.load(f)

    # 加载基金规则（费率数据）
    cache_dir = PROJECT_ROOT / "data" / "fund_cache"
    rules = {}
    for f in sorted(cache_dir.glob("trade_rules_*.json")):
        code = f.stem.split("_", 2)[2]
        rules[code] = json.loads(f.read_text("utf-8"))

    # 加载持仓穿透
    holdings_data = {}
    for f in sorted(cache_dir.glob("fund_holdings_*latest*")):
        code = f.stem.split("_", 2)[2]
        holdings_data[code] = json.loads(f.read_text("utf-8"))

    # 加载基金profile
    profiles = {}
    for f in sorted(cache_dir.glob("fund_profile_*.json")):
        code = f.stem.split("_", 2)[2]
        profiles[code] = json.loads(f.read_text("utf-8"))

    # 加载经理数据
    managers = {}
    for f in sorted(cache_dir.glob("fund_manager_*.json")):
        code = f.stem.split("_", 2)[2]
        managers[code] = json.loads(f.read_text("utf-8"))

    return fund_charts, rules, holdings_data, profiles, managers


def load_code_names():
    """从 holdings_snapshot 构建 code→name 映射"""
    snap_path = PROJECT_ROOT / "data" / "holdings_snapshot.json"
    code_name = {}
    if snap_path.exists():
        snap = json.loads(snap_path.read_text("utf-8"))
        for user, funds in snap.get("holdings", {}).items():
            for f in funds if isinstance(funds, list) else []:
                if isinstance(f, dict) and f.get("code") and f.get("name"):
                    code_name[f["code"]] = f["name"]
    return code_name


def get_sector_performance_60d(fund_charts, code_names, cutoff_date="2026-07-03"):
    """计算各板块近60天涨幅（用于芒格赛道热度判断）"""
    sector_returns = {}
    sector_counts = {}

    # 简化的板块分类
    def guess_sector(code, name=""):
        name = str(name)
        if "半导体" in name or "芯片" in name: return "半导体"
        if "新能源" in name or "光伏" in name: return "新能源"
        if "消费" in name: return "消费"
        if "医疗" in name or "医药" in name: return "医药"
        if "科技" in name or "信息" in name or "互联网" in name: return "科技"
        if "金融" in name or "银行" in name: return "金融"
        if "军工" in name: return "军工"
        if "QDII" in name or "全球" in name or "海外" in name: return "QDII"
        if "红利" in name: return "红利"
        return "其他"

    for code, pts in fund_charts.items():
        name = code_names.get(code, "")
        valid = [p for p in pts if p.get("xAxis", "") <= cutoff_date]
        if len(valid) < 20:
            continue
        recent = valid[-min(60, len(valid)):]
        ret = _float(recent[-1].get("yAxis", 0)) - _float(recent[0].get("yAxis", 0))
        sector = guess_sector(code, name)
        sector_returns[sector] = sector_returns.get(sector, 0) + ret
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    # 取平均
    result = {}
    for s, total in sector_returns.items():
        count = sector_counts.get(s, 1)
        result[s] = round(total / count, 1)
    return result


def duanyongping_tag(code, holdings_data, profiles, akshare_holdings=None):
    try:
        if akshare_holdings and code in akshare_holdings:
            stocks = akshare_holdings[code]
            if stocks is not None and len(stocks) > 0:
                good_biz = 0
                bad_biz = 0
                total = 0
                stock_names = []
                for _, row in stocks.iterrows():
                    name = str(row.iloc[2]) if len(row) >= 3 else str(row.iloc[0])
                    pct = float(row.iloc[3]) if len(row) >= 4 else 0
                    total += 1
                    stock_names.append(f"{name}({pct:.1f}%)")
                    if any(kw in name for kw in ["茅台","腾讯","阿里","美团","苹果","微软","谷歌","消费","医药","创新药","医疗","台积电","Ciena","半导体","芯片","科技","人工智能","AI","通信","光模块","软件","互联网","新能源","汽车"]):
                        good_biz += 1
                    elif any(kw in name for kw in ["地产","煤炭","钢铁","化工","有色","水泥"]):
                        bad_biz += 1
                if total > 0:
                    good_pct = good_biz / total * 100
                    bad_pct = bad_biz / total * 100
                    stocks_str = ", ".join(stock_names[:5])
                    print(f"DEBUG: 024239 holdings: good={good_pct:.0f}% bad={bad_pct:.0f}% stocks={stocks_str}")
                    if good_pct >= 50:
                        return (chr(0x1f7e2) + " 好生意主导", f"持仓{good_pct:.0f}%是好生意（{stocks_str}）", "green")
                    elif bad_pct >= 30:
                        return (chr(0x1f7e1) + " 高周期暴露", f"持仓{bad_pct:.0f}%是周期/地产/大宗（{stocks_str}）", "yellow")
                    else:
                        return (chr(0x26aa) + " 混合型", f"无明显倾向（{stocks_str}）", "gray")
    except:
        pass

    # Fallback to JD Finance data
    hd = holdings_data.get(code, {})
    stocks = hd.get("top_stocks", [])
    report_date = hd.get("report_date", "")
    if report_date:
        try:
            from datetime import datetime
            rpt = datetime.strptime(report_date[:10], "%Y-%m-%d")
            now = datetime(2026, 7, 4)
            months_lag = (now - rpt).days / 30
            if months_lag > 2:
                return (chr(0x26a0) + " 数据滞后", f"持仓数据是{months_lag:.0f}个月前（{report_date[:10]}），可能已调仓", "gray")
        except:
            pass
    if not stocks:
        return (chr(0x26aa) + " 数据不足", "无持仓穿透数据", "gray")
    good_biz = 0
    bad_biz = 0
    total = len(stocks)
    for s in stocks:
        name = str(s.get("name", ""))
        if any(kw in name for kw in ["茅台","腾讯","阿里","美团","苹果","微软","谷歌","消费","医药","创新药","医疗"]):
            good_biz += 1
        elif any(kw in name for kw in ["地产","煤炭","钢铁","化工","有色","水泥"]):
            bad_biz += 1
    good_pct = good_biz / total * 100
    bad_pct = bad_biz / total * 100
    if good_pct >= 60:
        return (chr(0x1f7e2) + " 好生意主导", f"持仓{good_pct:.0f}%是好生意（消费/科技/医药）", "green")
    elif bad_pct >= 40:
        return (chr(0x1f7e1) + " 高周期暴露", f"持仓{bad_pct:.0f}%是周期/地产/大宗商品", "yellow")
    else:
        return (chr(0x26aa) + " 混合型", "无明显行业倾向", "gray")

def buffett_tag(code, rules):
    """巴菲特标签：费率优势（已体现在成本分，只输出标签）"""
    r = rules.get(code, {})
    try:
        mf = float(r.get("manage_fee", 1.2))
    except:
        mf = 1.2
    try:
        pf = float(r.get("purchase_fee", 0.15))
    except:
        pf = 0.15
    is_c_class = "C" in str(r.get("fund_code", ""))

    if mf < 0.5 and pf == 0:
        return ("🟢 费率优势", f"管理费{mf}%+0申购费，成本低", "green")
    elif mf > 1.5:
        return ("🔴 费率偏高", f"管理费{mf}%偏贵", "red")
    elif mf < 0.8:
        return ("🟢 费率较低", f"管理费{mf}%", "green")
    else:
        return ("⚪ 费率适中", f"管理费{mf}%", "gray")


def munger_tag(code, fund_name, sector_perf_60d):
    """芒格标签：赛道热度（用板块真实涨幅）"""
    def guess_sector(name):
        name = str(name)
        if "半导体" in name or "芯片" in name: return "半导体"
        if "新能源" in name: return "新能源"
        if "科技" in name or "互联网" in name: return "科技"
        if "消费" in name: return "消费"
        if "医疗" in name or "医药" in name: return "医药"
        if "金融" in name: return "金融"
        if "QDII" in name or "全球" in name: return "QDII"
        if "红利" in name: return "红利"
        return "其他"

    sector = guess_sector(fund_name)
    perf = sector_perf_60d.get(sector, 0)

    if perf > 30:
        return ("🔴 赛道过热", f"{sector}板块近60天涨{perf:.1f}%，注意回调风险", "red")
    elif perf > 15:
        return ("🟡 赛道偏热", f"{sector}板块近60天涨{perf:.1f}%", "yellow")
    elif perf < -10:
        return ("🟢 冷门机会", f"{sector}板块近60天跌{perf:.1f}%，可能是低点", "green")
    else:
        return ("⚪ 赛道正常", f"{sector}板块近60天涨{perf:.1f}%", "gray")


def lilu_tag(code, managers, akshare_mgr=None):
    """李录标签：经理稳定性（使用AkShare经理数据）"""
    # Try AkShare data first (more accurate)
    if akshare_mgr and code in akshare_mgr:
        m = akshare_mgr[code]
        tenure_days = m.get("tenure_days", 0)
        tenure_years = tenure_days / 365
        fund_count = m.get("fund_count", 0)
        total_asset = m.get("total_asset", "?")

        if tenure_years >= 8:
            company = m.get("company", "")
            return ("🔵 经理稳定", f"{m.get('manager_name','')}@{company} 任职{tenure_years:.0f}年，管理{total_asset}亿", "blue")
        elif tenure_years >= 5:
            return ("🔵 经理稳定", f"任职{tenure_years:.0f}年", "blue")
        elif tenure_years >= 3:
            return ("⚪ 经理一般", f"任职{tenure_years:.0f}年", "gray")
        elif tenure_years >= 1:
            return ("🟡 经理经验不足", f"任职{tenure_years:.0f}年", "yellow")
        else:
            return ("🔴 经理刚换", f"任职不足1年", "red")

    # Fallback to JD Finance data
    mgr = managers.get(code, {})
    manager_list = mgr.get("managers", [])
    if not manager_list:
        return ("⚪ 数据不足", "无经理信息", "gray")

    max_tenure = 0
    for m in manager_list:
        try:
            tenure = float(m.get("tenure_years", 0))
            if tenure > max_tenure:
                max_tenure = tenure
        except:
            pass

    if max_tenure >= 8:
        return ("🔵 经理稳定", f"任职{max_tenure:.0f}年", "blue")
    elif max_tenure >= 5:
        return ("🔵 经理稳定", f"任职{max_tenure:.0f}年", "blue")
    elif max_tenure >= 3:
        return ("⚪ 经理一般", f"任职{max_tenure:.0f}年", "gray")
    elif max_tenure >= 1:
        return ("🟡 经理经验不足", f"任职{max_tenure:.0f}年", "yellow")
    else:
        return ("🔴 经理刚换", "任职不足1年或刚变更", "red")



def load_akshare_managers(codes):
    """从AkShare获取基金经理数据"""
    import akshare as ak
    import pandas as pd
    from datetime import datetime
    cache_path = Path(__file__).resolve().parent.parent / "data" / "cache_managers.json"
    if cache_path.exists():
        from datetime import datetime, timedelta
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=24):
            try:
                return json.loads(cache_path.read_text("utf-8"))
            except:
                pass
    try:
        df = ak.fund_manager_em()
        result = {}
        for code in codes:
            mask = df['现任基金代码'].astype(str).str.contains(code, na=False)
            if not mask.any():
                continue
            r = df[mask].iloc[0]
            tenure_days = int(r.get("累计从业时间", 0)) if pd.notna(r.get("累计从业时间", 0)) else 0
            result[code] = {
                "manager_name": str(r.get("姓名", "")),
                "company": str(r.get("所属公司", "")),
                "tenure_days": tenure_days,
                "fund_count": 1,
                "total_asset": str(r.get("现任基金资产总规模", "?")),
            }
        # Save to cache
        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        except:
            pass
        return result
    except Exception as e:
        print(f"AkShare manager error: {e}")
        return {}
    """从AkShare获取基金经理数据"""
    import akshare as ak
    import pandas as pd
    from datetime import datetime

    try:
        df = ak.fund_manager_em()
        result = {}
        for code in codes:
            # Column name is 现任基金代码
            mask = df['现任基金代码'].astype(str).str.contains(code, na=False)
            if not mask.any():
                continue
            r = df[mask].iloc[0]
            tenure_days = int(r.get("累计从业时间", 0)) if pd.notna(r.get("累计从业时间", 0)) else 0
            result[code] = {
                "manager_name": str(r.get("姓名", "")),
                "company": str(r.get("所属公司", "")),
                "tenure_days": tenure_days,
                "fund_count": 1,
                "total_asset": str(r.get("现任基金资产总规模", "?")),
                "best_return": str(r.get("现任基金最佳回报", "?")),
            }
        return result
    except Exception as e:
        print(f"AkShare manager error: {e}")
        return {}

def analyze(code, name, fund_charts, rules, holdings_data, profiles, managers, sector_perf_60d, akshare_mgr=None):
    """对单只基金执行四大师分析"""
    tags = {}

    # Load AkShare holdings data for duanyongping tag
    akshare_holdings = {}
    try:
        import akshare as ak
        for c in [code]:
            try:
                df = ak.fund_portfolio_hold_em(symbol=c, date="2026")
                if df is not None and not df.empty:
                    akshare_holdings[c] = df
            except:
                pass
    except:
        pass

    tags["段永平"] = duanyongping_tag(code, holdings_data, profiles, akshare_holdings)
    tags["巴菲特"] = buffett_tag(code, rules)
    tags["芒格"] = munger_tag(code, name, sector_perf_60d)
    tags["李录"] = lilu_tag(code, managers, akshare_mgr)

    return tags


def main():
    fund_charts, rules, holdings_data, profiles, managers = load_data()
    akshare_mgr = load_akshare_managers(list(code_names.keys()))
    code_names = load_code_names()

    # 计算板块热度
    print("计算板块热度...")
    sector_perf = get_sector_performance_60d(fund_charts, code_names)
    print(f"板块近60天涨幅: {', '.join(f'{s}={v:.1f}%' for s,v in sorted(sector_perf.items(), key=lambda x:-x[1])[:8])}")
    print()

    # 读取用户持仓
    from tools.jd_finance_api import get_user_holdings
    data = get_user_holdings(use_cache=False)
    holdings = data.get('holdings', [])

    for h in holdings:
        if isinstance(h, dict):
            code = h.get('code', '')
            name = h.get('name', '?')
            profit_rate = h.get('profit_rate', '0')

            print(f"=== {name} ({code}) ===")
            print(f"当前收益: {profit_rate}")
            print()

            tags = analyze(code, name, fund_charts, rules, holdings_data, profiles, managers, sector_perf)

            for master, (label, desc, color) in tags.items():
                print(f"  {master}: {label}")
                print(f"    {desc}")
            print()


if __name__ == "__main__":
    main()