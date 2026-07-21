#!/usr/bin/env python3
"""生成京东金融 API 完整文档。

整合三个数据源:
1. tools/jd_finance_api.py 中已实现的接口
2. Playwright 抓包发现的接口
3. .playwright-mcp/ 会话日志中发现的接口 + 预捕获JSON响应
"""
import json, re, sys
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).resolve().parent.parent

# ── 1. 从 jd_finance_api.py 中提取已实现的接口 ──

def extract_implemented_apis():
    """从代码中提取所有 API 调用及其所在的函数"""
    api_file = PROJECT / "tools" / "jd_finance_api.py"
    content = api_file.read_text("utf-8")
    
    # 找所有 _api_post / _api_form 调用
    # 格式: _api_post("path", {body}, ...) 或 _api_form("path", body, ...)
    results = []
    
    # 匹配函数定义和其中的API调用
    func_pattern = re.compile(
        r'def\s+(\w+)\s*\([^)]*\).*?(?=\ndef\s|\Z)',
        re.DOTALL
    )
    
    for func_match in func_pattern.finditer(content):
        func_name = func_match.group(1)
        func_body = func_match.group(0)
        
        # 在函数体中找 API 调用
        api_calls = re.findall(
            r'(?:_api_post|_api_form|_api_post_batch|_api_form_batch)\s*\(\s*["\']([^"\']+)["\']',
            func_body
        )
        
        for api_path in api_calls:
            # 清理路径
            clean_path = api_path.split("?")[0]
            # 提取查询参数中的 pageId
            page_id = ""
            if "pageId=" in api_path:
                page_id = re.search(r'pageId=(\d+)', api_path).group(1)
            
            # 找函数的docstring
            docstring = ""
            doc_match = re.search(r'"""(.*?)"""', func_body, re.DOTALL)
            if doc_match:
                docstring = doc_match.group(1).strip().split("\n")[0]
            
            results.append({
                "func_name": func_name,
                "api_path": clean_path,
                "page_id": page_id,
                "docstring": docstring,
                "implemented": True,
            })
    
    return results


# ── 2. 从 Playwright 扫描结果加载 ──

def load_playwright_apis():
    scan_path = PROJECT / "data" / "api_scan" / "playwright_api_scan.json"
    if not scan_path.exists():
        return {}
    data = json.loads(scan_path.read_text("utf-8"))
    return data


# ── 3. 从会话日志 JSON 目录加载预捕获响应 ──

def load_precaptured_responses():
    mcp_dir = PROJECT / ".playwright-mcp"
    responses = {}
    for jf in mcp_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text("utf-8"))
            name = jf.stem
            # 提取响应结构
            result_data = data.get("resultData", {})
            datas = result_data.get("datas", {})
            
            # 获取顶层key
            if isinstance(datas, dict):
                top_keys = list(datas.keys())[:10]
            elif isinstance(datas, list):
                top_keys = [f"list[{len(datas)}]"]
            else:
                top_keys = []
            
            responses[name] = {
                "top_keys": top_keys,
                "success": data.get("success"),
                "result_code": data.get("resultCode"),
                "sample": json.dumps(datas, ensure_ascii=False)[:1000],
            }
        except:
            pass
    return responses


# ── 4. 生成文档 ──

