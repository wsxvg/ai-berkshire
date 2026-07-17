#!/usr/bin/env python3
"""LLM Skill 自动化集成模块

将 fund-checklist、fund-penetration、fund-analyze 三个 Skill 整合为
自动化调用管道，供 daily_live_enhanced.py 和回测引擎使用。

功能：
1. 自动获取基金数据（档案/持仓/经理/费率/业绩）
2. 执行规则化六关检查（不需要LLM的部分）
3. 生成结构化 Skill 输入（供 IDE 中的 AI 执行）
4. 缓存分析结果（24小时有效）
5. 批量分析多只基金

Usage:
    # 单只基金分析
    py -3.10 tools/llm_skill_integration.py --code 006105

    # 批量分析（从评分文件读取TOP5）
    py -3.10 tools/llm_skill_integration.py --top 5

    # 强制刷新缓存
    py -3.10 tools/llm_skill_integration.py --code 006105 --refresh
"""

import json, sys, os, glob, argparse, hashlib, re
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# ── 参数解析 ──
parser = argparse.ArgumentParser(description="LLM Skill 自动化集成")
parser.add_argument("--code", type=str, help="基金代码")
parser.add_argument("--top", type=int, default=0, help="分析评分前N只基金")
parser.add_argument("--market", action="store_true", help="仅输出市场状态分析")
parser.add_argument("--refresh", action="store_true", help="强制刷新缓存")
parser.add_argument("--json", action="store_true", help="输出JSON格式")
args = parser.parse_args()

TODAY = datetime.now().strftime("%Y-%m-%d")
CACHE_DIR = PROJECT / "data" / "skill_cache"
CACHE_TTL_HOURS = 24


# ═══════════════════════════════════════════════════════════
# 数据获取层
# ═══════════════════════════════════════════════════════════

def load_fund_data(code):
    """加载基金全量数据（从缓存）"""
    cache_dir = PROJECT / "data" / "fund_cache"
    
    data = {"code": code}
    
    # 基金档案
    profile_files = list(cache_dir.glob(f"fund_profile_{code}*.json"))
    if profile_files:
        data["profile"] = json.loads(profile_files[0].read_text("utf-8"))
    
    # 交易规则
    rules_files = list(cache_dir.glob(f"trade_rules_{code}*.json"))
    if rules_files:
        data["rules"] = json.loads(rules_files[0].read_text("utf-8"))
    
    # 持仓分布
    holdings_files = list(cache_dir.glob(f"fund_holdings_{code}*.json"))
    if holdings_files:
        data["holdings"] = json.loads(holdings_files[0].read_text("utf-8"))
    
    # 业绩排名
    perf_files = list(cache_dir.glob(f"fund_perf_{code}*.json"))
    if perf_files:
        data["performance"] = json.loads(perf_files[0].read_text("utf-8"))
    
    # 基金经理
    mgr_files = list(cache_dir.glob(f"fund_manager_{code}*.json"))
    if mgr_files:
        data["manager"] = json.loads(mgr_files[0].read_text("utf-8"))
    
    # 净值曲线
    chart_file = PROJECT / "data" / "fund_charts" / f"{code}.json"
    if chart_file.exists():
        data["charts"] = json.loads(chart_file.read_text("utf-8"))
    
    return data


def load_scores():
    """加载评分引擎结果"""
    scores_file = PROJECT / "data" / "cache" / "scores.json"
    if scores_file.exists():
        return json.loads(scores_file.read_text("utf-8"))
    return {}


# ═══════════════════════════════════════════════════════════
# 六关检查（规则化部分，不需要LLM）
# ═══════════════════════════════════════════════════════════

def check_scale(profile):
    """第一关：规模检查"""
    scale_str = profile.get("fund_scale", profile.get("scale", ""))
    if not scale_str:
        return {"pass": True, "score": 3, "note": "规模数据缺失，默认通过"}
    
    nums = re.findall(r'[\d.]+', str(scale_str).replace("亿元", "").replace("亿", ""))
    if nums:
        scale_val = float(nums[0])
        if scale_val < 2:
            return {"pass": False, "score": 1, "note": f"规模{scale_val}亿<2亿，清盘风险"}
        elif scale_val < 5:
            return {"pass": True, "score": 2, "note": f"规模{scale_val}亿偏小"}
        elif scale_val < 50:
            return {"pass": True, "score": 4, "note": f"规模{scale_val}亿适中"}
        else:
            return {"pass": True, "score": 5, "note": f"规模{scale_val}亿充足"}
    return {"pass": True, "score": 3, "note": "规模数据无法解析"}


