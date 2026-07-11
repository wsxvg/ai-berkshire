# -*- coding: utf-8 -*-
"""飞书消息推送工具 — 使用飞书自建应用API"""
import json, os, sys, time, urllib.request, argparse
from pathlib import Path
from datetime import date

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 从 huohua-wds 项目提取的配置
# 生产环境中通过环境变量覆盖
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "cli_a933badfd57bdbde")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "zliAQFZ61YOVdhSz8vecahozbGz6Ym5j")
FEISHU_USER_ID = os.getenv("FEISHU_USER_ID", "ou_67774e11bf8d8cf2b981cf2b09bac038")


def _get_token():
    """获取飞书 tenant_access_token"""
    payload = json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get("tenant_access_token")
    except Exception as e:
        print(f"  [FEISHU] token failed: {e}")
        return None


def _send_card(card: dict) -> bool:
    """发送飞书卡片消息"""
    token = _get_token()
    if not token:
        return False

    payload = json.dumps({
        "receive_id": FEISHU_USER_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result.get("code") == 0:
            print(f"  [FEISHU] push OK")
            return True
        else:
            print(f"  [FEISHU] push failed: {result.get('msg','')}")
            return False
    except Exception as e:
        print(f"  [FEISHU] push error: {e}")
        return False


def _load_report():
    latest = _PROJECT_ROOT / "reports" / "auto" / "latest.md"
    return latest.read_text("utf-8") if latest.exists() else None


def _load_status():
    sp = _PROJECT_ROOT / "data" / "auto" / "status.json"
    if sp.exists():
        try: return json.loads(sp.read_text("utf-8"))
        except: return {}
    return {}


def push_report():
    """推送结构化基金报告到飞书，含买卖建议"""
    status = _load_status()
    today = date.today().isoformat()
    is_td = status.get("is_trading_day", False)

    # ── 辅助: 行业检测 ──
    def _sec(name):
        n = name or ""
        if "半导体" in n or "芯片" in n: return "半导体"
        if "科技" in n or "信息" in n or "互联网" in n: return "科技"
        if "医疗" in n or "医药" in n: return "医疗"
        if "消费" in n: return "消费"
        if "新能源" in n or "能源" in n: return "新能源"
        if "金融" in n or "银行" in n: return "金融"
        if "混合" in n or "成长" in n or "价值" in n or "精选" in n: return "混合"
        if "指数" in n or "ETF" in n or "联接" in n: return "指数"
        return "其他"

    # ── 1. 计算当前持仓行业占比 ──
    holdings = status.get("my_holdings", [])
    sec_vals = {}
    for h in holdings:
        n = h.get("name", "")
        mv = float(str(h.get("market_value", 0) or h.get("cost_value", 0) or h.get("amount", 0) or 0).replace(",", ""))
        s = _sec(n)
        sec_vals[s] = sec_vals.get(s, 0) + mv
    total_val = sum(sec_vals.values()) or 1
    sec_pct = {s: v / total_val * 100 for s, v in sec_vals.items()}

    # ── 2. 月度预算 ──
    from tools.monthly_budget import auto_detect_spent
    _budget = auto_detect_spent(holdings) if holdings else load()
    _remaining = max(0, _budget["budget"] - _budget["spent"])
    _monthly = _budget["budget"]

    # ── 3. 生成买卖建议 ──
    signals = status.get("cross_signals", [])
    recommend_buy = []
    recommend_blocked = []

    # 计算建议金额（凯利简化版）
    _valid_signals = []
    for s in signals:
        fn = s.get("fund_name", "") or "未知"
        sec = _sec(fn)
        cur = sec_pct.get(sec, 0)
        if cur < 24:
            _valid_signals.append(s)

    if _valid_signals:
        # 预留20%备用金，剩余按信号平均分配
        _available = _remaining * 0.8
        _per_fund = max(100, int(_available / max(len(_valid_signals), 1) / 100) * 100)
        # 单笔上限
        _per_fund = min(_per_fund, 2000)

    for i, s in enumerate(signals):
        fn = s.get("fund_name", "") or "未知"
        sec = _sec(fn)
        cur = sec_pct.get(sec, 0)
        if cur >= 24:
            recommend_blocked.append(f"⛔ {fn}  ({sec}已达{cur:.0f}% > 24%)")
        elif _remaining > 0:
            amt = _per_fund if i < len(_valid_signals) else 0
            recommend_buy.append(f"🟢 {fn}  ¥{amt:,}  ({sec} {cur:.0f}%)")

    # ── 3. 账户概览 ──
    user_count = status.get("user_count", 0)
    summary = f"**跟踪用户**: {user_count}人  **持仓**: {len(holdings)}只"
    if total_val:
        summary += f"\n**总资产**: ¥{total_val:,.0f}"

    # 本月可用资金
    summary += f"\n**月预算**: ¥{_monthly:,}  **已用**: ¥{_budget['spent']:,}  **可用**: ¥{_remaining:,}"

    # ── 4. 行业分布 ──
    sec_lines = []
    for s, p in sorted(sec_pct.items(), key=lambda x: -x[1])[:6]:
        bar = "█" * int(p / 4)
        flag = "⚠️" if p >= 24 else "✅"
        sec_lines.append(f"{flag} {s} {p:.0f}% {bar}")
    sector_text = "\n".join(sec_lines) if sec_lines else "暂无持仓"

    # ── 5. 全平台大佬排行榜 ──
    rank_lines = []
    ts = status.get("timestamp", "未知")
    try:
        import sys as _s2
        _s2.path.insert(0, str(_PROJECT_ROOT))
        from tools.jd_finance_api import _api_form, _ensure_cookies

        _cookies = _ensure_cookies()
        _data = _api_form("gw2/generic/redEnv001/h5/m/queryFundFirmOfferRecommend",
            {"rankType":401,"pageSize":10,"rankSortBy":1,"pin":"","skuId":"","recommendTargetUidList":[],"clientType":"android","extParams":{"requestFrom":"h5"},"clientVersion":"9.9.9"},
            cookies=_cookies)
        _list = _data.get("resultData",{}).get("data",{}).get("fundRankList",[])
        for i, u in enumerate(_list[:5], 1):
            _info = u.get("userInfo",{})
            _name = _info.get("userName","")
            _val = u.get("rankColumnValue",{}).get("text","")
            _col = u.get("rankColumnName",{}).get("text","近1年").replace("收益率","")
            _medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            rank_lines.append(f"{_medal} {_name[:8]:8s} {_col}{_val}")
    except Exception as e:
        rank_lines.append(f"加载失败: {e}")

    rank_text = "\n".join(rank_lines) if rank_lines else "暂无数据"

    # ── 构建卡片 ──
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**{'📈 交易日' if is_td else '📅 非交易日'} | {today}**"}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**📊 账户概览**\n{summary}"}},
        {"tag": "hr"},
    ]

    # 推荐买入
    if recommend_buy:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**✅ 推荐买入**\n" + "\n".join(recommend_buy[:5])}})
        elements.append({"tag": "hr"})

    # 受限提示
    block_text = ""
    if recommend_blocked:
        block_text += "\n".join(recommend_blocked[:3])
    if block_text:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**⛔ 受限**\n{block_text}"}})
        elements.append({"tag": "hr"})

    # 行业分布
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**📂 行业分布**\n{sector_text}"}})
    elements.append({"tag": "hr"})

    # 大佬排名
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🏆 大佬收益率排名**\n{rank_text}"}})
    elements.append({"tag": "hr"})

    # 按钮
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看完整报告"},
            "type": "primary",
            "multi_url": {"url": "https://github.com/wsxvg/ai-berkshire/actions", "android_url": "", "ios_url": ""},
        }],
    })
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"AI Berkshire · {today} · 数据更新:{ts[:16]} · 仅供参考,投资有风险"}],
    })

    card = {
        "header": {"title": {"tag": "plain_text", "content": f"AI Berkshire {today}"}, "template": "blue"},
        "elements": elements,
    }

    return _send_card(card)


