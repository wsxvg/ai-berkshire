#!/usr/bin/env python3
"""持仓穿透风险报告 — 每天自动生成"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 加载股票行业映射
try:
    _STOCK_SECTOR = json.loads((_PROJECT_ROOT / "backtest" / "data" / "stock_sector_map.json").read_text(encoding="utf-8"))
except:
    _STOCK_SECTOR = {}

def _get_stock_sector(code, name=""):
    """获取股票所属行业，先用映射表，再用名字关键词"""
    if code in _STOCK_SECTOR:
        return _STOCK_SECTOR[code]
    n = name or ""
    if "半导体" in n or "芯片" in n: return "半导体"
    if "科技" in n or "信息" in n or "通信" in n or "电子" in n: return "科技"
    if "医疗" in n or "医药" in n or "生物" in n: return "医疗"
    if "银行" in n or "保险" in n or "证券" in n: return "金融"
    return "其他"

def _load_fund_holdings(fund_code):
    """从缓存加载基金持仓"""
    # 优先从 fund_data 统一缓存
    fund_data_path = _PROJECT_ROOT / "data" / "fund_cache" / f"fund_data_{fund_code}.json"
    if fund_data_path.exists():
        try:
            data = json.loads(fund_data_path.read_text("utf-8"))
            holdings = data.get("holdings", {})
            stocks = holdings.get("top_stocks", []) if isinstance(holdings, dict) else []
            if stocks:
                return stocks
        except: pass
    # fallback: 单独持仓缓存 (有 _latest 后缀)
    for suffix in ["", "_latest"]:
        h_path = _PROJECT_ROOT / "data" / "fund_cache" / f"fund_holdings_{fund_code}{suffix}.json"
        if h_path.exists():
            try:
                data = json.loads(h_path.read_text("utf-8"))
                return data.get("top_stocks", [])
            except: pass
    return []

def generate_penetration_report(holdings_codes=None):
    """生成持仓穿透风险报告"""
    from tools.jd_finance_api import get_stock_quotes_extended

    report = {
        "sector_allocation": defaultdict(float),  # 行业分布
        "stock_exposure": defaultdict(float),      # 个股暴露
        "valuation_warnings": [],                  # 估值预警
        "sector_concentration": {},                # 行业集中度
        "overlap_funds": defaultdict(list),        # 持仓重叠
    }

    all_stocks = {}  # code -> {sector, total_ratio, funds}

    for code in (holdings_codes or []):
        stocks = _load_fund_holdings(code)
        for s in stocks:
            scode = s.get("code", "")
            ratio = float(str(s.get("ratio", "0")).replace("%", ""))
            name = s.get("name", "")
            sector = _get_stock_sector(scode, name)

            if scode not in all_stocks:
                all_stocks[scode] = {"name": name, "sector": sector, "total_ratio": 0, "funds": []}
            all_stocks[scode]["total_ratio"] += ratio
            all_stocks[scode]["funds"].append(code)

            report["sector_allocation"][sector] += ratio
            report["stock_exposure"][name] += ratio

    # 行业集中度
    total = sum(report["sector_allocation"].values()) or 1
    for sec, r in sorted(report["sector_allocation"].items(), key=lambda x: -x[1]):
        pct = r / total * 100
        report["sector_concentration"][sec] = round(pct, 1)

    # 获取持仓股票估值
    stock_codes = list(all_stocks.keys())
    valuations = {}
    # 分批获取估值
    batch_size = 20
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i+batch_size]
        try:
            quotes = get_stock_quotes_extended(batch)
            valuations.update(quotes)
        except:
            pass

    # 估值预警
    for scode, info in all_stocks.items():
        if scode in valuations:
            v = valuations[scode]
            pe = v.get("pe_ratio", 0)
            if pe and pe > 100:
                report["valuation_warnings"].append({
                    "stock": info["name"],
                    "pe": pe,
                    "sector": info["sector"],
                    "warning": "PE>100, 极高估值",
                    "funds": info["funds"],
                })
            elif pe and pe < 10 and pe > 0:
                report["valuation_warnings"].append({
                    "stock": info["name"],
                    "pe": pe,
                    "sector": info["sector"],
                    "warning": "PE<10, 低估值",
                    "funds": info["funds"],
                })

    # 持仓重叠分析
    for scode, info in all_stocks.items():
        if len(info["funds"]) >= 2:
            report["overlap_funds"][info["name"]] = {
                "sector": info["sector"],
                "funds": info["funds"],
                "total_ratio": round(info["total_ratio"], 1),
            }

    return report


def main():
    parser = argparse.ArgumentParser(description="持仓穿透风险报告")
    parser.add_argument("--codes", nargs="+", help="基金代码列表")
    parser.add_argument("--save", action="store_true", help="保存到文件")
    args = parser.parse_args()

    if not args.codes:
        print("Usage: python tools/penetration_report.py --codes 011452 021528 008888")
        return

    report = generate_penetration_report(args.codes)

    print(f"\n{'='*60}")
    print("持仓穿透风险报告")
    print(f"{'='*60}")

    print(f"\n行业分布:")
    print(f"{'行业':20s} {'占比':>8s}")
    print("-"*30)
    for sec, pct in sorted(report["sector_concentration"].items(), key=lambda x: -x[1]):
        print(f"{sec:20s} {pct:>7.1f}%")

    print(f"\n估值预警:")
    for w in report["valuation_warnings"][:10]:
        print(f"  ⚠ {w['stock']}: PE={w['pe']}, {w['warning']}")

    print(f"\n持仓重叠分析:")
    for name, info in sorted(report["overlap_funds"].items(), key=lambda x: -x[1]["total_ratio"])[:10]:
        print(f"  {name}: {info['sector']}, {len(info['funds'])}只基金持有")

    if args.save:
        out = _PROJECT_ROOT / "reports" / "auto" / "penetration_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n保存到 {out}")


if __name__ == "__main__":
    import argparse
    main()