def check_fees(rules):
    """第二关：费率检查"""
    purchase_fee = float(rules.get("purchase_fee", 0.15) or 0.15)
    manage_fee = float(rules.get("manage_fee", 1.5) or 1.5)
    trustee_fee = float(rules.get("trustee_fee", 0.25) or 0.25)
    
    total = purchase_fee + manage_fee + trustee_fee
    
    if total > 3.5:
        return {"pass": False, "score": 1, "note": f"总费率{total:.2f}%过高"}
    elif total > 2.5:
        return {"pass": True, "score": 2, "note": f"总费率{total:.2f}%偏高"}
    elif total > 1.8:
        return {"pass": True, "score": 3, "note": f"总费率{total:.2f}%适中"}
    else:
        return {"pass": True, "score": 4, "note": f"总费率{total:.2f}%低"}


def check_manager(manager_data):
    """第三关：经理检查"""
    if not manager_data or not manager_data.get("managers"):
        return {"pass": True, "score": 3, "note": "经理数据缺失"}
    
    mgr = manager_data["managers"][0] if manager_data["managers"] else {}
    tenure = mgr.get("tenure", "")
    
    # 解析任职年限
    years = 0
    if "年" in str(tenure):
        nums = re.findall(r'[\d.]+', str(tenure).split("年")[0])
        if nums:
            years = float(nums[0])
    
    if years < 1:
        return {"pass": False, "score": 2, "note": f"任职{years}年<1年，经验不足"}
    elif years < 3:
        return {"pass": True, "score": 3, "note": f"任职{years}年，经验一般"}
    elif years < 5:
        return {"pass": True, "score": 4, "note": f"任职{years}年，经验丰富"}
    else:
        return {"pass": True, "score": 5, "note": f"任职{years}年，经验资深"}


def check_performance(performance):
    """第四关：业绩检查"""
    if not performance:
        return {"pass": True, "score": 3, "note": "业绩数据缺失"}
    
    # 检查近1年排名
    rank_data = performance.get("rank_data", {})
    year1_rank = rank_data.get("year1", {})
    percentile = year1_rank.get("percentile", 50)
    
    if percentile < 25:
        return {"pass": True, "score": 5, "note": f"近1年排名前{percentile:.0f}%优秀"}
    elif percentile < 50:
        return {"pass": True, "score": 4, "note": f"近1年排名前{percentile:.0f}%良好"}
    elif percentile < 75:
        return {"pass": True, "score": 3, "note": f"近1年排名前{percentile:.0f}%一般"}
    else:
        return {"pass": False, "score": 2, "note": f"近1年排名前{percentile:.0f}%落后"}


def check_holdings_concentration(holdings_data):
    """第五关：持仓集中度检查"""
    if not holdings_data:
        return {"pass": True, "score": 3, "note": "持仓数据缺失"}
    
    stocks = holdings_data.get("stocks", [])
    if not stocks:
        return {"pass": True, "score": 3, "note": "无重仓股数据"}
    
    # 前10大重仓股集中度
    top10_weight = sum(float(s.get("weight", 0)) for s in stocks[:10])
    
    if top10_weight > 80:
        return {"pass": True, "score": 2, "note": f"前10大集中度{top10_weight:.1f}%过高"}
    elif top10_weight > 60:
        return {"pass": True, "score": 3, "note": f"前10大集中度{top10_weight:.1f}%偏高"}
    elif top10_weight > 40:
        return {"pass": True, "score": 4, "note": f"前10大集中度{top10_weight:.1f}%适中"}
    else:
        return {"pass": True, "score": 5, "note": f"前10大集中度{top10_weight:.1f}%分散"}


