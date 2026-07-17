#!/usr/bin/env python3
"""增强版每日实盘模拟 — 整合最优参数 + 场外基金费率感知 + LLM Skill集成

增强功能：
1. 复用回测最优参数（自动从 best_config.json 加载）
2. 场外基金费率感知（申购/赎回/服务费，持有<7天避免惩罚性赎回费）
3. A/C份额智能推荐（预期持有<1年推荐C类，>1年推荐A类）
4. 限额检测（单日限购、申购状态）
5. 时间止损（持仓>30天亏损>3%卖出）
6. LLM Skill 集成分析框架（checklist/penetration/analyze）
7. 增强日报输出（含场外基金特有信息）

Usage:
    py -3.10 scripts/daily_live_enhanced.py
    py -3.10 scripts/daily_live_enhanced.py --simulate-date 2026-07-01
"""

import json, sys, os, glob, argparse
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# ── 参数解析 ──
_ap = argparse.ArgumentParser(description="冠军策略模拟 — 增强版")
_ap.add_argument("--simulate-date", default=None, help="模拟指定日期 (YYYY-MM-DD)")
_ap.add_argument("--no-llm", action="store_true", help="禁用LLM分析")
_ap.add_argument("--config", default=None, help="配置文件路径 (默认 best_config.json)")
_ap.add_argument("--paper-mode", default="off", choices=["off", "auto"], help="影子模拟模式 (auto=自主推进)")
_args, _ = _ap.parse_known_args()

if _args.simulate_date:
    _dt = datetime.strptime(_args.simulate_date, "%Y-%m-%d")
    print(f"[SIM] simulate-date={_args.simulate_date}")
else:
    _dt = datetime.now()

TODAY = _dt.strftime("%Y-%m-%d")
TODAY_CN = _dt.strftime("%Y年%m月%d日")

# ── 导入回测引擎组件 ──
from tools.jd_finance_api import get_watchlist, get_trading_records, _ensure_cookies, _verify_cookies, FOLLOWED_USERS
from backtest.engine.backtest import (
    Portfolio, score_fund_backtest, detect_market_state,
    compute_correlation_matrix, check_max_correlation,
)
from tools.technical_indicators import compute_entry_timing_score, compute_rsi, compute_atr_pct
from tools.fund_rules import take_profit_level, swap_cost, weighted_clear, buy_shield

# ── 加载最优参数（支持 --config 覆盖）──
OPTIMAL_PATH = PROJECT / "data" / "evolution" / "optimal_config.json"
EVO_PATH = PROJECT / "data" / "evolution" / "best_config.json"
CONFIG_PATH = Path(_args.config) if _args.config else (OPTIMAL_PATH if OPTIMAL_PATH.exists() else EVO_PATH)
if CONFIG_PATH.exists():
    evo = json.loads(CONFIG_PATH.read_text("utf-8"))
    GENE = evo.get("config", evo)
    perf = evo.get("performance", {})
    print(f"参数: {CONFIG_PATH.name} | {evo.get('note', 'N/A')}")
    if perf:
        print(f"  收益={perf.get('total_return', 'N/A')}% 回撤={perf.get('max_drawdown', 'N/A')}% 交易={perf.get('trade_count', 'N/A')}")
else:
    evo = {}
    GENE = {}

# ── 数据加载 ──
CACHE = PROJECT / "data" / "fund_cache"
def load_cache(prefix):
    data = {}
    for f in glob.glob(str(CACHE / f"{prefix}_*.json")):
        code = Path(f).stem.replace(f"{prefix}_", "", 1)
        try: data[code] = json.loads(open(f, encoding="utf-8").read())
        except: pass
    return data

fund_rules = load_cache("trade_rules")
fund_managers = load_cache("fund_manager")
fund_profiles = load_cache("fund_profile")
fund_charts_path = PROJECT / "data" / "fund_charts.json"
fund_charts = json.loads(fund_charts_path.read_text("utf-8")) if fund_charts_path.exists() else {}

tp = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
trading_by_date = json.loads(tp.read_text("utf-8")) if tp.exists() else {}

name_map_path = PROJECT / "data" / "fund_name_map.json"
name_map = json.loads(name_map_path.read_text("utf-8")) if name_map_path.exists() else {}
code_to_name = {}
for nm, cd in name_map.items():
    if cd not in code_to_name:
        code_to_name[cd] = nm

# ── 虚拟持仓 ──
SIM_DIR = PROJECT / "reports" / "sim"
SIM_DIR.mkdir(parents=True, exist_ok=True)
VP_PATH = SIM_DIR / "virtual_portfolio_enhanced.json"
INITIAL_CASH = 100000

# ── Skill缓存 ──
SKILL_CACHE_DIR = PROJECT / "data" / "skill_cache"
SKILL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_vp():
    if VP_PATH.exists():
        return json.loads(VP_PATH.read_text("utf-8"))
    return {"created": TODAY, "initial_cash": INITIAL_CASH,
            "cash": INITIAL_CASH, "total_fees": 0,
            "holdings": {}, "pending": [], "history": [], "snapshots": [],
            "sell_history": {}}

