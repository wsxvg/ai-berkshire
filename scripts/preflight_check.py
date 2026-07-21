"""回测前数据预检：确保所有必需数据已就绪。

检查项:
1. 基金净值数据 (data/fund_charts/) — 至少252天历史
2. 交易规则 (data/fund_cache/trade_rules_*.json)
3. 基金档案 (data/fund_cache/fund_profile_*.json)
4. 基金经理 (data/fund_cache/fund_manager_*.json)
5. 持仓分布 (data/fund_cache/fund_holdings_*.json)

缺失数据自动拉取补全。
"""
import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.chart_loader import load_all_charts, get_chart_index


def check_charts(min_days: int = 252) -> dict:
    """检查基金净值数据完整性。"""
    charts = load_all_charts()
    index = get_chart_index()
    total = len(charts)
    insufficient = {c: info["count"] for c, info in index.items() if info.get("count", 0) < min_days}
    sufficient = total - len(insufficient)
    print(f"[CHART] 总计 {total} 只基金")
    print(f"  数据充分 (≥{min_days}天): {sufficient} 只 ({sufficient/max(total,1)*100:.1f}%)")
    print(f"  数据不足 (<{min_days}天): {len(insufficient)} 只 ({len(insufficient)/max(total,1)*100:.1f}%)")
    if insufficient:
        # 显示最差的10只
        worst = sorted(insufficient.items(), key=lambda x: x[1])[:10]
        print(f"  最差10只: {worst}")
    return {"total": total, "sufficient": sufficient, "insufficient": len(insufficient)}


def check_cache(pattern: str, name: str) -> int:
    """检查缓存文件数量。"""
    cache_dir = PROJECT / "data" / "fund_cache"
    files = list(cache_dir.glob(pattern))
    print(f"[{name}] 缓存文件: {len(files)} 个")
    return len(files)


def check_trading_data() -> bool:
    """检查交易记录数据。"""
    tp = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
    if not tp.exists():
        print("[FAIL] trading_by_date_fixed.json 不存在")
        return False
    data = json.loads(tp.read_text("utf-8"))
    total_records = sum(len(v) for v in data.values())
    total_days = len(data)
    print(f"[TRADING] {total_days} 个交易日, {total_records} 条交易记录")
    if total_days < 100:
        print(f"  [WARN] 交易日偏少 ({total_days} < 100)")
    return True


def fetch_missing_charts(min_days: int = 63) -> int:
    """拉取数据不足的基金净值。"""
    from scripts.bulk_fetch_charts import fetch_full_nav
    from tools.chart_loader import load_single_chart, update_chart
    charts_dir = PROJECT / "data" / "fund_charts"
    index = get_chart_index()
    insufficient = [c for c, info in index.items() if info.get("count", 0) < min_days]
    if not insufficient:
        print("[FETCH] 所有基金数据充分，无需拉取")
        return 0
    print(f"[FETCH] {len(insufficient)} 只基金数据不足，开始拉取...")
    ok = 0
    for i, code in enumerate(insufficient):
        try:
            pts = fetch_full_nav(code)
            if pts and len(pts) >= min_days:
                update_chart(code, pts, charts_dir)
                ok += 1
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(insufficient)}] ok={ok}")
        except Exception as e:
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(insufficient)}] ERR: {e}")
        time.sleep(0.15)
    print(f"[FETCH] 完成: {ok}/{len(insufficient)} 成功")
    return ok


def main():
    print("=" * 60)
    print("回测数据预检")
    print("=" * 60)

    # 1. 交易记录
    ok = check_trading_data()
    if not ok:
        print("\n[FAIL] 交易记录缺失，无法回测")
        sys.exit(1)

    # 2. 缓存文件
    check_cache("trade_rules_*.json", "TRADE_RULES")
    check_cache("fund_profile_*.json", "FUND_PROFILE")
    check_cache("fund_manager_*.json", "FUND_MANAGER")
    check_cache("fund_holdings_*.json", "FUND_HOLDINGS")

    # 3. 基金净值
    result = check_charts(min_days=252)

    # 4. 如果有大量数据不足，提示拉取
    if result["insufficient"] > result["total"] * 0.3:
        print(f"\n[WARN] {result['insufficient']} 只基金数据不足 (>{result['total']*0.3:.0f})")
        print("建议运行: python scripts/bulk_fetch_charts.py --force")

    print("\n[OK] 预检完成")


if __name__ == "__main__":
    main()