def check_trading_rules(rules):
    """第六关：交易规则检查"""
    issues = []
    
    # T+N 确认天数
    confirm_days = rules.get("confirm_days", 1)
    if confirm_days > 2:
        issues.append(f"T+{confirm_days}确认较慢")
    
    # 限购状态
    purchase_status = rules.get("purchase_status", "开放申购")
    if purchase_status and "开放" not in purchase_status:
        issues.append(f"申购状态: {purchase_status}")
    
    # 日限额
    day_limit = rules.get("day_limit", 99999999)
    if day_limit and day_limit != "Infinity":
        try:
            limit = float(day_limit)
            if limit < 1000:
                issues.append(f"日限额{limit}元过低")
            elif limit < 10000:
                issues.append(f"日限额{limit}元偏低")
        except:
            pass
    
    # 惩罚性赎回费
    short_term_fee = rules.get("short_term_redeem_fee", 1.5)
    if short_term_fee and float(short_term_fee or 1.5) >= 1.5:
        issues.append(f"持有<7天赎回费{short_term_fee}%")
    
    if issues:
        return {"pass": True, "score": 2, "note": "; ".join(issues)}
    else:
        return {"pass": True, "score": 4, "note": "交易规则正常"}


# ═══════════════════════════════════════════════════════════
# Skill 调用生成器
# ═══════════════════════════════════════════════════════════

def generate_skill_commands(code, checklist_result):
    """生成LLM Skill调用指令"""
    commands = []
    
    # 基本分析（总是生成）
    commands.append({
        "skill": "fund-checklist",
        "command": f"fund-checklist {code}",
        "description": "六关检查完整分析",
        "priority": 1,
    })
    
    # 穿透分析（如果有持仓数据）
    if checklist_result.get("has_holdings"):
        commands.append({
            "skill": "fund-penetration",
            "command": f"穿透分析 {code}",
            "description": "底层重仓股穿透分析",
            "priority": 2,
        })
    
    # 综合分析（如果评分较低或有关注点）
    if checklist_result.get("overall_score", 3) < 3.5:
        commands.append({
            "skill": "fund-analyze",
            "command": f"基金综合分析 {code}",
            "description": "AI深度解读评分原因",
            "priority": 3,
        })
    
    # 卖出分析（如果已持有）
    if checklist_result.get("is_held"):
        commands.append({
            "skill": "fund-sell",
            "command": f"基金卖出分析 {code}",
            "description": "持有基金卖出时机判断",
            "priority": 4,
        })
    
    return commands


# ═══════════════════════════════════════════════════════════
# 前视偏差防护层
# ═══════════════════════════════════════════════════════════

def generate_anti_lookahead_prompt(cutoff_date, fund_codes=None):
    """生成 LLM 调用时的防前视偏差约束文本
    
    在每次 LLM Skill 调用前，将此文本附加到 prompt 中，
    确保 LLM 不会使用 cutoff_date 之后的信息。
    
    Args:
        cutoff_date: 截止日期 (YYYY-MM-DD)
        fund_codes: 涉及的基金代码列表
        
    Returns:
        str: 可直接嵌入 LLM prompt 的约束文本
    """
    lines = [
        "",
        "---",
        "## 时间防火墙（必须严格遵守）",
        "",
        f"当前分析截止日期: **{cutoff_date}**",
        "",
        "以下行为被禁止：",
        f"1. 禁止使用 {cutoff_date} 之后的任何价格、净值、收益率数据",
        f"2. 禁止使用 {cutoff_date} 之后的任何新闻、公告、财报",
        f"3. 禁止使用 {cutoff_date} 之后的基金经理变更信息",
        f"4. 禁止联网搜索或调用任何外部 API 获取 {cutoff_date} 之后的数据",
        "5. 禁止讨论或引用「后来发生的事」「最终结果」等前瞻性描述",
        "",
        "允许的信息来源：",
        "- 本地缓存文件（data/fund_cache/*.json）中的所有历史数据",
        "- 本地基金净值曲线（fund_charts.json）中 ≤ cutoff_date 的数据",
        "- 本地交易记录（trading_by_date_fixed.json）中 ≤ cutoff_date 的记录",
        "- 京东金融 API 提供的当前快照数据（不包含未来预测）",
        "",
        "如果某个判断需要 {cutoff_date} 之后的数据才能做出，请明确说「该判断需要未来数据，无法在当前日期做出」而非尝试猜测。""",
        "---",
        "",
    ]
    return "\n".join(lines)


