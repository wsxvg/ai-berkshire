#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用京东官方 getFundChart API 对所有被 fund_name_map 自动匹配的基金做权威重映射。

背景:
  fund_name_map.json 用天天基金模糊名称匹配 (similarity>=0.85) 填充代码，
  已被证明会把基金错配成完全不同类型的基金（如股票基金→债券基金），
  严重污染回测数据。

权威方案:
  getFundChart 免登录 API 返回 detailChartJump.productId = 京东官方标准 TA 码，
  是基金在京东实盘交易中的权威代码。用它覆盖 fund_name_map 的猜测。

输入:
  - backtest/data/trading_by_date_real414.json (原始交易)
  - backtest/data/trading_by_date_real414_v4.json (含被自动匹配的 fund_code)
  - data/_auto_all_fids.json (全部需权威映射的京东内部码)
输出:
  - data/_authoritative_full.json  {fid: productId}
  - 供下游修复 v4
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.jd_finance_api import _api_post

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "_authoritative_full.json")

def get_fund_chart_pid(fund_id):
    body = {
        "fundId": str(fund_id), "chartType": 1, "legendIndex": "1",
        "scene": "ShiPanDetailPage", "targetUid": "",
        "channel": "null", "stationType": "1", "ctp": "", "paid": "",
        "extParams": {"requestFrom": "pc", "inAppName": ""},
        "clientVersion": "9.9.9", "clientType": "android",
    }
    d = _api_post("gw2/generic/jmServer/h5/m/getFundChart", body)
    dd = d.get("resultData", {}).get("data", {}).get("datas", {})
    return dd.get("detailChartJump", {}).get("productId")

def main():
    # 已有结果（增量续跑）
    results = {}
    if os.path.exists(OUT):
        results = json.load(open(OUT, encoding="utf-8"))
    fids = json.load(open(os.path.join(BASE, "data", "_auto_all_fids.json"), encoding="utf-8"))
    todo = [str(f) for f in fids if str(f) not in results]
    print(f"已映射 {len(results)}, 待映射 {len(todo)}", flush=True)

    def work(fid):
        try:
            return (fid, get_fund_chart_pid(fid), None)
        except Exception as e:
            return (fid, None, str(e)[:60])

    ok = 0; fail = 0; t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(work, fid): fid for fid in todo}
        done = 0
        for fut in as_completed(futs):
            fid, pid, err = fut.result()
            done += 1
            if pid:
                results[fid] = pid; ok += 1
            else:
                fail += 1
            if done % 100 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"  [{done}/{len(todo)}] ok:{ok} fail:{fail} el={el:.0f}s", flush=True)
                json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

    json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"完成: 共 {len(results)} 个权威映射, 本轮新增 {ok}, 失败 {fail}", flush=True)

if __name__ == "__main__":
    main()