#!/usr/bin/env python3
"""AI Berkshire Fund Scoring Engine (Phase 1)

Five-dimension fund scoring: Quality, Cost, Manager, Momentum, Smart Money.
Zero external dependencies — Python stdlib only (math, json, statistics).

Usage:
    python tools/fund_scorer.py --score 006105
    python tools/fund_scorer.py --batch 002891 018147 008253
    python tools/fund_scorer.py --test-sharpe 006105
"""

import argparse
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

# 统一日志入口（stderr + logs/fund_scorer.log 轮转）
try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("fund_scorer")



def _get_index_valuation(index_code: str = "H30184.CSI") -> dict:
    """Fetch index PE/PB valuation data from JD Finance API.
    Returns {pe_pct, pb_pct, pe, pb, top_title} or None."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        from jd_finance_api import get_index_valuation_trend_chart
        return get_index_valuation_trend_chart(index_code)
    except Exception:
        return None


def _valuation_modifier(val_data: dict = None) -> float:
    """Calculate score modifier based on index valuation.
    PE percentile > 90% → penalty (overheated)
    PE percentile < 20% → bonus (undervalued)
    Returns modifier between -1.0 and +1.0
    """
    if not val_data:
        return 0.0
    try:
        pe_pct = float(val_data.get("pe_percentile", 50) or 50)
        pb_pct = float(val_data.get("pb_percentile", 50) or 50)
        avg_pct = (pe_pct + pb_pct) / 2
        if avg_pct > 90: return -0.5 * (avg_pct - 90) / 10  # -0.0 ~ -0.5
        if avg_pct < 20: return 0.5 * (20 - avg_pct) / 20   # +0.0 ~ +0.5
        return 0.0
    except (ValueError, TypeError):
        return 0.0

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "fund_cache"
RISK_FREE_RATE = 0.025  # Chinese 10-year government bond yield ~2.5%
PURCHASE_DISCOUNT = 0.1  # default purchase fee discount (1折)
COOLDOWN_TRADING_DAYS = 20  # minimum hold before re-evaluating sell


def _read_json(path: Path):
    """Read a JSON file, return None if missing or invalid."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _read_cache(prefix: str, fund_code: str, max_age_days: int = 7):
    """Read a cache file by prefix."""
    # First try unified fund_data cache
    unified = _read_json(CACHE_DIR / f"fund_data_{fund_code}.json")
    if unified:
        fetch_time = unified.get("fetch_time", "")
        if fetch_time:
            try:
                age = (datetime.now() - datetime.fromisoformat(fetch_time)).days
                if age <= max_age_days:
                    # Map prefix to key in unified cache
                    key_map = {
                        "fund_perf": "performance",
                        "fund_profile": "profile",
                        "fund_holdings": "holdings",
                        "trade_rules": "rules",
                        "fund_manager": "manager",
                        "fund_detail": None,  # fund_detail is the raw data
                    }
                    key = key_map.get(prefix)
                    if key and key in unified:
                        return unified[key]
                    if prefix == "fund_detail":
                        return unified
            except (ValueError, TypeError):
                pass

    # Fallback: individual cache file
    path = CACHE_DIR / f"{prefix}_{fund_code}.json"
    return _read_json(path)


@dataclass
class DimensionScore:
    score: float
    weight: float
    freshness_days: int

    @property
    def stale(self) -> bool:
        return self.freshness_days > 90

    def effective_score(self) -> float:
        return self.score * 0.9 if self.stale else self.score


