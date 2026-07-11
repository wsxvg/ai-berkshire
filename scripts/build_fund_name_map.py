#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基金名称→代码映射补全脚本

用天天基金(eastmoney)公开搜索API补全未映射的基金名称。
京东金融API不支持用fundId查询fundCode，所以改用天天基金公开搜索接口。

输出: data/fund_name_map.json  {fund_name: fund_code}
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from difflib import SequenceMatcher

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRADING_HISTORY = PROJECT_ROOT / "backtest" / "data" / "trading_history_fixed.json"
HOLDINGS_SNAPSHOT = PROJECT_ROOT / "data" / "holdings_snapshot.json"
FUND_CACHE = PROJECT_ROOT / "data" / "fund_cache"
OUTPUT_MAP = PROJECT_ROOT / "data" / "fund_name_map.json"

# 请求间隔(秒), 避免被eastmoney封
THROTTLE_SEC = 0.35


def normalize_name(n: str) -> str:
    """归一化基金名称, 用于相似度比较"""
    n = n.replace(" ", "").replace("　", "")
    n = n.replace("型证券投资基金", "").replace("证券投资基金", "")
    n = n.replace("开放式", "").replace("契约型", "")
    n = n.replace("(LOF)", "").replace("（LOF）", "")
    n = n.replace("有限责任", "").replace("公司", "")
    n = re.sub(r"([A-Z])类$", r"\1", n)
    n = re.sub(r"([A-Z])类\)", r"\1)", n)
    return n


def similarity(a: str, b: str) -> float:
    """计算两个名称的归一化相似度"""
    na, nb = normalize_name(a), normalize_name(b)
    return SequenceMatcher(None, na, nb).ratio()


def search_fund_eastmoney(keyword: str) -> list[tuple[str, str]]:
    """天天基金按名称搜索, 返回 [(code, name), ...]"""
    url = f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={urllib.parse.quote(keyword)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://fund.eastmoney.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
        data = json.loads(text)
        datas = data.get("Datas", [])
        return [(d.get("CODE", ""), d.get("NAME", "")) for d in datas if d.get("CODE")]
    except Exception as e:
        print(f"  [WARN] search failed for [{keyword}]: {e}", file=sys.stderr)
        return []


def load_existing_mapping() -> dict[str, str]:
    """从 snapshot + fund_profile 缓存加载已有映射"""
    name_to_code = {}

    # holdings_snapshot (简称, 最匹配交易记录)
    if HOLDINGS_SNAPSHOT.exists():
        snap = json.loads(HOLDINGS_SNAPSHOT.read_text("utf-8"))
        for user, funds in snap.get("holdings", {}).items():
            for f in (funds if isinstance(funds, list) else []):
                if isinstance(f, dict) and f.get("code") and f.get("name"):
                    name_to_code[f["name"]] = f["code"]

    # fund_profile 缓存 (全称)
    import glob
    for fpath in glob.glob(str(FUND_CACHE / "fund_profile_*.json")):
        code = Path(fpath).stem.replace("fund_profile_", "")
        if code in name_to_code.values():
            continue
        try:
            data = json.loads(open(fpath, encoding="utf-8").read())
            full_name = data.get("full_name", "")
            if full_name:
                name_to_code[full_name] = code
        except Exception:
            pass

    return name_to_code


def find_best_match(trading_name: str, candidates: list[tuple[str, str]]) -> str | None:
    """从搜索结果中找最匹配的code"""
    if not candidates:
        return None

    best_code = None
    best_score = 0.0
    for code, name in candidates:
        score = similarity(trading_name, name)
        # 精确匹配归一化后名称
        if normalize_name(trading_name) == normalize_name(name):
            return code
        if score > best_score:
            best_score = score
            best_code = code

    # 相似度阈值 0.85, 避免错误匹配
    if best_score >= 0.85:
        return best_code
    return None


def main():
    print("=== 基金名称→代码映射补全 ===")

    # 加载已有映射
    name_to_code = load_existing_mapping()
    print(f"已有映射: {len(name_to_code)} 条")

    # 加载所有交易记录中的基金名
    th = json.loads(TRADING_HISTORY.read_text("utf-8"))
    all_names = set()
    for r in th:
        fn = r.get("fund_name", "").strip()
        if fn:
            all_names.add(fn)
    print(f"交易记录基金名: {len(all_names)} 个")

    # 未映射的名称
    unmapped = [n for n in all_names if n not in name_to_code]
    print(f"未映射: {len(unmapped)} 个")

    if not unmapped:
        print("全部已映射, 无需补全")
    else:
        print(f"\n开始用天天基金API补全 {len(unmapped)} 个名称...")
        found = 0
        for i, name in enumerate(unmapped):
            candidates = search_fund_eastmoney(name)
            code = find_best_match(name, candidates)
            if code:
                name_to_code[name] = code
                found += 1
                if found <= 5 or found % 20 == 0:
                    print(f"  [{found}/{len(unmapped)}] {name[:30]} -> {code}")
            else:
                if i < 5:
                    print(f"  [MISS] {name[:40]} (候选{len(candidates)}条都不匹配)")
            time.sleep(THROTTLE_SEC)

        print(f"\n补全完成: 新增 {found}/{len(unmapped)} 个映射")

    # 保存
    # 按名称排序输出
    sorted_map = dict(sorted(name_to_code.items()))
    OUTPUT_MAP.write_text(
        json.dumps(sorted_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n已保存到 {OUTPUT_MAP} ({len(sorted_map)} 条)")

    # 统计覆盖率
    covered = sum(1 for n in all_names if n in sorted_map)
    print(f"覆盖率: {covered}/{len(all_names)} ({covered/len(all_names)*100:.1f}%)")


if __name__ == "__main__":
    main()