def generate_skill_call_context(fund_code, fund_data, cutoff_date=None):
    """生成单只基金的 Skill 调用上下文（含防前视偏差约束）
    
    整合了基金全量数据 + 市场状态 + 时间防火墙。
    这是 daily_live_enhanced.py 调用 LLM Skill 前的标准输入。
    
    Args:
        fund_code: 基金代码
        fund_data: load_fund_data() 返回的完整基金数据
        cutoff_date: 可选截止日期，默认为当天
        
    Returns:
        dict: 包含 market, fund, constraints 三个 section
    """
    if cutoff_date is None:
        cutoff_date = datetime.now().strftime("%Y-%m-%d")
    
    market = detect_market_state_extended()
    constraints = generate_anti_lookahead_prompt(cutoff_date, [fund_code])
    
    profile = fund_data.get("profile", {})
    rules = fund_data.get("rules", {})
    performance = fund_data.get("performance", {})
    manager = fund_data.get("manager", {})
    holdings = fund_data.get("holdings", {})
    
    # 只保留 cutoff_date 之前的业绩数据
    filtered_perf = {}
    if performance:
        for k, v in performance.items():
            # 如果是带日期的数据，检查日期
            if isinstance(v, dict) and "date" in v:
                if str(v.get("date", "")) <= cutoff_date:
                    filtered_perf[k] = v
            else:
                filtered_perf[k] = v
    
    return {
        "cutoff_date": cutoff_date,
        "fund_code": fund_code,
        "fund_name": profile.get("fund_name", profile.get("name", fund_code)),
        "market": market,
        "fund_data": {
            "profile": profile,
            "rules": rules,
            "performance": filtered_perf,
            "manager": manager,
            "holdings": holdings,
        },
        "constraints": constraints,
        "skill_commands": generate_skill_commands(fund_code, {
            "has_holdings": bool(holdings),
            "overall_score": 0,  # 由调用方在 analyze_fund 中填充
            "is_held": False,
        }),
    }


# ═══════════════════════════════════════════════════════════
# 市场状态分析（多时间框架 + 估值分位）
# ═══════════════════════════════════════════════════════════