def push_text(title: str, content: str, color: str = "blue") -> bool:
    """发送简单文本卡片"""
    card = {
        "header": {"title": {"tag": "plain_text", "content": title}, "template": color},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
    }
    return _send_card(card)


def push_alert(stock: str, reason: str, detail: str = "") -> bool:
    """发送预警消息"""
    card = {
        "header": {"title": {"tag": "plain_text", "content": f"⚠ {stock} 预警"}, "template": "red"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**原因**: {reason}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": detail or "无详情"}},
        ],
    }
    return _send_card(card)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="飞书推送")
    parser.add_argument("--report", action="store_true", help="推送当日基金报告")
    parser.add_argument("--text", type=str, help="推送文本")
    parser.add_argument("--title", type=str, default="AI Berkshire")
    parser.add_argument("--color", type=str, default="blue")
    parser.add_argument("--alert", type=str, help="推送预警")
    parser.add_argument("--detail", type=str, default="")
    args = parser.parse_args()

    if args.report:
        push_report()
    elif args.text:
        push_text(args.title, args.text, args.color)
    elif args.alert:
        push_alert(args.alert, args.detail)
    else:
        print("Usage: python tools/feishu_push.py --report")
        print("       python tools/feishu_push.py --text '消息内容'")
        print("       python tools/feishu_push.py --alert '股票名' --detail '预警详情'")