@dataclass
class FundScore:
    fund_code: str
    fund_type: str  # active | passive_index | index_enhanced
    quality: DimensionScore
    cost: DimensionScore
    manager: DimensionScore
    momentum: DimensionScore
    smart_money: DimensionScore
    total: float = 0.0
    stale: bool = False
    verdict: str = "pass"
    risk_points: list = field(default_factory=list)
    falsify_conditions: list = field(default_factory=list)

    def compare(self, previous: "FundScore") -> dict:
        """Compare with previous score. Returns change analysis + action override."""
        total_delta = self.total - previous.total
        dim_deltas = {}
        for name in ["quality", "cost", "manager", "momentum", "smart_money"]:
            curr = getattr(self, name).score
            prev = getattr(previous, name).score
            dim_deltas[name] = curr - prev

        main_driver = max(dim_deltas, key=lambda k: abs(dim_deltas[k]))
        override = None
        # Cooldown: total change < 0.3 AND all dimension changes < 0.5 → no action
        if abs(total_delta) < 0.3 and all(abs(v) < 0.5 for v in dim_deltas.values()):
            override = "hold"
        return {
            "total_delta": total_delta,
            "main_driver": main_driver,
            "dim_deltas": dim_deltas,
            "override": override,
        }

    def compute(self, established_days: int = None, valuation_modifier: float = 0.0):
        dims = [self.quality, self.cost, self.manager, self.momentum, self.smart_money]
        total_weight = sum(d.weight for d in dims)
        raw = sum(d.score * d.weight for d in dims) / total_weight
        penalty = sum((d.score - d.effective_score()) * d.weight for d in dims) / total_weight
        self.total = raw - penalty

        # 估值修正：市场过热减分，低估加分
        self.valuation_note = ""
        if valuation_modifier != 0.0:
            self.total += valuation_modifier
            if valuation_modifier < 0:
                self.valuation_note = f"valuation_overheat: {valuation_modifier:+.2f}"
            else:
                self.valuation_note = f"valuation_undervalue: {valuation_modifier:+.2f}"
        self.stale = any(d.stale for d in dims)

        # Base verdict
        if self.total >= 4.0:
            self.verdict = "buy"
        elif self.total >= 3.3:
            self.verdict = "watch"
        else:
            self.verdict = "pass"

        # Falsify rules (documented in 自主决策系统设计-v1.md 五)
        self.falsify_conditions = []
        stale_count = sum(1 for d in dims if d.stale)
        if stale_count >= 3:
            self.total *= 0.8
            self.falsify_conditions.append(
                f"stale: {stale_count}个维度过期, 总分降权20%")

        if self.smart_money.score == 0:
            self.total = min(self.total, 3.3)
            self.falsify_conditions.append(
                "downgrade: 聪明钱分=0, 总分cap 3.3")

        # 成立不足1年 → pass (no historical data for quality/momentum)
        if established_days is not None and established_days < 365:
            self.total = min(self.total, 2.5)
            self.verdict = "pass"
            self.falsify_conditions.append(
                f"falsify: 成立仅{established_days}天, 无足够历史数据, 裁决: pass")

        # Re-evaluate verdict after falsify
        if self.total >= 4.0:
            self.verdict = "buy"
        elif self.total >= 3.3:
            self.verdict = "watch"
        else:
            self.verdict = "pass"


# ============================================================
# Cache Reader
# ============================================================

def _read_cache(cache_type: str, key: str):
    safe_key = key.replace("/", "_").replace("\\", "_")
    p = CACHE_DIR / f"{cache_type}_{safe_key}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ============================================================
# Sharpe Ratio
# ============================================================

def calc_sharpe(daily_returns: list[float], rf: float = RISK_FREE_RATE) -> float:
    """Calculate annualized Sharpe ratio from daily return series.

    Args:
        daily_returns: list of daily return ratios (e.g. 0.01 = 1%)
        rf: annual risk-free rate (default 2.5%)

    Returns:
        Annualized Sharpe ratio, or 0.0 if insufficient data.
    """
    if len(daily_returns) < 10:
        return 0.0

    mean_daily = statistics.mean(daily_returns)
    std_daily = statistics.stdev(daily_returns)

    if std_daily == 0:
        return 0.0

    annualized_return = mean_daily * 252
    annualized_vol = std_daily * math.sqrt(252)
    sharpe = (annualized_return - rf) / annualized_vol
    return sharpe


def nav_to_daily_returns(nav_series: list[dict]) -> list[float]:
    """Convert NAV dict series to daily return ratios."""
    returns = []
    for i in range(1, len(nav_series)):
        prev = _float(nav_series[i - 1].get("nav"))
        curr = _float(nav_series[i].get("nav"))
        if prev and curr:
            returns.append((curr - prev) / prev)
    return returns


def chart_to_daily_returns(chart_points: list[dict]) -> list[float]:
    """Convert chart yAxis cumulative returns to daily return ratios.

    chart_points have {xAxis: date, yAxis: cumulative_return_pct}.
    First point is always 0%, subsequent points are cumulative.
    """
    if not chart_points or len(chart_points) < 2:
        return []
    returns = []
    prev = _float(chart_points[0].get("yAxis"))
    for i in range(1, len(chart_points)):
        curr = _float(chart_points[i].get("yAxis"))
        if prev is not None and curr is not None:
            returns.append((curr - prev) / 100.0)
        prev = curr
    return returns


def sharpe_to_score(sharpe: float) -> float:
    """Map Sharpe ratio to 0-5 score.

    Reference:
        >2.0  excellent (5.0)
        1.5-2.0 very good (4.0-5.0)
        1.0-1.5 good      (3.0-4.0)
        0.5-1.0 fair      (1.5-3.0)
        0.0-0.5 poor      (0.0-1.5)
        <0     bad        (0.0)
    """
    if sharpe >= 2.0:
        return 5.0
    elif sharpe >= 1.5:
        return 4.0 + (sharpe - 1.5) * 2.0  # 1.5→4.0, 2.0→5.0
    elif sharpe >= 1.0:
        return 3.0 + (sharpe - 1.0) * 2.0  # 1.0→3.0, 1.5→4.0
    elif sharpe >= 0.5:
        return 1.5 + (sharpe - 0.5) * 3.0  # 0.5→1.5, 1.0→3.0
    elif sharpe > 0:
        return sharpe * 3.0  # 0.0→0.0, 0.5→1.5
    else:
        return 0.0