def generate_doc(implemented, playwright_apis, precaptured):
    lines = []
    lines.append("# 京东金融基金 API 接口完整文档")
    lines.append("")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 数据源: jd_finance_api.py 代码 + Playwright 抓包 + MCP 会话日志")
    lines.append(f"> 已实现接口: {len(implemented)} 个 | Playwright 发现: {len(playwright_apis)} 个 | 预捕获响应: {len(precaptured)} 个")
    lines.append("")
    lines.append("## API 基础信息")
    lines.append("")
    lines.append("### 请求地址")
    lines.append("")
    lines.append("| Base URL | 说明 |")
    lines.append("|----------|------|")
    lines.append("| `https://ms.jr.jd.com` | 主 API 网关 (gw/generic/...) |")
    lines.append("| `https://ms2.jd.com` | 备用 API 网关 (gw2/generic/...) |")
    lines.append("| `https://jdjr.jd.com` | 京东金融 PC 站 |")
    lines.append("| `https://lc.jr.jd.com` | 基金交易 H5 页面 |")
    lines.append("")
    lines.append("### 请求方式")
    lines.append("")
    lines.append('- **POST** (大多数 API): 使用 `application/x-www-form-urlencoded`，body 为 `reqData={"key":"value"}` 格式的 JSON 字符串')
    lines.append("- **GET** (部分 API): 参数通过 URL query string 传递")
    lines.append("- **Cookie**: 大部分基金数据接口不需要 cookie；用户持仓、交易记录等需要登录 cookie")
    lines.append("- **Referer/Origin**: 部分新端点需要 `Referer: https://jdjr.jd.com/`")
    lines.append("")
    lines.append("### 响应格式")
    lines.append("")
    lines.append("```json")
    lines.append('{')
    lines.append('  "success": true,')
    lines.append('  "resultCode": "0000",')
    lines.append('  "resultMessage": "操作成功",')
    lines.append('  "resultData": {')
    lines.append('    "datas": { ... }  // 核心数据')
    lines.append('  }')
    lines.append('}')
    lines.append("```")
    lines.append("")
    
    # ── 按类别整理 ──
    
    categories = {
        "fund_detail": {"name": "基金详情", "apis": []},
        "fund_nav": {"name": "基金净值与走势", "apis": []},
        "fund_ranking": {"name": "基金排行与筛选", "apis": []},
        "fund_trade": {"name": "交易规则与费率", "apis": []},
        "fund_holdings": {"name": "持仓分布与穿透", "apis": []},
        "fund_manager": {"name": "基金经理", "apis": []},
        "fund_announcement": {"name": "基金公告与诊断", "apis": []},
        "user": {"name": "用户持仓与交易记录", "apis": []},
        "community": {"name": "社区与关注", "apis": []},
        "market": {"name": "行情与指数", "apis": []},
        "auth": {"name": "认证与登录", "apis": []},
        "wealth": {"name": "财富管理与营销", "apis": []},
        "other": {"name": "其他", "apis": []},
    }
    
    def categorize(api_path):
        p = api_path.lower()
        if "detail" in p and "fund" in p: return "fund_detail"
        if "netvalue" in p or "nav" in p or "profit" in p or "chart" in p or "performance" in p: return "fund_nav"
        if "rank" in p or "label" in p or "getpagemu" in p: return "fund_ranking"
        if "trade" in p or "fee" in p or "rules" in p or "traderule" in p: return "fund_trade"
        if "holding" in p or "investment" in p or "distribution" in p: return "fund_holdings"
        if "manager" in p: return "fund_manager"
        if "notice" in p or "announcement" in p or "diagnosis" in p or "diagnos" in p: return "fund_announcement"
        if "holding" in p and "user" in p or "userinfo" in p or "trade" in p and "record" in p: return "user"
        if "circle" in p or "follow" in p or "feed" in p or "jimu" in p: return "community"
        if "index" in p or "valuation" in p or "block" in p or "quote" in p or "gold" in p: return "market"
        if "cookie" in p or "token" in p or "rsa" in p or "login" in p or "publickey" in p: return "auth"
        if "wealth" in p or "caifu" in p or "coupon" in p or "notify" in p: return "wealth"
        return "other"
    
    # 收集所有唯一API
    all_apis = {}  # {path: {func, implemented, post_data, source}}
    
    for impl in implemented:
        path = impl["api_path"]
        if path not in all_apis:
            all_apis[path] = {
                "func_name": impl["func_name"],
                "docstring": impl["docstring"],
                "implemented": True,
                "page_id": impl.get("page_id", ""),
                "sources": ["代码"],
            }
    
    for path, info in playwright_apis.items():
        if path not in all_apis:
            all_apis[path] = {
                "func_name": "",
                "docstring": "",
                "implemented": False,
                "post_data": info.get("post_data", ""),
                "sources": ["Playwright"],
            }
        else:
            if "Playwright" not in all_apis[path]["sources"]:
                all_apis[path]["sources"].append("Playwright")
    
    # 从会话日志提取的API路径也需要加入
    session_catalog_path = PROJECT / "data" / "api_scan" / "api_catalog_from_sessions.json"
    if session_catalog_path.exists():
        session_data = json.loads(session_catalog_path.read_text("utf-8"))
        for cat_name, apis in session_data.get("apis", {}).items():
            for api_info in apis:
                path = api_info["path"]
                # 只处理有效路径
                if not path.startswith("/gw"):
                    continue
                # 去掉查询参数
                clean_path = path.split("?")[0]
                if clean_path not in all_apis:
                    all_apis[clean_path] = {
                        "func_name": "",
                        "docstring": "",
                        "implemented": False,
                        "sources": ["会话日志"],
                    }
                elif "会话日志" not in all_apis[clean_path]["sources"]:
                    all_apis[clean_path]["sources"].append("会话日志")
    
    # 分类
    for path, info in all_apis.items():
        cat = categorize(path)
        # 匹配预捕获响应
        api_name = path.split("/")[-1].split("?")[0]
        precaptured_match = None
        for pc_name, pc_data in precaptured.items():
            if api_name.lower() in pc_name.lower() or pc_name.lower() in api_name.lower():
                precaptured_match = (pc_name, pc_data)
                break
        
        categories[cat]["apis"].append({
            "path": path,
            "info": info,
            "precaptured": precaptured_match,
        })
    
    # 生成各分类章节
    lines.append("## 目录")
    lines.append("")
    for cat_key, cat in categories.items():
        if cat["apis"]:
            lines.append(f"- [{cat['name']}](#{cat_key}) ({len(cat['apis'])} 个)")
    lines.append("")
    
    for cat_key, cat in categories.items():
        if not cat["apis"]:
            continue
        lines.append(f"## {cat['name']}")
        lines.append("")
        
        for item in sorted(cat["apis"], key=lambda x: x["path"]):
            path = item["path"]
            info = item["info"]
            status = "✅ 已实现" if info["implemented"] else "🆕 未实现"
            
            lines.append(f"### `{path}`")
            lines.append("")
            lines.append(f"- **状态**: {status}")
            lines.append(f"- **来源**: {', '.join(info['sources'])}")
            if info.get("func_name"):
                lines.append(f"- **封装函数**: `{info['func_name']}()`")
            if info.get("docstring"):
                lines.append(f"- **说明**: {info['docstring']}")
            if info.get("page_id"):
                lines.append(f"- **PageId**: {info['page_id']}")
            if info.get("post_data"):
                lines.append(f"- **请求参数示例**: `{info['post_data'][:200]}`")
            
            # 添加预捕获响应
            if item["precaptured"]:
                pc_name, pc_data = item["precaptured"]
                lines.append(f"- **响应文件**: `.playwright-mcp/{pc_name}.json`")
                lines.append(f"- **响应顶层字段**: `{', '.join(pc_data['top_keys'])}`")
                if pc_data.get("sample"):
                    lines.append(f"- **响应示例**:")
                    lines.append("  ```json")
                    lines.append(f"  {pc_data['sample'][:500]}")
                    lines.append("  ```")
            
            lines.append("")
    
    # ── 调用示例 ──
    lines.append("## 调用示例")
    lines.append("")
    lines.append("### Python (使用 jd_finance_api.py)")
    lines.append("")
    lines.append("```python")
    lines.append("import sys")
    lines.append("sys.path.insert(0, '.')")
    lines.append("from tools.jd_finance_api import (")
    lines.append("    get_fund_detail,           # 基金详情(一站式)")
    lines.append("    get_fund_chart_data,       # 走势图+全量净值")
    lines.append("    get_fund_trade_rules,      # 交易规则")
    lines.append("    get_fund_holdings_distribution,  # 持仓分布")
    lines.append("    get_fund_performance,      # 业绩排名")
    lines.append("    get_fund_manager_list,     # 经理列表")
    lines.append("    get_user_holdings,         # 用户持仓(需登录)")
    lines.append("    get_trading_records,       # 交易记录(需登录)")
    lines.append("    get_fund_ranking_list,     # 基金排行")
    lines.append("    get_index_block_info,      # 指数板块信息")
    lines.append("    get_index_valuation,       # 指数估值趋势")
    lines.append("    get_stock_quotes,          # 股票实时行情")
    lines.append(")")
    lines.append("")
    lines.append("# 1. 获取基金详情 (一站式, 含净值/业绩/持仓/经理/走势图)")
    lines.append("detail = get_fund_detail('110020')")
    lines.append("print(detail['profile']['full_name'])  # 基金全称")
    lines.append("print(detail['chart']['chart_points'][-1])  # 最新净值点")
    lines.append("")
    lines.append("# 2. 获取全量历史净值 (用于增量更新)")
    lines.append("chart = get_fund_chart_data('110020', full_history=True)")
    lines.append("nav_pts = chart['chart_points_full']  # 全量累计收益率%")
    lines.append("")
    lines.append("# 3. 获取用户持仓 (需要 cookie)")
    lines.append("holdings = get_user_holdings(target_uid='17533758')")
    lines.append("for h in holdings.get('holdings', []):")
    lines.append("    print(h['fund_name'], h['market_value'])")
    lines.append("```")
    lines.append("")
    lines.append("### 直接调用 API (底层)")
    lines.append("")
    lines.append("```python")
    lines.append("from tools.jd_finance_api import _api_post, _api_form, _ensure_cookies")
    lines.append("")
    lines.append("cookies = _ensure_cookies()")
    lines.append("")
    lines.append("# POST 请求 (JSON body)")
    lines.append("data = _api_post('gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo',")
    lines.append('    {"fundCode": "110020", "pageNum": 1, "pageSize": 20},')
    lines.append("    cookies=cookies)")
    lines.append("nav_list = data['resultData']['datas']['netValueList']")
    lines.append("")
    lines.append("# POST 请求 (Form body, 用于 gw2 端点)")
    lines.append("data = _api_form('gw2/generic/jj/h5/m/queryFullRanking',")
    lines.append('    {"fundType": "gp", "sortColumn": "1n", "pageSize": 50},')
    lines.append("    cookies=cookies)")
    lines.append("```")
    lines.append("")
    
    # ── 新发现的高价值接口 ──
    lines.append("## 🆕 新发现的高价值接口（建议实现）")
    lines.append("")
    lines.append("以下接口在 Playwright 抓包和会话日志中被发现，但尚未在 `jd_finance_api.py` 中实现:")
    lines.append("")
    
    high_value_new = []
    for path, info in all_apis.items():
        if not info["implemented"]:
            cat = categorize(path)
            api_name = path.split("/")[-1]
            # 过滤掉噪音（重复的feedFlow等）
            if "feedflow" in path.lower():
                continue
            if path.endswith("\\") or path.endswith("\\\\"):
                continue
            high_value_new.append((cat, path, api_name))
    
    # 按类别分组
    new_by_cat = {}
    for cat, path, name in high_value_new:
        new_by_cat.setdefault(cat, []).append((path, name))
    
    cat_names = {
        "fund_detail": "基金详情",
        "fund_nav": "基金净值与走势",
        "fund_ranking": "基金排行与筛选",
        "fund_trade": "交易规则与费率",
        "fund_holdings": "持仓分布与穿透",
        "fund_manager": "基金经理",
        "fund_announcement": "基金公告与诊断",
        "user": "用户相关",
        "community": "社区与关注",
        "market": "行情与指数",
        "auth": "认证",
        "wealth": "财富管理",
        "other": "其他",
    }
    
    for cat in sorted(new_by_cat.keys()):
        lines.append(f"### {cat_names.get(cat, cat)}")
        lines.append("")
        lines.append("| API 路径 | 接口名 |")
        lines.append("|----------|--------|")
        seen = set()
        for path, name in sorted(new_by_cat[cat]):
            if path not in seen:
                lines.append(f"| `{path}` | {name} |")
                seen.add(path)
        lines.append("")
    
    return "\n".join(lines)


def main():
    print("提取已实现接口...")
    implemented = extract_implemented_apis()
    print(f"  找到 {len(implemented)} 个已实现接口调用")
    
    print("加载 Playwright 扫描结果...")
    playwright_apis = load_playwright_apis()
    print(f"  找到 {len(playwright_apis)} 个 Playwright 发现的接口")
    
    print("加载预捕获 JSON 响应...")
    precaptured = load_precaptured_responses()
    print(f"  找到 {len(precaptured)} 个预捕获响应")
    
    print("生成文档...")
    doc = generate_doc(implemented, playwright_apis, precaptured)
    
    out_path = PROJECT / "docs" / "jd_finance_api_complete.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(f"\n文档已生成: {out_path}")
    print(f"文档大小: {len(doc)} 字符")


if __name__ == "__main__":
    main()