def detect_market_state_extended():
    """多时间框架市场状态检测：60日/120日/250日 + 估值分位
    
    比引擎内置的60日单一维度更全面，专门为 LLM 分析提供宏观环境上下文。
    
    Returns:
        dict: 市场状态快照，可直接嵌入 LLM prompt
    """
    charts_path = PROJECT / "backtest" / "data" / "fund_charts.json"
    if not charts_path.exists():
        return {"error": "fund_charts.json not found"}
    
    charts = json.loads(charts_path.read_text("utf-8"))
    benchmark_code = "110020"  # 沪深300ETF联接
    
    pts = charts.get(benchmark_code, [])
    if not pts:
        return {"error": f"benchmark {benchmark_code} not in fund_charts"}
    
    # 提取 yAxis 序列（累计收益率%）
    yvals = [(p["xAxis"], (100 + _safe_float(p.get("yAxis", 0))) / 100) for p in pts]
    yvals.sort(key=lambda x: x[0])
    
    now_date = yvals[-1][0] if yvals else TODAY
    now_nav = yvals[-1][1] if yvals else 100
    
    # 多时间框架收益率（用日历日近似交易日）
    def _return_over_days(days):
        """回溯 days 个日历日，取最近的数据点"""
        target_date = (datetime.strptime(now_date, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
        # 找 >= target_date 的第一个点
        prev_val = None
        for d, v in yvals:
            if d >= target_date:
                prev_val = v
                break
        if prev_val is None and yvals:
            prev_val = yvals[0][1]
        if prev_val is None or prev_val <= 0:
            return None
        return (now_nav / prev_val - 1) * 100
    
    ret_60d = _return_over_days(60)
    ret_120d = _return_over_days(120)
    ret_250d = _return_over_days(250)  # ~1年
    
    # 估值分位：当前净值在历史范围中的位置
    all_navs = [v for _, v in yvals]
    if len(all_navs) > 250:
        hist_high = max(all_navs)
        hist_low = min(all_navs)
        pct_250d = sum(1 for v in all_navs[-250:] if v <= now_nav) / min(250, len(all_navs)) * 100
        pct_all = sum(1 for v in all_navs if v <= now_nav) / len(all_navs) * 100
    else:
        hist_high, hist_low = now_nav, now_nav
        pct_250d, pct_all = 50, 50
    
    # 波动率：近60日日收益率标准差年化
    vol_60d = 0
    if len(yvals) > 60:
        recent = yvals[-60:]
        daily_rets = [(recent[i][1] / recent[i-1][1] - 1) for i in range(1, len(recent))]
        if daily_rets:
            mean_ret = sum(daily_rets) / len(daily_rets)
            var = sum((r - mean_ret) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
            vol_60d = (var ** 0.5) * (252 ** 0.5) * 100
    
    # ── 市场状态分类 ──
    regime, regime_desc, suggested_position = _classify_regime(
        ret_60d, ret_120d, ret_250d, pct_250d, vol_60d
    )
    
    return {
        "date": now_date,
        "benchmark": f"沪深300ETF联接({benchmark_code})",
        "returns": {
            "近60日": f"{ret_60d:+.1f}%" if ret_60d is not None else "N/A",
            "近120日": f"{ret_120d:+.1f}%" if ret_120d is not None else "N/A",
            "近1年": f"{ret_250d:+.1f}%" if ret_250d is not None else "N/A",
        },
        "returns_raw": {
            "d60": round(ret_60d, 2) if ret_60d is not None else None,
            "d120": round(ret_120d, 2) if ret_120d is not None else None,
            "d250": round(ret_250d, 2) if ret_250d is not None else None,
        },
        "valuation": {
            "当前净值": f"{now_nav:.4f}",
            "近1年分位": f"{pct_250d:.0f}%",
            "历史全分位": f"{pct_all:.0f}%",
            "估值状态": "高估" if pct_250d > 80 else ("低估" if pct_250d < 20 else "适中"),
        },
        "valuation_raw": {
            "pct_250d": round(pct_250d, 1),
            "pct_all": round(pct_all, 1),
            "is_expensive": pct_250d > 80,
            "is_cheap": pct_250d < 20,
        },
        "volatility": {
            "年化波动率": f"{vol_60d:.1f}%",
            "波动状态": "高波动" if vol_60d > 25 else ("低波动" if vol_60d < 12 else "正常"),
        },
        "volatility_raw": round(vol_60d, 1),
        "regime": regime,
        "regime_description": regime_desc,
        "suggested_position": suggested_position,
    }


def _safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _classify_regime(ret_60d, ret_120d, ret_250d, pct_250d, vol_60d):
    """基于多时间框架和估值分位分类市场状态
    
    比引擎内置的 60 日单维度更细粒度。
    """
    if ret_60d is None:
        return "unknown", "数据不足无法判断", "观望"
    
    # 趋势方向
    short_trend = "up" if ret_60d > 0 else "down"
    mid_trend = "up" if (ret_120d or 0) > 0 else "down"
    long_trend = "up" if (ret_250d or 0) > 0 else "down"
    
    # 估值状态
    expensive = pct_250d > 80
    cheap = pct_250d < 20
    high_vol = vol_60d > 25
    
    # ── 分类逻辑 ──
    if short_trend == "up" and mid_trend == "up" and long_trend == "up":
        if expensive:
            regime = "[牛市] 牛市高位"
            desc = "中长期趋势向上，但估值处于近1年高位。继续持有但注意回撤风险。"
            position = "持仓为主，谨慎加仓"
        else:
            regime = "[牛市] 牛市中期"
            if cheap:
                desc = "中长期趋势向上且估值低位，典型的黄金买入窗口。"
                position = "积极加仓"
            else:
                desc = "中长期趋势向上，估值适中。趋势健康，可保持进攻仓位。"
                position = "正常加仓"
    elif short_trend == "up" and (mid_trend == "down" or long_trend == "down"):
        regime = "[震荡] 超跌反弹"
        desc = "短期反弹但中长期趋势仍向下。可能是熊市反弹而非趋势反转，需警惕假突破。"
        position = "试探性建仓，严格止损"
    elif short_trend == "down" and mid_trend == "up" and long_trend == "up":
        regime = "[震荡] 牛市回调"
        desc = "中长期趋势向上，短期回调。如果是正常技术性调整，是加仓良机。"
        if cheap or pct_250d < 40:
            desc += " 估值不贵，回调可能是加仓机会。"
            position = "逢低加仓"
        else:
            position = "持仓观望"
    elif short_trend == "down" and (mid_trend == "up" or long_trend == "up"):
        regime = "[警告] 趋势转弱"
        desc = "短期转弱，中期趋势面临考验。密切观察中期趋势是否破位。"
        if high_vol:
            desc += " 高波动环境下不确定性增加。"
            position = "减仓至半仓"
        else:
            position = "控制仓位，观望"
    elif short_trend == "down" and mid_trend == "down" and long_trend == "down":
        if cheap:
            regime = "[熊市] 熊市底部"
            desc = "全周期下跌但估值已进入低位。可能是定投建仓的好时机，但短期仍可能继续下跌。"
            position = "定投建仓，不宜重仓"
        else:
            regime = "[熊市] 熊市中继"
            desc = "全周期下跌，估值尚未见底。建议观望或轻仓防御。"
            position = "轻仓/空仓观望"
    else:
        regime = "[震荡] 震荡市"
        if high_vol:
            desc = "多时间框架方向不一致，高波动环境下市场缺乏明确方向。"
            position = "高抛低吸，网格交易"
        else:
            desc = "多时间框架方向不一致，低波动横盘整理中。"
            position = "精选个股，控制仓位"
    
    return regime, desc, position


def get_market_context_for_llm():
    """获取可嵌入 LLM prompt 的市场上下文文本"""
    m = detect_market_state_extended()
    if "error" in m:
        return f"市场状态: 无法获取 ({m['error']})"
    
    lines = [
        f"**市场状态快照** ({m['date']})",
        f"",
        f"| 时间框架 | 收益率 |",
        f"|----------|--------|",
    ]
    for period, val in m["returns"].items():
        lines.append(f"| {period} | {val} |")
    
    lines += [
        f"",
        f"- 估值分位: 近1年 {m['valuation']['近1年分位']}，历史 {m['valuation']['历史全分位']} → {m['valuation']['估值状态']}",
        f"- 年化波动率: {m['volatility']['年化波动率']} ({m['volatility']['波动状态']})",
        f"- 市场周期: **{m['regime']}**",
        f"- 判断: {m['regime_description']}",
        f"- 建议仓位: **{m['suggested_position']}**",
        f"",
        f"[警告] 分析基金时请考虑以上宏观环境：牛市中容忍更高估值，熊市中更重视防守。",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 主分析函数
# ═══════════════════════════════════════════════════════════

def analyze_fund(code, force_refresh=False):
    """对单只基金执行完整分析"""
    
    # 检查缓存
    cache_dir = CACHE_DIR / code
    cache_file = cache_dir / f"{TODAY}.json"
    
    if cache_file.exists() and not force_refresh:
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - mtime < timedelta(hours=CACHE_TTL_HOURS):
                return json.loads(cache_file.read_text("utf-8"))
        except:
            pass
    
    # 加载数据
    data = load_fund_data(code)
    profile = data.get("profile", {})
    rules = data.get("rules", {})
    holdings = data.get("holdings", {})
    performance = data.get("performance", {})
    manager = data.get("manager", {})
    
    name = profile.get("fund_name", profile.get("name", code))
    
    # 执行六关检查
    checks = {
        "scale": check_scale(profile),
        "fees": check_fees(rules),
        "manager": check_manager(manager),
        "performance": check_performance(performance),
        "concentration": check_holdings_concentration(holdings),
        "trading_rules": check_trading_rules(rules),
    }
    
    # 计算总分
    scores = [c["score"] for c in checks.values()]
    overall_score = sum(scores) / len(scores) if scores else 3.0
    
    # 判定
    vetoed = any(not c["pass"] for c in checks.values())
    verdict = "veto" if vetoed else ("warn" if overall_score < 3.5 else "pass")
    
    # 生成Skill调用指令
    result = {
        "code": code,
        "name": name,
        "date": TODAY,
        "overall_score": round(overall_score, 2),
        "verdict": verdict,
        "checks": checks,
        "has_holdings": bool(holdings),
        "is_held": False,  # 由调用方设置
        "skill_commands": generate_skill_commands(code, {
            "has_holdings": bool(holdings),
            "overall_score": overall_score,
            "is_held": False,
        }),
        "data_completeness": {
            "has_profile": bool(profile),
            "has_rules": bool(rules),
            "has_holdings": bool(holdings),
            "has_performance": bool(performance),
            "has_manager": bool(manager),
            "has_charts": "charts" in data,
        },
        "raw_data_summary": {
            "fund_type": profile.get("fund_type", ""),
            "fund_scale": profile.get("fund_scale", profile.get("scale", "")),
            "establish_date": profile.get("establish_date", ""),
            "risk_level": profile.get("risk_level", ""),
            "purchase_fee": rules.get("purchase_fee", ""),
            "manage_fee": rules.get("manage_fee", ""),
            "trustee_fee": rules.get("trustee_fee", ""),
            "confirm_days": rules.get("confirm_days", ""),
            "purchase_status": rules.get("purchase_status", ""),
            "day_limit": rules.get("day_limit", ""),
        },
    }
    
    # 缓存
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    
    return result


def analyze_top_n(n=5):
    """分析评分前N只基金（含市场状态上下文）"""
    scores = load_scores()
    if not scores:
        print("[ERROR] 无评分数据，请先运行评分引擎")
        return []
    
    # 获取市场状态（所有基金共用）
    market = detect_market_state_extended()
    
    # 排序取前N
    sorted_funds = sorted(scores.items(), key=lambda x: x[1].get("total", 3), reverse=True)
    top_n = sorted_funds[:n]
    
    results = []
    for code, score_data in top_n:
        result = analyze_fund(code)
        result["scoring_score"] = score_data.get("total", 3)
        results.append(result)
    
    return {"market": market, "funds": results}


# ═══════════════════════════════════════════════════════════
# 输出格式化
# ═══════════════════════════════════════════════════════════

def format_report(result):
    """格式化单只基金分析报告"""
    lines = []
    lines.append(f"### {result['name']} ({result['code']})")
    lines.append(f"**综合评分**: {result['overall_score']:.1f}/5.0 | **判定**: {result['verdict']}")
    lines.append("")
    lines.append("| 关卡 | 评分 | 通过 | 说明 |")
    lines.append("|------|------|------|------|")
    
    for name, check in result["checks"].items():
        passed = "✅" if check["pass"] else "❌"
        lines.append(f"| {name} | ★{check['score']} | {passed} | {check['note']} |")
    
    lines.append("")
    lines.append("**建议执行的 Skill 分析:**")
    for cmd in result.get("skill_commands", []):
        lines.append(f"- `{cmd['command']}` — {cmd['description']}")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def main():
    # ── 仅输出市场状态 ──
    if args.market:
        market = detect_market_state_extended()
        if args.json:
            print(json.dumps(market, ensure_ascii=False, indent=2))
        else:
            print(get_market_context_for_llm())
        return
    
    if args.code:
        result = analyze_fund(args.code, force_refresh=args.refresh)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(format_report(result))
    
    elif args.top > 0:
        data = analyze_top_n(args.top)
        results = data["funds"]
        market = data["market"]
        
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            # 市场状态
            print(get_market_context_for_llm())
            print()
            print("---")
            print()
            
            # 基金分析
            print(f"# LLM Skill 分析报告 — TOP{args.top}")
            print(f"\n> 生成时间: {TODAY}")
            print(f"> 分析基金数: {len(results)}")
            print()
            for r in results:
                print(format_report(r))
                print("---")
                print()
            
            # 市场调整后的建议
            val_raw = market.get("valuation_raw", {})
            is_expensive = val_raw.get("is_expensive", False)
            is_cheap = val_raw.get("is_cheap", False)
            
            if is_expensive:
                market_note = "[警告] 当前估值偏高，建议对高评分基金也只建试探仓（正常仓位的50%），等待回调加仓。"
            elif is_cheap:
                market_note = "[建议] 当前估值偏低，对于通过六关检查的基金可以适当提高仓位（正常仓位的130%）。"
            else:
                market_note = "市场估值适中，按正常仓位执行。"
            
            print(f"## [权衡] 市场调整建议")
            print(market_note)
            print()
            
            # 汇总表
            print("## 汇总")
            print("| 基金 | 评分 | 判定 | 规模 | 费率 | 经理 | 业绩 | 集中度 | 交易 |")
            print("|------|------|------|------|------|------|------|--------|------|")
            for r in results:
                checks = r["checks"]
                print(f"| {r['name'][:15]} ({r['code']}) | {r['overall_score']:.1f} | {r['verdict']} | ★{checks['scale']['score']} | ★{checks['fees']['score']} | ★{checks['manager']['score']} | ★{checks['performance']['score']} | ★{checks['concentration']['score']} | ★{checks['trading_rules']['score']} |")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
