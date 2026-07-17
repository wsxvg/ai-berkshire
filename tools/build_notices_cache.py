"""批量抓取 13 只自选基金公告 - 分类型翻多页

输出文件 (按类型分目录避免互相覆盖):
- data/fund_cache/fund_notices_{code}_all.json  (type=0 全部)
- data/fund_cache/fund_notices_{code}_manager.json (type=14 经理变更)
- data/fund_cache/fund_notices_{code}_dividend.json (type=13 分红)
- data/fund_cache/fund_notices_{code}_report.json (type=12 定期报告)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.jd_finance_api import _api_post, _ensure_cookies, _CACHE_DIR
import json
from pathlib import Path

WATCHLIST = ["013841", "016664", "022184", "024239", "024663", "017731",
             "501226", "539002", "018147", "012922", "012920", "021511", "023851"]

# 类型: (后缀, typeCode, label, max_pages)
TYPES = [
    ("all", "0", "全部", 20),
    ("manager", "14", "经理变更", 5),
    ("dividend", "13", "分红配送", 5),
    ("report", "12", "定期报告", 5),
]


def fetch_all_pages(code, type_code, max_pages, cookies):
    """翻多页抓取 type_code 类型公告"""
    all_items = []
    for page in range(1, max_pages + 1):
        data = _api_post("gw/generic/jj/h5/m/getFundNoticesPageInfo",
                         {"fundCode": code, "pageSize": 30, "noticeTypeCode": type_code, "pageNum": page},
                         cookies=cookies)
        rd = data.get("resultData", {})
        if rd.get("code") != "0000":
            break
        items = rd.get("datas", {}).get("noticeContentList", [])
        if not items:
            break
        for n in items:
            all_items.append({
                "date": n.get("noteDate", ""),
                "title": n.get("noticeTitle", ""),
                "url": n.get("noticeHtmlUrl", ""),
                "type": str(n.get("noticeTypeCode", "")),
            })
        if len(items) < 30:
            break  # 末页
    return all_items


def main():
    c = _ensure_cookies()
    summary = {}
    for code in WATCHLIST:
        print(f"\n--- {code} ---")
        summary[code] = {}
        for suffix, type_code, label, max_pages in TYPES:
            items = fetch_all_pages(code, type_code, max_pages, c)
            summary[code][label] = len(items)
            # 写入按类型分文件
            out = _CACHE_DIR / f"fund_notices_{code}_{suffix}.json"
            out.write_text(json.dumps({"fund_code": code, "type_code": type_code,
                                        "label": label, "notices": items}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            print(f"  {label} (type={type_code}): {len(items)} 条 → {out.name}")
            # 打印经理变更前 2 条示例
            if type_code == "14" and items:
                for n in items[:2]:
                    print(f"    - {n['date'][:10]} {n['title'][:55]}")

    # 写汇总
    Path("data/fund_cache/notices_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 完成, 13 只基金 × 4 类型 全部缓存 ===")
    for code, types in summary.items():
        print(f"  {code}: {types}")


if __name__ == "__main__":
    main()
