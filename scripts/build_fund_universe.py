#!/usr/bin/env python3
"""全量基金池构建脚本 — 从东方财富获取20000+基金，预筛选后拉取历史净值

用途：脱离大佬信号，从全市场基金中筛选高收益标的

流程：
1. 从东方财富获取全量基金列表（含收益率排名）
2. 按类型+收益率预筛选（去掉债券/货币基金，保留股票/混合/QDII）
3. 按近1年收益率排序，取Top N
4. 拉取Top N的历史净值数据（用于回测）
5. 保存到 data/fund_universe/

用法:
    python scripts/build_fund_universe.py              # 获取全量列表+预筛选
    python scripts/build_fund_universe.py --top 500    # 额外拉取Top500历史净值
    python scripts/build_fund_universe.py --top 100 --type qdii  # 只拉QDII Top100
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.eastmoney_api import get_all_funds, get_fund_nav_history

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fund_universe"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def build_universe(top_n=None, fund_types=None):
    """构建全量基金池
    
    Args:
        top_n: 取收益率前N只（None=全部）
        fund_types: 要包含的基金类型列表，None=全部可交易类型
    """
    print("=" * 70)
    print("全量基金池构建")
    print("=" * 70)
    
    # Step 1: 获取全量基金列表
    all_funds = []
    if fund_types:
        for ft in fund_types:
            print(f"\n--- 获取 {ft} 类型基金 ---")
            r = get_all_funds(ft, "1n")  # 按近1年收益率降序
            all_funds.extend(r["rankings"])
            print(f"  {ft}: {len(r['rankings'])} 只 (总计: {r['total_count']})")
    else:
        print("\n--- 获取全量基金 ---")
        r = get_all_funds("all", "1n")
        all_funds = r["rankings"]
        print(f"  全量: {len(all_funds)} 只 (总计: {r['total_count']})")
    
    # Step 2: 去重
    seen = set()
    unique_funds = []
    for f in all_funds:
        if f["code"] not in seen:
            seen.add(f["code"])
            unique_funds.append(f)
    print(f"\n去重后: {len(unique_funds)} 只")
    
    # Step 3: 预筛选 — 排除明显不可交易的
    # 排除：净值=0（未开始交易）、成立不足1年（nav_date太近）
    tradeable = []
    for f in unique_funds:
        if f["nav"] > 0 and f["nav_date"]:
            tradeable.append(f)
    print(f"可交易: {len(tradeable)} 只")
    
    # Step 4: 按近1年收益率排序（已排序但去重后需重排）
    tradeable.sort(key=lambda x: x["year_return"], reverse=True)
    
    # Step 5: 取Top N
    if top_n and top_n < len(tradeable):
        top_funds = tradeable[:top_n]
    else:
        top_funds = tradeable
    
    # Step 6: 保存列表
    list_file = DATA_DIR / f"fund_list_{datetime.now().strftime('%Y%m%d')}.json"
    with open(list_file, "w", encoding="utf-8") as f:
        json.dump({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_market": len(unique_funds),
            "total_tradeable": len(tradeable),
            "selected": len(top_funds),
            "funds": top_funds,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n基金列表已保存: {list_file}")
    
    # Step 7: 统计
    print(f"\n{'='*70}")
    print("统计概览")
    print(f"{'='*70}")
    print(f"全市场基金: {len(unique_funds)}")
    print(f"可交易基金: {len(tradeable)}")
    print(f"选中基金: {len(top_funds)}")
    
    # 收益率分布
    if top_funds:
        returns = [f["year_return"] for f in top_funds]
        print(f"\n近1年收益率分布:")
        print(f"  最高: {max(returns):.2f}%")
        print(f"  最低: {min(returns):.2f}%")
        print(f"  中位数: {sorted(returns)[len(returns)//2]:.2f}%")
        
        # Top 10
        print(f"\n收益率 Top 10:")
        for i, f in enumerate(top_funds[:10], 1):
            print(f"  {i:2}. {f['code']} {f['name'][:25]}: 1yr={f['year_return']:.2f}%")
    
    return top_funds


def fetch_nav_history(fund_codes, max_pages=40):
    """批量拉取基金历史净值
    
    Args:
        fund_codes: 基金代码列表
        max_pages: 每只基金最大页数（每页20条，40页≈800条≈3年）
    
    Returns: {code: [{date, nav, daily_return}, ...]}
    """
    print(f"\n{'='*70}")
    print(f"拉取 {len(fund_codes)} 只基金历史净值（每只最多{max_pages}页）")
    print(f"{'='*70}")
    
    cache_file = DATA_DIR / f"nav_history_{datetime.now().strftime('%Y%m%d')}.json"
    
    # 增量保存：先加载已有缓存
    result = {}
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            result = json.load(f)
        print(f"已有缓存: {len(result)} 只")
    
    total = len(fund_codes)
    for i, code in enumerate(fund_codes):
        if code in result:
            continue
        print(f"  [{i+1}/{total}] {code}...", end=" ", flush=True)
        nav = get_fund_nav_history(code, max_pages)
        if nav:
            result[code] = nav
            print(f"{len(nav)} 天 ({nav[0]['date']}~{nav[-1]['date']})")
        else:
            print("FAILED")
        
        # 每10只保存一次（防中断丢数据）
        if (i + 1) % 10 == 0:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
            print(f"  --- 保存进度: {len(result)}/{total} ---")
        
        time.sleep(0.2)
    
    # 最终保存
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"\n历史净值已保存: {cache_file} ({len(result)} 只)")
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="全量基金池构建")
    parser.add_argument("--top", type=int, default=None, 
                        help="取收益率前N只（默认全部）")
    parser.add_argument("--type", type=str, nargs="+", default=None,
                        help="基金类型: gp(股票) hh(混合) qdii zq(债券) zs(指数) fof lof")
    parser.add_argument("--nav", action="store_true",
                        help="额外拉取历史净值（用于回测）")
    parser.add_argument("--nav-pages", type=int, default=40,
                        help="历史净值每只最大页数（默认40页≈3年）")
    args = parser.parse_args()
    
    # Step 1: 构建基金列表
    funds = build_universe(top_n=args.top, fund_types=args.type)
    
    # Step 2: 拉取历史净值（可选）
    if args.nav and funds:
        codes = [f["code"] for f in funds]
        fetch_nav_history(codes, args.nav_pages)
    
    print(f"\n{'='*70}")
    print("完成!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