# ============================================================
# Max Drawdown
# ============================================================

def calc_max_drawdown(values: list[float]) -> float:
    """Calculate maximum drawdown from a series of values (as positive %)."""
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def chart_to_nav_index(chart_points: list[dict]) -> list[float]:
    """Convert chart cumulative return % to NAV-like index (base=100)."""
    vals = [_float(p.get("yAxis")) for p in chart_points if _float(p.get("yAxis")) is not None]
    if not vals:
        return []
    return [(100 + v) / 100 * 100 for v in vals]


# ============================================================
# Stock Code Mapping（穿透持仓估值用）
# ============================================================

def _stock_to_unique_code(code: str) -> str:
    """Convert fund holding stock code to JD Finance uniqueCode format.
    Examples: '688041' → 'SH-688041', 'TSM' → 'NASDAQ-TSM', '0700' → 'HK-0700'"""
    code = str(code).strip().upper()
    if code.startswith("SH-") or code.startswith("SZ-") or code.startswith("NASDAQ-") or code.startswith("HK-"):
        return code
    if code.startswith("6") or code.startswith("5"):
        return f"SH-{code}"
    if code.startswith("0") or code.startswith("3") or code.startswith("2"):
        return f"SZ-{code}"
    if re.match(r'^[A-Z][A-Z.]+$', code):
        return f"NASDAQ-{code}"
    if code.startswith("H") or re.match(r'^\d{5}$', code):
        return f"HK-{code}"
    return code


def score_penetration_valuation(holdings_data: dict = None) -> float:
    """Score fund's top 10 holdings valuation (PE/PB).
    Returns 0-5 score, or 3.0 if no data."""
    if not holdings_data:
        return 3.0

    top_stocks = holdings_data.get("top_stocks", [])
    if not top_stocks:
        return 3.0

    try:
        from tools.jd_finance_api import get_stock_quotes_extended
    except ImportError:
        return 3.0

    # Build unique codes
    codes = []
    name_map = {}
    for s in top_stocks[:10]:
        raw_code = s.get("code", "") or s.get("stock_code", "") or ""
        if raw_code:
            uc = _stock_to_unique_code(raw_code)
            codes.append(uc)
            name_map[uc] = s.get("name", "")

    if not codes:
        return 3.0

    quotes = get_stock_quotes_extended(codes)
    if not quotes:
        return 3.0

    # Compute weighted PE/PB
    total_ratio = 0.0
    weighted_pe = 0.0
    weighted_pb = 0.0
    stock_count = 0

    for s, uc in zip(top_stocks, codes):
        q = quotes.get(uc, {})
        ratio = _float(s.get("ratio", 0))
        pe = q.get("pe_ratio", 0)
        pb = q.get("pb_ratio", 0)
        if pe > 0 and ratio > 0:
            weighted_pe += pe * (ratio / 100)
            weighted_pb += pb * (ratio / 100)
            total_ratio += ratio / 100
            stock_count += 1

    if stock_count == 0 or total_ratio == 0:
        return 3.0

    avg_pe = weighted_pe / total_ratio
    avg_pb = weighted_pb / total_ratio

    # Score: lower PE/PB = cheaper = higher score
    # For equity/tech funds which typically have higher PE:
    if avg_pe <= 20:
        pe_score = 5.0
    elif avg_pe <= 40:
        pe_score = 4.0
    elif avg_pe <= 60:
        pe_score = 3.0
    elif avg_pe <= 100:
        pe_score = 2.0
    else:
        pe_score = 1.0

    if avg_pb <= 3:
        pb_score = 5.0
    elif avg_pb <= 6:
        pb_score = 4.0
    elif avg_pb <= 10:
        pb_score = 3.0
    elif avg_pb <= 15:
        pb_score = 2.0
    else:
        pb_score = 1.0

    return pe_score * 0.5 + pb_score * 0.5


# ============================================================
# Quality Score
# ============================================================