def save_vp(vp):
    VP_PATH.write_text(json.dumps(vp, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════
# 场外基金费率感知模块
# ═══════════════════════════════════════════════════════════

def get_fee_info(code):
    """获取基金完整费率信息"""
    rules = fund_rules.get(code, {})
    return {
        "purchase_fee": float(rules.get("purchase_fee", 0) or 0),
        "manage_fee": float(rules.get("manage_fee", 0) or 0),
        "trustee_fee": float(rules.get("trustee_fee", 0) or 0),
        "service_fee": float(rules.get("service_fee", 0) or 0),
        "redeem_fees": rules.get("redeem_fees", []),
        "day_limit": rules.get("day_limit", 99999999),
        "purchase_status": rules.get("purchase_status", "开放申购"),
        "redeem_status": rules.get("redeem_status", "开放赎回"),
    }


def get_redeem_fee(code, days_held):
    """根据持有天数获取赎回费率"""
    rules = fund_rules.get(code, {})
    tiers = rules.get("redeem_fees", [])
    if not tiers:
        if days_held < 7: return 0.015  # 1.5% 惩罚性
        if days_held < 30: return 0.0075
        if days_held < 365: return 0.005
        return 0.0
    for tier in tiers:
        interval = str(tier.get("interval", ""))
        rate = float(tier.get("rate", 0))
        if "≤" in interval and "<" in interval:
            parts = interval.replace("天", "").split("≤")
            if len(parts) >= 2:
                rest = parts[1].split("<")
                try:
                    low = int(parts[0].strip()) if parts[0].strip().isdigit() else 0
                    high = int(rest[0].strip()) if len(rest) >= 1 and rest[0].strip().isdigit() else 9999
                    if low <= days_held < high:
                        return rate / 100
                except: pass
        elif "≥" in interval:
            low_str = interval.replace("天", "").replace("≥", "").strip()
            try:
                low = int(low_str) if low_str.isdigit() else 0
                if days_held >= low:
                    return rate / 100
            except: pass
    return 0.0


def check_short_term_penalty(code, days_held):
    """检查是否处于惩罚性赎回费期"""
    if days_held < 7:
        fee = get_redeem_fee(code, days_held)
        if fee >= 0.01:  # >= 1%
            return True, f"持有{days_held}天，赎回费{fee*100:.1f}%（惩罚性）"
    if days_held < 30:
        fee = get_redeem_fee(code, days_held)
        if fee >= 0.005:  # >= 0.5%
            return True, f"持有{days_held}天，赎回费{fee*100:.1f}%（较高）"
    return False, ""


def recommend_share_class(code, name, expected_hold_days):
    """A/C份额智能推荐
    
    C类：无申购费，但有销售服务费（~0.4%/年），适合持有<1年
    A类：有申购费（~1.5%），但无服务费，适合持有>1年
    """
    # 检查是否已有A/C后缀
    if "C" in name[-3:] or "c" in name[-3:]:
        current_class = "C"
    elif "A" in name[-3:] or "a" in name[-3:]:
        current_class = "A"
    else:
        current_class = "unknown"
    
    rules = fund_rules.get(code, {})
    purchase_fee = float(rules.get("purchase_fee", 0) or 0)
    service_fee = float(rules.get("service_fee", 0) or 0)
    
    # 计算两种方案的总成本
    if expected_hold_days < 365:
        # C类：服务费 * 年数
        c_cost = service_fee * (expected_hold_days / 365)
        a_cost = purchase_fee * 0.1  # A类申购费1折
        if c_cost < a_cost:
            return "C", f"预期持有{expected_hold_days}天，C类成本{c_cost:.2f}% < A类{a_cost:.2f}%"
        else:
            return "A", f"预期持有{expected_hold_days}天，A类成本{a_cost:.2f}% ≤ C类{c_cost:.2f}%"
    else:
        return "A", f"预期持有{expected_hold_days}天(>1年)，A类长期更优"


def check_purchase_limit(code, amount):
    """检查申购限额"""
    rules = fund_rules.get(code, {})
    status = rules.get("purchase_status", "")
    if status and status != "开放申购":
        return False, f"申购状态: {status}"
    day_limit = rules.get("day_limit", 99999999)
    if day_limit == "Infinity" or day_limit is None:
        return True, ""
    try:
        limit = float(day_limit)
        if limit < 100:
            return False, f"日限额过低: {limit}元"
        if amount > limit:
            return False, f"超过日限额: {limit}元"
        return True, ""
    except:
        return True, ""


# ═══════════════════════════════════════════════════════════
# 时间止损模块
# ═══════════════════════════════════════════════════════════

def check_time_stop(code, holdings, current_date, threshold_days=30, threshold_loss=-3):
    """时间止损：持仓超过N天仍亏损>X%则卖出"""
    if code not in holdings:
        return False, ""
    h = holdings[code]
    buy_date = h.get("buy_date", current_date)
    try:
        dt1 = datetime.strptime(buy_date[:10], "%Y-%m-%d")
        dt2 = datetime.strptime(current_date[:10], "%Y-%m-%d")
        days_held = (dt2 - dt1).days
    except:
        return False, ""
    
    if days_held < threshold_days:
        return False, ""
    
    # 计算盈亏
    pts = fund_charts.get(code, [])
    if not pts:
        return False, ""
    valid = [p for p in pts if p.get("xAxis", "")[:10] <= current_date]
    if not valid:
        return False, ""
    
    latest_yaxis = float(valid[-1].get("yAxis", 0))
    latest_nav = (100 + latest_yaxis) / 100
    buy_pts = [p for p in pts if p.get("xAxis", "")[:10] <= buy_date]
    if not buy_pts:
        return False, ""
    buy_yaxis = float(buy_pts[-1].get("yAxis", 0))
    buy_nav = (100 + buy_yaxis) / 100
    
    if buy_nav <= 0:
        return False, ""
    pnl = (latest_nav / buy_nav - 1) * 100
    
    if pnl < threshold_loss:
        return True, f"时间止损: 持有{days_held}天, 亏损{pnl:.1f}%"
    return False, ""


# ═══════════════════════════════════════════════════════════
# LLM Skill 集成框架
# ═══════════════════════════════════════════════════════════

def generate_skill_input(code, name, score, market_state, holdings_info=None):
    """为LLM Skill分析生成结构化输入"""
    rules = fund_rules.get(code, {})
    profile = fund_profiles.get(code, {})
    manager = fund_managers.get(code, {})
    
    skill_input = {
        "fund_code": code,
        "fund_name": name,
        "score": round(score, 2),
        "market_state": market_state,
        "fee_info": get_fee_info(code),
        "profile": {
            "fund_type": profile.get("fund_type", ""),
            "scale": profile.get("scale", ""),
            "establish_date": profile.get("establish_date", ""),
            "risk_level": profile.get("risk_level", ""),
        },
        "manager": {
            "name": manager.get("managers", [{}])[0].get("name", "") if manager.get("managers") else "",
            "tenure": manager.get("managers", [{}])[0].get("tenure", "") if manager.get("managers") else "",
        },
        "rules_check": {
            "take_profit": take_profit_level(profile.get("fund_type", "active")),
            "swap_cost": swap_cost(code),
            "weighted_clear": weighted_clear(code),
            "buy_shield": buy_shield(code),
        },
    }
    return skill_input


def run_skill_analysis(code, name, score, market_state):
    """运行LLM Skill分析（生成结构化结果供日报使用）
    
    注意：此函数生成的是结构化数据框架，实际LLM调用需要在外部IDE中执行。
    结果缓存24小时避免重复计算。
    """
    cache_dir = SKILL_CACHE_DIR / code
    cache_file = cache_dir / f"{TODAY}.json"
    
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text("utf-8"))
        except:
            pass
    
    # 生成结构化分析框架
    skill_input = generate_skill_input(code, name, score, market_state)
    
    # 量化规则检查（不需要LLM）
    rules_check = skill_input["rules_check"]
    
    # 基于规则的初步判断
    verdict = "pass"
    reasons = []
    
    # 规则1: 规模<5亿 → 否决
    scale_str = skill_input["profile"]["scale"]
    if "亿" in scale_str:
        import re
        nums = re.findall(r'[\d.]+', scale_str.replace("亿元", "").replace("亿", ""))
        if nums:
            scale_val = float(nums[0])
            if scale_val < 5:
                verdict = "veto"
                reasons.append(f"规模{scale_val}亿<5亿，清盘风险")
    
    # 规则2: 经理变更<6月 → 否决
    # (需要公告数据，此处跳过)
    
    # 规则3: 费率过高 → 警告
    fee_info = skill_input["fee_info"]
    total_fee = fee_info["purchase_fee"] + fee_info["manage_fee"] + fee_info["trustee_fee"]
    if total_fee > 3:
        reasons.append(f"总费率{total_fee:.1f}%偏高")
    
    # 规则4: 调仓成本检查
    swap = rules_check["swap_cost"]
    if not swap.get("should_swap", True):
        reasons.append(f"调仓成本{swap.get('swap_cost_pct', 0):.1f}%过高")
    
    # 生成Skill调用指令（供IDE中的AI执行）
    skill_commands = [
        f"fund-checklist {code}",
        f"fund-penetration {code}",
        f"fund-analyze {code}",
    ]
    
    result = {
        "code": code,
        "name": name,
        "date": TODAY,
        "score": round(score, 2),
        "verdict": verdict,
        "reasons": reasons,
        "fee_info": fee_info,
        "rules_check": rules_check,
        "skill_commands": skill_commands,
        "skill_input": skill_input,
        "llm_analyzed": False,  # 标记是否已被LLM分析
    }
    
    # 缓存结果
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    
    return result


# ═══════════════════════════════════════════════════════════
# PaperAccount: 四阶段投产管道
# shadow(0资金,30天) → pilot(10%,60天) → standard(50%,90天) → full(100%)
# 自主推进 + 熔断 + 偏差追踪
# ═══════════════════════════════════════════════════════════

class PaperAccount:
    """四阶段投产: shadow → pilot → standard → full

    - shadow→pilot:  30天 + 偏差<5% + 执行率>80% → 全自动
    - pilot→standard: 60天 + 净值>初始 + 回撤<8% → 48h沉默后自动
    - standard→full:  90天 + 年化15-40% + 回撤<12.4% + 月胜率>50% → 48h沉默后自动
    - 任意→冻结: 回撤超标 或 偏差>3%连续5天 → 立即冻结
    """

    PHASES = {
        "shadow":   {"target_days": 30, "cash_pct": 0.0,  "max_pos": 0,  "cb_dd": 5.0,  "max_dev": 5.0, "min_exec": 80.0},
        "pilot":    {"target_days": 60, "cash_pct": 0.10, "max_pos": 15, "cb_dd": 8.0,  "max_dev": 3.0},
        "standard": {"target_days": 90, "cash_pct": 0.50, "max_pos": 25, "cb_dd": 12.4, "max_dev": 3.0},
        "full":     {"target_days": 0,  "cash_pct": 1.0,  "max_pos": 25, "cb_dd": 15.0, "max_dev": 3.0},
    }
    BT_DAYS = 543  # 2025-01-05 ~ 2026-07-01

    def __init__(self, sim_dir, today, initial_cash=100000, bt_return=69.60):
        self.acc_path = sim_dir / "champion_paper_account.json"
        self.sts_path = sim_dir / "champion_status.json"
        self.today = today
        self.ic = initial_cash
        self.bt_ret = bt_return
        self.data, self.status = {}, {}

    def load_or_init(self):
        if self.acc_path.exists():
            self.data = json.loads(self.acc_path.read_text("utf-8"))
            self.status = json.loads(self.sts_path.read_text("utf-8"))
        else:
            self.data = {
                "phase": "shadow", "start_date": self.today,
                "initial_cash": self.ic, "backtest_return": self.bt_ret,
                "deployed_cash": 0, "daily_snapshots": [],
                "deviation_log": [], "frozen": False, "circuit_breaker_count": 0,
            }
            self.status = {
                "phase": "shadow", "start_date": self.today, "elapsed_days": 0,
                "pending_advance": False, "advance_at": None, "advance_to": None,
                "advance_log": [], "circuit_breaker_count": 0,
                "last_run": self.today, "frozen": False,
            }
            self.save()
        return self

    def save(self):
        self.acc_path.parent.mkdir(parents=True, exist_ok=True)
        self.acc_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.sts_path.write_text(json.dumps(self.status, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def phase(self):
        return self.data.get("phase", "shadow")

    @property
    def cfg(self):
        return self.PHASES.get(self.phase, self.PHASES["shadow"])

    @property
    def elapsed(self):
        try:
            s = datetime.strptime(self.data.get("start_date", self.today)[:10], "%Y-%m-%d")
            n = datetime.strptime(self.today[:10], "%Y-%m-%d")
            return max(0, (n - s).days)
        except Exception:
            return 0

    def _theo_ret(self):
        """线性插值回测收益作为理论基准"""
        return self.bt_ret * self.elapsed / self.BT_DAYS

    def daily_update(self, actual_nav, signals_total, signals_exec, current_dd):
        """每日快照 + 熔断检查 + Phase 推进"""
        if self.data.get("frozen"):
            self.save()
            return {"frozen": True, "advanced": False}

        e = self.elapsed
        self.status["elapsed_days"] = e
        self.status["last_run"] = self.today

        a_ret = ((actual_nav - self.ic) / self.ic * 100) if self.ic > 0 else 0
        t_ret = self._theo_ret()
        dev = abs(t_ret - a_ret)
        er = (signals_exec / signals_total * 100) if signals_total > 0 else 100

        snap = {
            "date": self.today, "elapsed_days": e,
            "actual_nav": round(actual_nav, 2), "actual_return_pct": round(a_ret, 2),
            "theoretical_return_pct": round(t_ret, 2),
            "deviation_pct": round(dev, 2),
            "signals": signals_total, "executed": signals_exec,
            "execution_rate": round(er, 1), "current_dd": round(current_dd, 2),
        }
        self.data["daily_snapshots"].append(snap)

        if dev > 3.0:
            self.data["deviation_log"].append({
                "date": self.today, "deviation_pct": round(dev, 2),
                "theoretical": round(t_ret, 2), "actual": round(a_ret, 2),
            })

        # 熔断检查
        cb = self._check_cb(current_dd, dev)
        if cb:
            self.save()
            return {"frozen": True, "advanced": False, "snapshot": snap}

        # Phase 推进
        adv = self._try_advance(a_ret, er, current_dd, dev)
        self.save()
        return {"frozen": False, "advanced": adv, "snapshot": snap}

    def _check_cb(self, dd, dev):
        c = self.cfg
        if dd > c["cb_dd"]:
            self._freeze(f"回撤{dd:.1f}%>限额{c['cb_dd']}%")
            return True
        recent = [d for d in self.data.get("deviation_log", [])[-5:]
                  if d.get("deviation_pct", 0) > c["max_dev"]]
        if len(recent) >= 5:
            self._freeze(f"偏差连续5天>{c['max_dev']}%")
            return True
        return False

    def _freeze(self, reason):
        self.data["frozen"] = True
        self.status["frozen"] = True
        self.status["frozen_reason"] = reason
        self.status["frozen_date"] = self.today
        self.data["circuit_breaker_count"] = self.data.get("circuit_breaker_count", 0) + 1
        self.status["circuit_breaker_count"] = self.status.get("circuit_breaker_count", 0) + 1
        print(f"🚨 CIRCUIT BREAKER: {reason}")

    def _try_advance(self, a_ret, exec_rate, dd, dev):
        c = self.cfg
        if self.elapsed < c["target_days"]:
            return False

        p = self.phase
        if p == "shadow":
            if dev < c["max_dev"] and exec_rate >= c.get("min_exec", 80):
                self._advance("pilot", f"自动: {self.elapsed}天 偏差{dev:.1f}% 执行率{exec_rate:.0f}%")
                return True

        elif p == "pilot":
            if not self.status.get("pending_advance"):
                if a_ret > 0 and dd < c["cb_dd"]:
                    t = datetime.now() + timedelta(hours=48)
                    self.status["pending_advance"] = True
                    self.status["advance_at"] = t.strftime("%Y-%m-%d %H:%M:%S")
                    self.status["advance_to"] = "standard"
                    print(f"[PHASE-ADVANCE] pilot→standard 排队, 48h后推进 ({self.status['advance_at']})")
            else:
                self._check_notice("standard")

        elif p == "standard":
            if not self.status.get("pending_advance"):
                ann = a_ret * 365 / max(self.elapsed, 1)
                snaps = self.data.get("daily_snapshots", [])
                months = {}
                for s in snaps:
                    m = s.get("date", "")[:7]
                    if m:
                        months[m] = s.get("actual_return_pct", 0)
                wr = sum(1 for v in months.values() if v > 0) / max(len(months), 1) * 100
                if 15 <= ann <= 40 and dd < c["cb_dd"] and wr >= 50:
                    t = datetime.now() + timedelta(hours=48)
                    self.status["pending_advance"] = True
                    self.status["advance_at"] = t.strftime("%Y-%m-%d %H:%M:%S")
                    self.status["advance_to"] = "full"
                    print(f"[PHASE-ADVANCE] standard→full 排队, 48h后推进 ({self.status['advance_at']})")
            else:
                self._check_notice("full")
        return False

    def _check_notice(self, target):
        at = self.status.get("advance_at", "")
        if not at:
            return
        try:
            adt = datetime.strptime(at, "%Y-%m-%d %H:%M:%S")
            if datetime.now() >= adt:
                self._advance(target, "48h沉默期已过, 自动推进")
        except Exception:
            pass

    def _advance(self, new_phase, reason):
        old = self.phase
        self.data["phase"] = new_phase
        self.data["start_date"] = self.today
        self.data["deployed_cash"] = self.ic * self.PHASES[new_phase]["cash_pct"]
        self.status["phase"] = new_phase
        self.status["pending_advance"] = False
        self.status["advance_at"] = None
        self.status["advance_to"] = None
        self.status["advance_log"].append({"date": self.today, "from": old, "to": new_phase, "reason": reason})
        print(f"[PHASE-ADVANCE] {old} → {new_phase}: {reason}")


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def run():
    print(f"=== 冠军策略模拟 {TODAY_CN} ===")

    # 0. PaperAccount (Phase 管理)
    paper = None
    if _args.paper_mode == "auto":
        bt_ret = evo.get("performance", {}).get("total_return", 69.60) if isinstance(evo, dict) else 69.60
        paper = PaperAccount(SIM_DIR, TODAY, INITIAL_CASH, bt_ret).load_or_init()
        print(f"0. PaperAccount: phase={paper.phase} elapsed={paper.elapsed}d deployed={paper.data.get('deployed_cash', 0):.0f}")
        if paper.data.get("frozen"):
            print(f"   🚨 账户已冻结: {paper.status.get('frozen_reason', '未知')}")
    
    # 1. 数据加载
    cookies = _ensure_cookies(offline=True)
    if not cookies:
        cp = PROJECT / "data" / "jd_auth" / "cookies.json"
        if cp.exists():
            cookies = json.loads(cp.read_text("utf-8"))
    if not cookies and not _args.simulate_date:
        print("[ERROR] 无 Cookie")
        return
    
    wl = get_watchlist(cookies=cookies, use_cache=True)
    if not wl or not wl.get("funds"):
        print("[ERROR] 自选列表为空")
        return
    funds = {f["fund_code"]: f for f in wl["funds"]}
    print(f"1. 自选 {len(funds)} 只")
    
    # 2. 市场状态
    market = detect_market_state(TODAY, fund_charts)
    min_score = GENE.get(f"min_score_{market}", GENE.get("min_score", 3.0))
    print(f"2. 市场: {market} (门槛={min_score})")
    
    # 3. 组合状态恢复
    vp = load_vp()
    portfolio = Portfolio(INITIAL_CASH)
    portfolio.set_fund_rules(fund_rules)
    portfolio._profiles = fund_profiles
    portfolio.slippage_pct = GENE.get("slippage_pct", 0.1)
    
    for code, h in vp.get("holdings", {}).items():
        cb = h.get("cost_basis", 5000)
        portfolio.holdings[code] = {
            "name": h["name"], "shares": cb, "cost": cb,
            "buy_date": h.get("buy_date", TODAY), "buy_nav": 1.0,
            "peak_nav": h.get("peak_nav", 1.0),
        }
    portfolio.cash = vp.get("cash", INITIAL_CASH)
    portfolio.total_fees = vp.get("total_fees", 0)
    for pb in vp.get("pending", []):
        portfolio.pending_buys.append(pb)
    portfolio.sell_history = vp.get("sell_history", {})
    
    portfolio.settle_pending(TODAY)
    print(f"3. 持仓 {len(portfolio.holdings)} 只, 现金 {portfolio.cash:,.0f}")
    
    # 4. 评分 + 费率感知
    print("4. 评分...")
    candidates = []
    for code, info in funds.items():
        name = info.get("fund_name", code)
        
        # RSI超买拦截
        pts = fund_charts.get(code, [])
        if len(pts) >= 60:
            timing = compute_entry_timing_score(pts, TODAY)
            if timing.get("should_warn") and GENE.get("block_overbought", False):
                print(f"   BLOCKED {name[:25]}: RSI超买({timing.get('rsi', 0):.0f})")
                continue
        
        try:
            fs = score_fund_backtest(code, name, fund_charts, None,
                fund_rules.get(code), fund_managers.get(code),
                TODAY, trading_by_date, fund_profiles.get(code))
            s = fs.total if hasattr(fs, 'total') else 3.0
        except Exception as e:
            s = max(1.0, min(5.0, 3.0))
        
        if s < min_score:
            continue
        
        # 费率感知：检查申购限额
        purchasable, reason = portfolio.is_purchasable(code)
        if not purchasable:
            print(f"   SKIP {name[:25]}: {reason}")
            continue
        
        candidates.append({"code": code, "name": name, "score": s})
    
    candidates.sort(key=lambda x: -x["score"])
    print(f"   通过评分: {len(candidates)} 只")
    
    # 5. 相关性过滤
    if portfolio.holdings and candidates:
        held_codes = list(portfolio.holdings.keys()) + [c["code"] for c in candidates]
        corr = compute_correlation_matrix(fund_charts, held_codes, TODAY, lookback=60)
        filtered = []
        for c in candidates:
            max_c = check_max_correlation(c["code"], list(portfolio.holdings.keys()), corr, 
                                          GENE.get("max_correlation", 0.85))
            if max_c <= GENE.get("max_correlation", 0.85):
                filtered.append(c)
            else:
                print(f"   FILTERED {c['name'][:25]}: 相关{max_c:.2f}")
        candidates = filtered
    
    # 6. LLM Skill分析（TOP5）
    print("5. LLM Skill分析...")
    skill_results = []
    if not _args.no_llm:
        for c in candidates[:5]:
            result = run_skill_analysis(c["code"], c["name"], c["score"], market)
            skill_results.append(result)
            if result["verdict"] == "veto":
                print(f"   VETO {c['name'][:25]}: {'; '.join(result['reasons'])}")
            elif result["reasons"]:
                print(f"   WARN {c['name'][:25]}: {'; '.join(result['reasons'])}")
    
    # 7. 卖出决策
    print("6. 卖出检查...")
    sell_actions = []
    for code in list(portfolio.holdings.keys()):
        h = portfolio.holdings[code]
        days = portfolio._holding_days(code, TODAY)
        
        # 场外基金费率感知：检查惩罚性赎回费
        is_short_term, penalty_reason = check_short_term_penalty(code, days)
        if is_short_term and days < 7:
            print(f"   HOLD {h['name'][:25]}: {penalty_reason}（避免惩罚性赎回费）")
            continue
        
        # 时间止损
        time_stop, ts_reason = check_time_stop(code, portfolio.holdings, TODAY)
        if time_stop:
            print(f"   SELL_TS {h['name'][:25]}: {ts_reason}")
            portfolio.sell(code, 0, 1.0, TODAY, "time_stop", True)
            sell_actions.append({"action": "SELL", "code": code, "name": h["name"], "reason": ts_reason})
            continue
        
        if days < GENE.get("min_holding_days", 60):
            continue
        
        # 标准止盈止损
        pts = fund_charts.get(code, [])
        actual_pnl = 0
        if pts:
            today_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if today_pts:
                latest_nav = (100 + float(today_pts[-1].get("yAxis", 0))) / 100
                buy_pts = [p for p in pts if p.get("xAxis", "")[:10] <= h.get("buy_date", TODAY)]
                if buy_pts:
                    buy_nav = (100 + float(buy_pts[-1].get("yAxis", 0))) / 100
                    if buy_nav > 0:
                        actual_pnl = (latest_nav / buy_nav - 1) * 100
        
        # 止盈
        tp_pct = GENE.get("take_profit_pct", 35)
        if actual_pnl >= tp_pct:
            portfolio.sell(code, 0, 1.0, TODAY, "take_profit", False)
            sell_actions.append({"action": "SELL", "code": code, "name": h["name"], 
                                 "reason": f"止盈+{actual_pnl:.0f}%"})
            print(f"   SELL_TP {h['name'][:25]}: +{actual_pnl:.0f}%")
        
        # 止损
        elif actual_pnl <= GENE.get("stop_loss_pct", -10):
            portfolio.sell(code, 0, 1.0, TODAY, "stop_loss", True)
            sell_actions.append({"action": "SELL", "code": code, "name": h["name"],
                                 "reason": f"止损{actual_pnl:.0f}%"})
            print(f"   SELL_SL {h['name'][:25]}: {actual_pnl:.0f}%")
        
        # 移动止盈
        elif GENE.get("trailing_tp_activate", 0) > 0 and actual_pnl >= GENE.get("trailing_tp_activate", 0):
            peak_nav = h.get("peak_nav", 1.0)
            current_nav = (100 + float(today_pts[-1].get("yAxis", 0))) / 100 if today_pts else 1.0
            if peak_nav > 0:
                dd = (current_nav / peak_nav - 1) * 100
                if dd < -GENE.get("trailing_tp_drawdown", 10):
                    portfolio.sell(code, 0, 1.0, TODAY, "trailing_tp", True)
                    sell_actions.append({"action": "SELL", "code": code, "name": h["name"],
                                         "reason": f"移动止盈 profit={actual_pnl:.0f}% dd={dd:.0f}%"})
                    print(f"   SELL_TTP {h['name'][:25]}: profit={actual_pnl:.0f}% dd={dd:.0f}%")
    
    # 8. 买入决策
    print("7. 买入...")
    buy_actions = []
    max_pos = GENE.get("max_position_pct", 20)
    cash_reserve = GENE.get("cash_reserve_pct", 0.1)
    cooldown_cfg = {"profit_days": GENE.get("cooldown_profit_days", 10),
                    "loss_days": GENE.get("cooldown_loss_days", 30)}
    
    for c in candidates:
        code = c["code"]
        if code in portfolio.holdings:
            continue
        if any(p["code"] == code for p in portfolio.pending_buys):
            continue
        if portfolio.is_in_cooldown(code, TODAY, cooldown_cfg):
            continue
        
        # LLM否决检查
        skill_result = next((r for r in skill_results if r["code"] == code), None)
        if skill_result and skill_result["verdict"] == "veto":
            print(f"   VETOED {c['name'][:25]}: {'; '.join(skill_result['reasons'])}")
            continue
        
        available = portfolio.cash * (1 - cash_reserve)
        per_position = available * max_pos / 100
        kelly = GENE.get("kelly_cap", 0.3)
        amount = min(per_position, available * kelly)
        amount = round(amount / 100) * 100
        
        if amount < 100:
            continue
        
        # 限额检查
        ok, limit_reason = check_purchase_limit(code, amount)
        if not ok:
            print(f"   LIMIT {c['name'][:25]}: {limit_reason}")
            continue
        
        # A/C份额推荐
        expected_hold = 90  # 预期持有90天
        recommended_class, class_reason = recommend_share_class(code, c["name"], expected_hold)
        
        if portfolio.buy(code, c["name"], amount, 1.0, TODAY):
            buy_actions.append({
                "action": "BUY", "code": code, "name": c["name"],
                "amount": amount, "score": c["score"],
                "share_class_recommended": recommended_class,
                "share_class_reason": class_reason,
            })
            print(f"   BUY {c['name'][:30]}: {amount:,.0f} (评分{c['score']:.1f} 推荐{recommended_class}类)")
    
    # 9. 同步持仓 + 计算市值
    vp["cash"] = portfolio.cash
    vp["total_fees"] = portfolio.total_fees
    
    holdings_market_value = 0
    vp_holdings = {}
    for code, h in portfolio.holdings.items():
        cb = h["cost"]
        mv = cb
        pts = fund_charts.get(code, [])
        if pts:
            today_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if today_pts:
                latest_nav = (100 + float(today_pts[-1].get("yAxis", 0))) / 100
                buy_pts = [p for p in pts if p.get("xAxis", "")[:10] <= h.get("buy_date", TODAY)]
                if buy_pts:
                    buy_nav = (100 + float(buy_pts[-1].get("yAxis", 0))) / 100
                    if buy_nav > 0:
                        mv = cb * (latest_nav / buy_nav)
        
        # 更新peak_nav
        if pts:
            today_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if today_pts:
                latest_nav = (100 + float(today_pts[-1].get("yAxis", 0))) / 100
                if "peak_nav" not in h or latest_nav > h.get("peak_nav", 0):
                    h["peak_nav"] = latest_nav
        
        holdings_market_value += mv
        days_held = portfolio._holding_days(code, TODAY)
        fee_info = get_fee_info(code)
        short_term, penalty = check_short_term_penalty(code, days_held)
        
        vp_holdings[code] = {
            "name": h["name"], "cost_basis": cb,
            "market_value": round(mv, 2),
            "buy_date": h.get("buy_date", TODAY),
            "buy_score": 3.0,
            "pnl_pct": round((mv - cb) / cb * 100, 2) if cb > 0 else 0,
            "days_held": days_held,
            "fee_info": fee_info,
            "short_term_penalty": short_term,
            "redeem_fee_current": get_redeem_fee(code, days_held),
            "peak_nav": h.get("peak_nav", 1.0),
        }
    vp["holdings"] = vp_holdings
    
    pending_value = sum(p.get("amount", 0) for p in portfolio.pending_buys)
    total_val = portfolio.cash + holdings_market_value + pending_value
    vp["snapshots"].append({"date": TODAY, "total_value": round(total_val, 2),
                            "cash": round(portfolio.cash, 2),
                            "holdings": len(portfolio.holdings),
                            "pending": len(portfolio.pending_buys)})
    vp["sell_history"] = portfolio.sell_history
    vp["pending"] = list(portfolio.pending_buys)
    save_vp(vp)

    # 9.5 PaperAccount 更新 (偏差追踪 + 熔断 + Phase 推进)
    paper_result = None
    if paper:
        snaps = vp.get("snapshots", [])
        max_val = max((s.get("total_value", INITIAL_CASH) for s in snaps), default=total_val)
        current_dd = max(0, (max_val - total_val) / max_val * 100) if max_val > 0 else 0
        signals_total = len(candidates)
        signals_exec = len(buy_actions)
        paper_result = paper.daily_update(total_val, signals_total, signals_exec, current_dd)
        if paper_result.get("frozen"):
            print(f"   🚨 熔断触发! 账户已冻结: {paper.status.get('frozen_reason', '')}")
        if paper_result.get("advanced"):
            print(f"   ✅ Phase 已推进!")

    # 10. 增强日报
    print("8. 日报...")
    lines = [
        f"# 增强版实盘模拟日报 {TODAY_CN}",
        f"",
        f"> 自选 {len(funds)} 只 | 市场 {market} | 门槛 {min_score} | 参数年化={evo.get('annualized', 'N/A')}%",
        f"",
        f"## 📊 市场状态",
        f"| 指标 | 值 |",
        f"|------|------|",
        f"| 市场状态 | {market} |",
        f"| 评分门槛 | {min_score} |",
        f"| 日期 | {TODAY} |",
        f"",
        f"## 💰 当前持仓",
        f"| 基金 | 成本 | 市值 | 盈亏 | 持有天数 | 申购费 | 管理费 | 赎回费(当前) | 短期惩罚 |",
        f"|------|------|------|------|----------|--------|--------|-------------|----------|",
    ]
    for code, h in vp_holdings.items():
        fi = h.get("fee_info", {})
        pnl = h.get("pnl_pct", 0)
        rf = h.get("redeem_fee_current", 0)
        stp = "⚠️是" if h.get("short_term_penalty") else "否"
        lines.append(f"| {h['name'][:20]} ({code}) | {h['cost_basis']:,.0f} | {h['market_value']:,.0f} | {pnl:+.1f}% | {h.get('days_held',0)}天 | {fi.get('purchase_fee',0):.1f}% | {fi.get('manage_fee',0):.2f}% | {rf*100:.2f}% | {stp} |")
    
    lines += [
        f"",
        f"## 🔴 卖出建议",
    ]
    if sell_actions:
        lines.append("| 基金 | 原因 |")
        lines.append("|------|------|")
        for a in sell_actions:
            lines.append(f"| {a['name']} ({a['code']}) | {a['reason']} |")
    else:
        lines.append("无卖出信号")
    
    lines += [
        f"",
        f"## 🟢 买入建议",
    ]
    if buy_actions:
        lines.append("| 基金 | 金额 | 评分 | 推荐份额 | 理由 |")
        lines.append("|------|------|------|----------|------|")
        for a in buy_actions:
            lines.append(f"| {a['name']} ({a['code']}) | {a['amount']:,.0f} | {a['score']:.1f} | {a['share_class_recommended']}类 | {a['share_class_reason']} |")
    else:
        lines.append("无买入信号")
    
    # LLM分析section
    lines += [
        f"",
        f"## 🤖 LLM Skill 分析",
    ]
    if skill_results:
        lines.append("| 基金 | 评分 | 判定 | 原因 | Skill命令 |")
        lines.append("|------|------|------|------|----------|")
        for sr in skill_results:
            reasons_str = "; ".join(sr.get("reasons", [])) or "无"
            cmds = " / ".join(sr.get("skill_commands", [])[:2])
            lines.append(f"| {sr['name'][:20]} ({sr['code']}) | {sr['score']:.1f} | {sr['verdict']} | {reasons_str} | `{cmds}` |")
    else:
        lines.append("LLM分析未启用（--no-llm）")
    
    # 风险提示
    lines += [
        f"",
        f"## ⚠️ 风险提示",
    ]
    risk_count = 0
    for code, h in vp_holdings.items():
        if h.get("short_term_penalty"):
            lines.append(f"- ⚠️ {h['name']}: 处于惩罚性赎回费期，避免近期卖出")
            risk_count += 1
        if h.get("pnl_pct", 0) < -5:
            lines.append(f"- 🔴 {h['name']}: 亏损{h['pnl_pct']:.1f}%，关注止损")
            risk_count += 1
    if risk_count == 0:
        lines.append("无风险提示")
    
    # 组合状态
    lines += [
        f"",
        f"## 📈 组合状态",
        f"| 指标 | 值 |",
        f"|------|------|",
        f"| 总资产 | {total_val:,.2f} |",
        f"| 现金 | {portfolio.cash:,.2f} |",
        f"| 持仓市值 | {holdings_market_value:,.2f} |",
        f"| 待确认 | {len(portfolio.pending_buys)} 笔 |",
        f"| 手续费 | {portfolio.total_fees:,.2f} |",
        f"| 收益率 | {((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}% |",
        f"| 持仓数 | {len(portfolio.holdings)} 只 |",
    ]

    # PaperAccount Phase 状态
    if paper and paper_result:
        snap = paper_result.get("snapshot", {})
        lines += [
            f"",
            f"## 🏁 PaperAccount 状态",
            f"| 指标 | 值 |",
            f"|------|------|",
            f"| Phase | {paper.phase} |",
            f"| 已运行 | {paper.elapsed} 天 |",
            f"| 目标天数 | {paper.cfg['target_days']} |",
            f"| 已部署资金 | {paper.data.get('deployed_cash', 0):,.0f} |",
            f"| 实际收益 | {snap.get('actual_return_pct', 0):+.2f}% |",
            f"| 理论收益 | {snap.get('theoretical_return_pct', 0):+.2f}% |",
            f"| 偏差 | {snap.get('deviation_pct', 0):.2f}% |",
            f"| 执行率 | {snap.get('execution_rate', 0):.1f}% |",
            f"| 当前回撤 | {snap.get('current_dd', 0):.2f}% |",
            f"| 熔断阈值 | {paper.cfg['cb_dd']}% |",
            f"| 冻结 | {'是' if paper.data.get('frozen') else '否'} |",
        ]
        if paper.status.get("pending_advance"):
            lines.append(f"| 推进队列 | {paper.status.get('advance_to', '?')} @ {paper.status.get('advance_at', '?')} |")

    lines += [
        f"",
        f"---",
        f"*{TODAY_CN} 冠军策略模拟 | Phase={paper.phase if paper else 'N/A'}*",
    ]
    
    (SIM_DIR / f"enhanced_{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")
    
    # 保存机器报告
    ai_report = {
        "date": TODAY,
        "market": market,
        "min_score": min_score,
        "candidates_top5": [{"code": c["code"], "name": c["name"], "score": c["score"]} for c in candidates[:5]],
        "buy_recommendations": buy_actions,
        "sell_recommendations": sell_actions,
        "holdings": vp_holdings,
        "skill_analysis": skill_results,
        "portfolio": {"total_value": round(total_val, 2), "cash": round(portfolio.cash, 2), "fees": round(portfolio.total_fees, 2)},
    }
    (SIM_DIR / f"enhanced_{TODAY}.json").write_text(json.dumps(ai_report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"   日报: {SIM_DIR / f'enhanced_{TODAY}.md'}")
    print(f"   机器报告: {SIM_DIR / f'enhanced_{TODAY}.json'}")
    print(f"\n=== 完成: 总资产 {total_val:,.0f} ({((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%) ===")


if __name__ == "__main__":
    run()
