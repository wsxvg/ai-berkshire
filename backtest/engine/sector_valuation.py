"""行业估值维度 — 用于回测的五维评分第六维增强。

基于京东金融 getIndexBlockInfo API 获取的 CSI 行业指数 PE/PB 历史百分位（2016至今），
在回测中对基金所属行业进行估值过滤，防止在行业过热时高位接盘。

当前支持 3 个行业指数：
  H30184.CSI  半导体      (68只基金)
  930712.CSI  有色金属     (28只基金)
  930713.CSI  煤炭         (~5只基金)
"""

import json
from pathlib import Path
from datetime import datetime

# 基金关键词 → 行业指数
FUND_KEYWORD_TO_INDEX = {
    "半导体": "H30184.CSI",
    "芯片": "H30184.CSI",
    "科技": "H30184.CSI",       # 宽泛匹配，优先级低
    "电子": "H30184.CSI",
    "集成电路": "H30184.CSI",
    "有色金属": "930712.CSI",
    "金属": "930712.CSI",
    "矿产": "930712.CSI",
    "黄金": "930712.CSI",
    "煤炭": "930713.CSI",
}

# 关键词匹配优先级（长关键词优先，避免"新能源"匹配到"能源"）
KEYWORD_PRIORITY = sorted(FUND_KEYWORD_TO_INDEX.keys(), key=lambda k: -len(k))


def load_industry_data():
    """加载行业PE/PB历史数据"""
    p = Path(__file__).parent.parent.parent / "data" / "industry_valuation.json"
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def map_fund_to_industry(fund_name):
    """根据基金名称关键词映射到行业指数代码"""
    for kw in KEYWORD_PRIORITY:
        if kw in fund_name:
            return FUND_KEYWORD_TO_INDEX[kw]
    return None


def get_industry_pe_percentile(index_code, cutoff_date, industry_data):
    """获取截止到 cutoff_date 的 PE 百分位。

    在历史 PE 记录中查找日期 ≤ cutoff_date 的最近一条记录。
    返回 PE 百分位（0-100），数据不足返回 None。
    """
    if not index_code or index_code not in industry_data:
        return None
    pe_history = industry_data[index_code].get("pe_history", [])
    if not pe_history:
        return None

    # 二分查找最近日期
    target = cutoff_date[:10]
    best = None
    for p in pe_history:
        d = p.get("date", "")[:10]
        if d <= target:
            best = p
        else:
            break
    if best is None:
        return None
    return best.get("pe_pct")


def score_sector_valuation_backtest(fund_code, fund_name, cutoff_date, industry_data):
    """行业估值评分：基于截止日 PE 百分位进行估值过滤。

    规则：
    - PE百分位 > 80: 严重高估，扣 1.5 分
    - PE百分位 > 70: 高估，扣 1.0 分
    - PE百分位 > 60: 偏贵，扣 0.5 分
    - PE百分位 < 30: 低估，加 0.5 分
    - PE百分位 < 20: 严重低估，加 1.0 分
    - 无数据: 0 分（不干预）

    返回：修正值（正=加分，负=扣分）
    """
    index_code = map_fund_to_industry(fund_name)
    if not index_code:
        return 0.0

    pe_pct = get_industry_pe_percentile(index_code, cutoff_date, industry_data)
    if pe_pct is None:
        return 0.0

    # 估值评分
    if pe_pct > 80:
        return -1.5   # 严重高估，强力拦截
    elif pe_pct > 70:
        return -1.0   # 高估
    elif pe_pct > 60:
        return -0.5   # 偏贵
    elif pe_pct < 20:
        return 1.0    # 严重低估，鼓励买入
    elif pe_pct < 30:
        return 0.5    # 低估
    else:
        return 0.0    # 中性估值


def test_coverage(fund_codes, fund_name_map):
    """测试基金覆盖率"""
    total = len(fund_codes)
    matched = 0
    by_industry = {}
    for code in fund_codes:
        name = fund_name_map.get(code, code)
        idx = map_fund_to_industry(name)
        if idx:
            matched += 1
            by_industry.setdefault(idx, []).append(code)

    print(f"基金覆盖率: {matched}/{total} ({matched/total*100:.1f}%)")
    for idx, codes in by_industry.items():
        print(f"  {idx}: {len(codes)} 只")
    return matched / total if total > 0 else 0