def _float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(str(v).replace("%", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def scale_penalty(scale_text: str) -> float:
    """Nonlinear scale penalty multiplier for active funds.
    100-200亿 ×0.9, 200-500亿 ×0.8, >500亿 ×0.7."""
    if not scale_text:
        return 1.0
    s = str(scale_text).replace(",", "").replace(" ", "")
    import re
    nums = re.findall(r"[\d.]+", s)
    if not nums:
        return 1.0
    val = float(nums[0])
    if "万" in s and "亿" not in s:
        val /= 10000
    # If no unit specified, assume 亿 (common for fund scale)
    if val <= 100:
        return 1.0
    elif val <= 200:
        return 0.9
    elif val <= 500:
        return 0.8
    else:
        return 0.7


def score_quality(perf_data: dict, nav_index: list[float] = None,
                  daily_returns: list[float] = None,
                  scale_text: str = None,
                  holdings_data: dict = None) -> DimensionScore:
    perf_list = perf_data.get("performance", []) if perf_data else []

    perf_map = {}
    for p in perf_list:
        perf_map[p.get("period", "")] = p

    # 1y rank (30%)
    rank_1y = perf_map.get("近1年", {}).get("rank_pct")
    score_1y = max(0, 5 * (1 - rank_1y)) if rank_1y is not None else 2.5

    # 3y rank (25%)
    rank_3y = perf_map.get("近3年", {}).get("rank_pct")
    score_3y = max(0, 5 * (1 - rank_3y)) if rank_3y is not None else 2.5

    # Max drawdown (20%)
    if nav_index and len(nav_index) >= 2:
        max_dd = calc_max_drawdown(nav_index)
    else:
        max_dd = 15.0

    if max_dd <= 10:
        score_dd = 5.0
    elif max_dd <= 15:
        score_dd = 4.0
    elif max_dd <= 20:
        score_dd = 3.0
    elif max_dd <= 30:
        score_dd = 2.0
    else:
        score_dd = 1.0

    # 机构持有比例 removed; redistributed to remaining metrics
    # 1y=30%, 3y=25%, max_dd=20%, scale_stability=15%, sharpe=10%
    sharpe_val = calc_sharpe(daily_returns) if daily_returns and len(daily_returns) >= 10 else 0
    score_sharpe = sharpe_to_score(sharpe_val)
    # Valuation: 10% (穿透持仓PE/PB)
    val_score = score_penetration_valuation(holdings_data)

    # 短期过热惩罚: 近3月涨幅极端过高 → 扣分
    heat_penalty = 0.0
    if nav_index and len(nav_index) >= 60:
        recent_3m = nav_index[-1] / nav_index[-60] - 1  # 近60交易日涨幅
        if recent_3m > 1.0:
            heat_penalty = -0.8  # 翻倍以上，明显过热
        elif recent_3m > 0.8:
            heat_penalty = -0.4  # 涨幅过高，轻微扣分

    score = score_1y * 0.25 + score_3y * 0.20 + score_dd * 0.20 + 3.0 * 0.15 + score_sharpe * 0.10 + val_score * 0.10
    score += heat_penalty  # 过热扣分，不经过规模惩罚
    penalty = scale_penalty(scale_text) if scale_text else 1.0

    return DimensionScore(
        score=min(5.0, max(0, score * penalty)),
        weight=0.25,
        freshness_days=0,
    )


# ============================================================
# Cost Score
# ============================================================

def score_cost(rules: dict, discount: float = PURCHASE_DISCOUNT) -> DimensionScore:
    if not rules:
        return DimensionScore(score=3.0, weight=0.20, freshness_days=365)

    manage = _float(rules.get("manage_fee", 0))
    custody = _float(rules.get("custody_fee", 0))
    # 京东API: purchase_fee 是渠道打折后的实际费率，purchase_fee_original 是原费率
    # 评分时用实际费率（已是打折值），不再重复打折
    purchase = _float(rules.get("purchase_fee", 0))

    total_annual = manage + custody
    total_1y = total_annual + purchase
    total_3y = total_annual * 3 + purchase  # 3-year total including one-time purchase fee

    # Annual fee score (35%)
    if total_annual <= 0.2:
        score_annual = 5.0
    elif total_annual <= 0.6:
        score_annual = 4.0
    elif total_annual <= 1.0:
        score_annual = 3.0
    elif total_annual <= 1.5:
        score_annual = 2.0
    else:
        score_annual = 1.0

    # 1-year total score (25%)
    if total_1y <= 0.5:
        score_1y = 5.0
    elif total_1y <= 1.0:
        score_1y = 4.0
    elif total_1y <= 1.5:
        score_1y = 3.0
    elif total_1y <= 2.5:
        score_1y = 2.0
    else:
        score_1y = 1.0

    # 3-year cost (25%): log mapping for better differentiation
    # index fund total_3y≈0.45% → score≈4.5, active fund total_3y≈4.5% → score≈2.0
    score_3y = max(0, 5.0 - math.log(total_3y + 0.5) * 1.8)

    score = score_annual * 0.35 + score_1y * 0.25 + score_3y * 0.25
    score += 5.0 * 0.15  # redeem fee default

    return DimensionScore(
        score=min(5.0, max(0, score)),
        weight=0.20,
        freshness_days=0,
    )


# ============================================================
# Manager Score
# ============================================================

def score_manager(mgr_data: dict) -> DimensionScore:
    if not mgr_data:
        return DimensionScore(score=2.5, weight=0.20, freshness_days=90)

    managers = mgr_data.get("managers", [])
    if not managers:
        return DimensionScore(score=2.5, weight=0.20, freshness_days=90)

    m = managers[0]

    # API radar data is not available (getFundManagerDetailPageInfo returns no scores)
    # Use employ_performance as proxy for manager skill
    employ_perf = _float(m.get("employ_performance", 0))
    if employ_perf > 0:
        # Map cumulative performance to 0-5: >200% → 5.0, >100% → 4.0, >50% → 3.0, >0% → 2.0
        score_radar = min(5.0, employ_perf / 100 + 2.5)
    else:
        score_radar = 2.5

    tenure_str = m.get("employment_date", "") or m.get("tenure", "")
    tenure_years = 3  # default
    if tenure_str:
        try:
            # Format 1: "13年276天" (from get_fund_detail.manager.employment_date)
            if "年" in tenure_str and "天" in tenure_str:
                parts = tenure_str.replace("年", "-").replace("天", "").split("-")
                if len(parts) >= 2:
                    tenure_years = int(parts[0]) + int(parts[1]) / 365
                else:
                    tenure_years = int(parts[0])
            # Format 2: "5年7个月" or "5年7月"
            elif "年" in tenure_str and ("个月" in tenure_str or "月" in tenure_str):
                parts = tenure_str.replace("年", "-").replace("个月", "-").replace("月", "-").split("-")
                if len(parts) >= 2:
                    tenure_years = int(parts[0]) + int(parts[1]) / 12
                elif len(parts) == 1:
                    tenure_years = int(parts[0])
            # Format 3: "2022.01.11~至今" or "2022-01-11~至今" (from get_fund_manager)
            elif "~" in tenure_str or "至今" in tenure_str:
                import re as _re
                date_match = _re.search(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})", tenure_str)
                if date_match:
                    start = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                    tenure_years = (datetime.now() - start).days / 365
            # Format 4: pure number (years)
            else:
                try:
                    tenure_years = float(tenure_str.replace("年", "").strip())
                except (ValueError, TypeError):
                    pass
        except (ValueError, IndexError, TypeError):
            pass

    if tenure_years >= 8:
        score_tenure = 5.0
    elif tenure_years >= 5:
        score_tenure = 4.0
    elif tenure_years >= 3:
        score_tenure = 3.0
    elif tenure_years >= 1:
        score_tenure = 2.0
    else:
        score_tenure = 1.0

    # Manage scale penalty (too large → harder to outperform)
    scale_text = m.get("manage_scale", "") or ""
    scale_pen = scale_penalty(scale_text) if scale_text else 1.0

    score = (score_radar * 0.35 + score_tenure * 0.25 + 3.0 * 0.40) * scale_pen

    return DimensionScore(
        score=min(5.0, max(0, score)),
        weight=0.20,
        freshness_days=0,
    )


# ============================================================
# Momentum Score
# ============================================================

def score_momentum(nav_index: list[float]) -> DimensionScore:
    if not nav_index or len(nav_index) < 20:
        return DimensionScore(score=2.5, weight=0.15, freshness_days=30)

    values = nav_index
    current = values[-1]

    # Short-term trend (25%): 20-day MA vs current
    ma20 = statistics.mean(values[-20:])
    score_short = min(5.0, (current / ma20 - 1) * 100 + 2.5)

    # Medium-term trend (25%): 60-day MA slope
    if len(values) >= 60:
        ma60 = statistics.mean(values[-60:])
        ma60_30 = statistics.mean(values[-90:-30]) if len(values) >= 90 else statistics.mean(values[:30])
        slope = (ma60 - ma60_30) / ma60_30 * 100
        score_mid = min(5.0, slope * 2 + 2.5)
    else:
        score_mid = 2.5

    # Max drawdown recovery (15%)
    peak = max(values)
    distance = (current - peak) / peak
    if distance >= 0:
        score_recovery = 5.0
    elif distance > -0.05:
        score_recovery = 4.0
    elif distance > -0.10:
        score_recovery = 3.0
    elif distance > -0.20:
        score_recovery = 2.0
    else:
        score_recovery = 1.0

    score = score_short * 0.25 + score_mid * 0.25 + score_recovery * 0.15
    score += 3.0 * 0.35  # remaining weights (momentum duration 20%, correlation 15%)

    return DimensionScore(
        score=min(5.0, max(0, score)),
        weight=0.15,
        freshness_days=0,
    )


# ============================================================
# Smart Money Score
# ============================================================

def score_smart_money(fund_code: str,
                      trading_cache: dict = None,
                      holdings_snapshot: dict = None,
                      holdings_diff: dict = None) -> DimensionScore:
    """Score smart money dimension from pipeline caches.

    Args:
        fund_code: fund code to score
        trading_cache: data/trading_records_cache.json content
        holdings_snapshot: data/holdings_snapshot.json content
        holdings_diff: data/holdings_diff_cache.json content
    """
    # Load caches if not provided
    if trading_cache is None:
        trading_cache = _read_json(PROJECT_ROOT / "data" / "trading_records_cache.json")
    if holdings_snapshot is None:
        holdings_snapshot = _read_json(PROJECT_ROOT / "data" / "holdings_snapshot.json")
    if holdings_diff is None:
        holdings_diff = _read_json(PROJECT_ROOT / "data" / "holdings_diff_cache.json")

    # --- Build by_fund index from holdings_snapshot ---
    # snapshot format: {date, timestamp, holdings: {user_name: [{code, name, amount, ...}]}}
    by_fund = {}  # code -> set of user names
    code_to_name = {}  # code -> name (for trading_records lookup)
    if holdings_snapshot and "holdings" in holdings_snapshot:
        for user_name, funds in holdings_snapshot["holdings"].items():
            if not isinstance(funds, list):
                continue
            for f in funds:
                if isinstance(f, dict) and f.get("code"):
                    code = f["code"]
                    by_fund.setdefault(code, set()).add(user_name)
                    if code not in code_to_name and f.get("name"):
                        code_to_name[code] = f["name"]

    # --- First entry (首次建仓): from holdings_diff ---
    first_entry_count = 0
    if holdings_diff and "funds" in holdings_diff:
        fd = holdings_diff["funds"].get(fund_code, {})
        new_users = fd.get("new_users", []) or fd.get("add_users", [])
        first_entry_count = len(new_users)

    # --- Buy consensus (加仓): from trading_records ---
    # trading_records key is fund NAME, not code. Build lookup.
    buy_count = 0
    sell_count = 0
    if trading_cache and "funds" in trading_cache:
        # Try direct code lookup first
        tf = trading_cache["funds"].get(fund_code, {})
        if tf:
            buy_count = tf.get("buy_count", 0)
            sell_count = tf.get("sell_count", 0)
        else:
            # Lookup by name
            fund_name = code_to_name.get(fund_code, "")
            if fund_name:
                tf = trading_cache["funds"].get(fund_name, {})
                buy_count = tf.get("buy_count", 0)
                sell_count = tf.get("sell_count", 0)

    # --- Holdings breadth ---
    breadth = len(by_fund.get(fund_code, set()))

    # --- Penetrate overlap (Phase 3 placeholder) ---
    penetrate_count = 0

    # --- Synthesize per design doc formula ---
    raw_first = min(first_entry_count, 3) * 1.5 * 1.67
    raw_add = min(buy_count, 5) * 1.0
    raw_breadth = min(breadth / 3, 1.0) * 5.0 if breadth > 0 else 0.0
    raw_penetrate = min(penetrate_count / 5, 1.0) * 5.0

    raw = raw_first * 0.30 + raw_add * 0.30 + raw_breadth * 0.25 + raw_penetrate * 0.15

    # No first entry → cap at 3.0
    if first_entry_count == 0:
        raw = min(raw, 3.0)

    # Freshness: trading cache date
    freshness = 0
    if trading_cache and "date" in trading_cache:
        try:
            cache_date = datetime.strptime(str(trading_cache["date"])[:10], "%Y-%m-%d").date()
            freshness = (date.today() - cache_date).days
        except (ValueError, TypeError):
            pass

    return DimensionScore(
        score=min(5.0, max(0, raw)),
        weight=0.20,
        freshness_days=freshness,
    )


# ============================================================
# Main Scoring
# ============================================================

def score_fund(fund_code: str, detail_data: dict = None,
               chart_data: list[dict] = None, nav_data: list[dict] = None,
               trading_cache: dict = None, holdings_snapshot: dict = None,
               holdings_diff: dict = None) -> FundScore:
    """Score a fund using cached data or live detail data."""
    perf = detail_data.get("performance") if detail_data else _read_cache("fund_perf", fund_code)
    rules = _read_cache("trade_rules", fund_code)
    mgr = detail_data.get("manager") if detail_data else _read_cache("fund_manager", fund_code)
    # Fallback: if manager cache has no employ_performance, try fund_detail cache
    if mgr and mgr.get("managers") and not mgr["managers"][0].get("employ_performance"):
        detail_cache = _read_cache("fund_detail", fund_code)
        if detail_cache and detail_cache.get("manager", {}).get("managers"):
            detail_mgr = detail_cache["manager"]
            # Merge employ_performance into mgr data
            if detail_mgr["managers"][0].get("employ_performance"):
                mgr["managers"][0]["employ_performance"] = detail_mgr["managers"][0]["employ_performance"]
                mgr["managers"][0]["manage_scale"] = detail_mgr["managers"][0].get("manage_scale", "")
                mgr["managers"][0]["year_performance"] = detail_mgr["managers"][0].get("year_performance", "")

    # Build nav_index: prefer chart data (longer history), fallback to nav_history
    nav_index = None
    daily_returns = None
    if chart_data and len(chart_data) >= 20:
        nav_index = chart_to_nav_index(chart_data)
        daily_returns = chart_to_daily_returns(chart_data)
    elif nav_data and len(nav_data) >= 2:
        nav_index = [_float(n.get("nav")) for n in nav_data if _float(n.get("nav"))]
        daily_returns = nav_to_daily_returns(nav_data)

    profile = detail_data.get("profile") if detail_data else _read_cache("fund_profile", fund_code)
    established_days = None
    if profile:
        est_str = profile.get("established", "") or profile.get("established_date", "")
        if est_str:
            try:
                est = datetime.strptime(est_str.replace("/", "-")[:10], "%Y-%m-%d")
                established_days = (datetime.now() - est).days
            except (ValueError, IndexError):
                pass
    fund_type = "active"
    if profile:
        type_name = profile.get("fund_type", "")
        # "指数型-股票" / "QDII-指数" → passive_index
        if "指数" in type_name and "增强" not in type_name:
            fund_type = "passive_index"
        elif "指数增强" in type_name or ("指数" in type_name and "增强" in type_name):
            fund_type = "index_enhanced"

    # If profile has no fund_type, try to guess from fund name
    if fund_type == "active" and profile:
        fname = profile.get("full_name", "") or profile.get("name", "")
        if ("指数" in fname or "ETF" in fname) and "增强" not in fname:
            fund_type = "passive_index"
        elif "指数增强" in fname or ("指数" in fname and "增强" in fname):
            fund_type = "index_enhanced"

    if fund_type == "passive_index":
        q = DimensionScore(score=3.0, weight=0.25, freshness_days=0)
        mgr_dim = DimensionScore(score=-1, weight=0, freshness_days=0)
        mom = DimensionScore(score=3.0, weight=0.15, freshness_days=0)
    else:
        scale_text = profile.get("scale") if profile else None
        hd = detail_data.get("holdings") if detail_data else _read_cache("fund_holdings", fund_code)
        q = score_quality(perf, nav_index, daily_returns, scale_text, hd)
        mgr_dim = score_manager(mgr)
        mom = score_momentum(nav_index)

    c = score_cost(rules)
    sm = score_smart_money(fund_code, trading_cache, holdings_snapshot, holdings_diff)

    fs = FundScore(
        fund_code=fund_code,
        fund_type=fund_type,
        quality=q,
        cost=c,
        manager=mgr_dim,
        momentum=mom,
        smart_money=sm,
    )
    fs.compute(established_days=established_days)

    # 过度上涨扣分已包含在 score_quality 的 heat_penalty 中
    # 此处不再重复扣分

    return fs


def batch_score(codes: list[str]) -> dict[str, FundScore]:
    return {code: score_fund(code) for code in codes}


# ============================================================
# Test: Sharpe ratio with live NAV data
# ============================================================

def test_sharpe(fund_code: str):
    """Test Sharpe ratio calculation by fetching live NAV data."""
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from jd_finance_api import get_fund_detail, get_fund_chart_data

    print(f"\n{'='*60}")
    print(f"Sharpe Ratio Test: {fund_code}")
    print(f"{'='*60}")

    detail = get_fund_detail(fund_code, use_cache=False)
    if not detail:
        _logger.error("No data returned")
        return

    # Chart data (232 points, daily cumulative returns)
    chart = get_fund_chart_data(fund_code)
    chart_points = chart.get("chart_points", [])

    nav = detail.get("nav_history", [])
    print(f"\nNAV data points: {len(nav)} (from getFundHistoryNetValuePageInfo)")
    if nav:
        print(f"  Date range: {nav[0]['date']} ~ {nav[-1]['date']}")
    print(f"Chart data points: {len(chart_points)} (from getFundDetailChartPageInfo)")
    if chart_points:
        print(f"  Date range: {chart_points[0]['xAxis']} ~ {chart_points[-1]['xAxis']}")

    # Calculate Sharpe from chart data (longer history)
    daily_returns = chart_to_daily_returns(chart_points)
    sharpe = calc_sharpe(daily_returns)
    print(f"\nSharpe ratio (chart-based, {len(daily_returns)} daily returns): {sharpe:.4f}")
    print(f"Sharpe score (0-5): {sharpe_to_score(sharpe):.2f}")

    # Max drawdown from chart data
    nav_idx = chart_to_nav_index(chart_points)
    mdd = calc_max_drawdown(nav_idx) if nav_idx else 0
    print(f"Max drawdown (chart-based): {mdd:.2f}%")

    # Full scoring
    fs = score_fund(fund_code, detail_data=detail, chart_data=chart_points)
    print(f"\n{'='*60}")
    print(f"Full Scoring: {fund_code}")
    print(f"{'='*60}")
    print(f"  Fund Type:  {fs.fund_type}")
    print(f"  Quality:    {fs.quality.score:.2f} (w={fs.quality.weight})")
    print(f"  Cost:       {fs.cost.score:.2f} (w={fs.cost.weight})")
    print(f"  Manager:    {fs.manager.score:.2f} (w={fs.manager.weight})")
    print(f"  Momentum:   {fs.momentum.score:.2f} (w={fs.momentum.weight})")
    print(f"  SmartMoney: {fs.smart_money.score:.2f} (w={fs.smart_money.weight})")
    print(f"  Total:      {fs.total:.2f}")
    print(f"  Verdict:    {fs.verdict}")
    print()


# ============================================================
# Scoring Stability Validation (P1)
# ============================================================

def validate_scoring_predictive_power(n_days: int = 90) -> dict:
    """Validate: did high-scoring funds outperform low-scoring funds over N days?

    Uses cached fund_perf data to compare past scores against actual returns.
    Pure data validation, no LLM involvement.

    Args:
        n_days: lookback period (default 90 days)

    Returns:
        dict with comparison results
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Collect all cached fund_perf files
    perf_files = list(CACHE_DIR.glob("fund_perf_*.json"))
    print(f"\n{'='*60}")
    print(f"  Scoring Stability Validation (past {n_days}d)")
    print(f"{'='*60}")
    print(f"  Found {len(perf_files)} cached funds")

    results = {"high_score": [], "mid_score": [], "low_score": [], "errors": []}

    def _eval_one(fp):
        code = fp.stem.replace("fund_perf_", "")
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return None

        perf_list = data.get("performance", [])
        perf_map = {p.get("period", ""): p for p in perf_list}

        # Get near_3m return (the validation target)
        near_3m = perf_map.get("近3月", {})
        near_3m_return = near_3m.get("return")
        if near_3m_return is None:
            return None

        # Score the fund using cache data only
        try:
            fs = score_fund(code)
        except Exception:
            return None

        return {
            "code": code,
            "score": fs.total,
            "verdict": fs.verdict,
            "return_3m": near_3m_return,
        }

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_eval_one, fp): fp for fp in perf_files}
        for fut in as_completed(futs):
            r = fut.result()
            if r is None:
                continue
            s = r["score"]
            if s >= 4.0:
                results["high_score"].append(r)
            elif s >= 3.3:
                results["mid_score"].append(r)
            else:
                results["low_score"].append(r)

    # Summary
    print(f"\n  Results:")
    if results["high_score"]:
        avg_return = statistics.mean([r["return_3m"] for r in results["high_score"]])
        median_r = statistics.median([r["return_3m"] for r in results["high_score"]])
        print(f"    High-score group (≥4.0, n={len(results['high_score'])}):")
        print(f"      avg return(3m)={avg_return:.2f}%, median={median_r:.2f}%")
    else:
        print(f"    High-score group (≥4.0): no funds")

    if results["mid_score"]:
        avg_return = statistics.mean([r["return_3m"] for r in results["mid_score"]])
        median_r = statistics.median([r["return_3m"] for r in results["mid_score"]])
        print(f"    Mid-score group (3.3-4.0, n={len(results['mid_score'])}):")
        print(f"      avg return(3m)={avg_return:.2f}%, median={median_r:.2f}%")
    else:
        print(f"    Mid-score group (3.3-4.0): no funds")

    if results["low_score"]:
        avg_return = statistics.mean([r["return_3m"] for r in results["low_score"]])
        median_r = statistics.median([r["return_3m"] for r in results["low_score"]])
        print(f"    Low-score group (<3.3, n={len(results['low_score'])}):")
        print(f"      avg return(3m)={avg_return:.2f}%, median={median_r:.2f}%")
    else:
        print(f"    Low-score group (<3.3): no funds")

    # Gap analysis
    if results["high_score"] and results["low_score"]:
        h_avg = statistics.mean([r["return_3m"] for r in results["high_score"]])
        l_avg = statistics.mean([r["return_3m"] for r in results["low_score"]])
        gap = h_avg - l_avg
        print(f"\n  Performance gap (high vs low): {gap:.2f}%")
        print(f"  {'✅ Scoring is predictive' if gap > 0 else '❌ Scoring needs adjustment'}")

    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI Berkshire Fund Scoring Engine")
    parser.add_argument("--score", type=str, help="Score a single fund code")
    parser.add_argument("--batch", type=str, nargs="+", help="Batch score fund codes")
    parser.add_argument("--test-sharpe", type=str, help="Test Sharpe ratio with live data")
    parser.add_argument("--validate", action="store_true", help="Run scoring validation")
    args = parser.parse_args()

    if args.validate:
        validate_scoring_predictive_power()
    elif args.test_sharpe:
        test_sharpe(args.test_sharpe)
    elif args.score:
        fs = score_fund(args.score)
        print(f"\n{args.score}: total={fs.total:.2f}, verdict={fs.verdict}")
    elif args.batch:
        results = batch_score(args.batch)
        for code, fs in results.items():
            print(f"{code}: total={fs.total:.2f}, verdict={fs.verdict}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
