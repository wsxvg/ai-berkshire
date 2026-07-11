#!/usr/bin/env python3
"""Generate a clean light-themed HTML report with scoring + recommendations."""
import json, sys
from pathlib import Path
from datetime import date

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
DATA_DIR = _PROJECT_ROOT / "data"
REPORTS_DIR = _PROJECT_ROOT / "reports" / "auto"
CACHE_DIR = _PROJECT_ROOT / "data" / "fund_cache"

def load_cache(name, default=None):
    p = Path(name)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})

today = date.today().isoformat()
trading = load_cache(DATA_DIR / "trading_records_cache.json", {})
status = load_cache(DATA_DIR / "auto" / "status.json", {})
snapshot = load_cache(DATA_DIR / "holdings_snapshot.json", {})
fund_scores = status.get("fund_scores", {})

_code_to_name = {}
if "holdings" in snapshot:
    for user, funds in snapshot["holdings"].items():
        if isinstance(funds, list):
            for f in funds:
                if isinstance(f, dict) and f.get("code") and f.get("name"):
                    _code_to_name[f["code"]] = f["name"]
for fname, fd in trading.get("funds", {}).items():
    code = fd.get("fund_code") or fd.get("code", "")
    if code and not _code_to_name.get(code):
        _code_to_name[code] = fname

is_td = status.get("is_trading_day", True)
funds = trading.get("funds", {})
my_holdings = status.get("my_holdings", [])
my_holdings = [h for h in my_holdings if h.get("code")]

_score_history = []
_hp = DATA_DIR / "fund_scores_history.jsonl"
if _hp.exists():
    try:
        for line in _hp.read_text("utf-8").strip().split("\n"):
            if line: _score_history.append(json.loads(line))
    except: pass
_prev_scores = _score_history[-2]["scores"] if len(_score_history) >= 2 else {}

def _get_limit(code):
    p = CACHE_DIR / f"trade_rules_{code}.json"
    if p.exists():
        try:
            d = json.loads(p.read_text("utf-8"))
            return d.get("day_limit") or d.get("dayLimit") or 0
        except: pass
    return 0

_my_codes = {h["code"] for h in my_holdings}

strong_buy, buy_signal, sell_signals = [], [], []
for fname, fd in funds.items():
    bc = fd.get("buy_count", 0); sc = fd.get("sell_count", 0)
    code = fd.get("fund_code") or fd.get("code", "")
    si = fund_scores.get(code, {})
    item = {"name": fname, "code": code, "buy_count": bc, "sell_count": sc,
            "buy_users": fd.get("buy_users", []), "sell_users": fd.get("sell_users", []),
            "score_total": si.get("total"), "score_verdict": si.get("verdict", "")}
    if bc >= 3: item["signal"] = "strong_buy"; strong_buy.append(item)
    elif bc >= 2: item["signal"] = "buy"; buy_signal.append(item)
    elif sc >= 2: item["signal"] = "sell"; sell_signals.append(item)
strong_buy.sort(key=lambda x: (x["score_total"] or 0, x["buy_count"]), reverse=True)

rec_buy = [it for items, thr in [(strong_buy, 3.3), (buy_signal, 3.3)] for it in items if (it.get("score_total") or 0) >= thr][:5]
rec_watch = []
for fname, fd in funds.items():
    code = fd.get("fund_code") or fd.get("code", "")
    t = fund_scores.get(code, {}).get("total")
    if t is not None and t >= 3.3 and fd.get("buy_count", 0) < 2:
        rec_watch.append({"name": fname, "code": code, "score_total": t})
rec_sell = sell_signals[:5]

def _trend(code):
    c = fund_scores.get(code, {}).get("total")
    p = _prev_scores.get(code, {}).get("total") if _prev_scores else None
    if c is None or p is None: return ""
    d = c - p
    if d >= 0.1: return f'<span class="tr-up">↑{d:.2f}</span>'
    if d <= -0.1: return f'<span class="tr-down">↓{abs(d):.2f}</span>'
    return '<span class="tr-flat">→</span>'

def dim_bars(s):
    dims = [("质量","quality",0.25),("成本","cost",0.20),("经理","manager",0.20),("动量","momentum",0.15),("聪明钱","smart_money",0.20)]
    r = ""
    for cn,ck,cw in dims:
        v = s.get(ck,0); pct = min(v/5*100,100)
        col = "#16a34a" if v>=4 else "#d97706" if v>=3 else "#dc2626"
        r += f'<div class="db"><span class="dl">{cn}</span><div class="dt"><div class="df" style="width:{pct:.0f}%;background:{col}"></div></div><span class="dv">{v:.1f}</span></div>'
    return r

def score_td(s):
    t = s.get("score_total")
    if t is None: return '<td class="sn">—</td>'
    return f'<td class="s{"b" if t>=4 else "w" if t>=3.3 else "p"}">{t:.1f}</td>'

def _tg(name):
    t = []
    if "QDII" in name: t.append("QDII")
    if "指数" in name or "ETF" in name: t.append("指")
    if name.endswith("C"): t.append("C")
    return "".join(f'<span class="tg tg-{k}">{k}</span>' for k in t)

def _my_row(h):
    code = h.get("code",""); name = h.get("name","")[:20]
    amt = h.get("amount","—"); pr = h.get("profit_rate","—")
    fd = {}
    for fn,fdata in funds.items():
        if fdata.get("fund_code")==code or fdata.get("code")==code: fd=fdata; break
    bc = fd.get("buy_count",0); sc = fd.get("sell_count",0)
    si = fund_scores.get(code,{}); t = si.get("total")
    ss = f'{t:.1f}' if t is not None else "—"
    lim = _get_limit(code); ls = f'¥{int(lim)}/天' if lim and lim>0 and lim!=float('inf') else "—"
    return f'<tr><td>{name}</td><td style="font-family:monospace">{code}</td><td>{amt}</td><td>{pr}</td><td>{bc}人</td><td>{sc}人</td><td class="s{"b" if t and t>=4 else "w" if t and t>=3.3 else "p"}">{ss}</td><td style="font-size:11px">{ls}</td></tr>'

def _rc(item, action, color, label):
    t = item.get("score_total"); ss = f'{t:.1f}' if t else "—"
    code = item["code"]; name = item["name"][:24]
    lim = _get_limit(code); ls = f'¥{int(lim)}/天' if lim and lim>0 and lim!=float('inf') else ""
    rsn = f'{item.get("buy_count",0)}人买入'
    if action=="sell": rsn = f'{item.get("sell_count",0)}人卖出'
    elif action=="watch": rsn = f'评分{ss}'
    ht = '<span class="rc-hold">你持有</span>' if code in _my_codes else ""
    return f'<div class="rc rc-{action}"><span class="rc-icon">{color}</span><span class="rc-label">{label}</span><span class="rc-name">{name}{ht}</span><span class="rc-code">{code}</span><span class="rc-score">{ss}</span>{_trend(code)}<span class="rc-limit">{ls}</span><span class="rc-reason">{rsn}</span></div>'

top = sorted([(c,s) for c,s in fund_scores.items() if s.get("verdict") in ("buy","watch")], key=lambda x: x[1]["total"], reverse=True)[:6]
score_html = ""
for code,s in top:
    n = _code_to_name.get(code,code)[:16]; v = s.get("verdict","")
    vl = {"buy":"建议买入","watch":"值得关注","pass":"建议跳过"}.get(v,v)
    score_html += f'<div class="sc"><div class="sh"><span class="scode">{code}</span><span class="sname">{n}</span>{_trend(code)}<span class="st">{s.get("total",0):.1f}</span><span class="sv sv-{v}">{vl}</span></div>{dim_bars(s)}</div>'

sb_rows = ""
for i,item in enumerate(strong_buy,1):
    t = item.get("score_total"); rc = ' class="sb"' if t and t>=4 else ""
    sb_rows += f'<tr{rc}><td>{i}</td><td>{item["name"]}</td><td style="font-family:monospace">{item["code"]}</td><td><span class="tb">{item["buy_count"]}人</span></td>{score_td(item)}<td>{_tg(item["name"])}</td><td style="font-size:12px">{", ".join(item["buy_users"][:3])}</td></tr>'

sell_rows = ""
for item in sell_signals:
    sell_rows += f'<tr><td>{item["name"]}</td><td style="font-family:monospace">{item["code"]}</td><td><span class="ts">{item["sell_count"]}人卖出</span></td>{score_td(item)}<td style="font-size:12px">{", ".join(item["sell_users"][:3])}</td></tr>'
if not sell_rows: sell_rows = '<tr><td colspan="5" style="text-align:center;color:#9ca3af;padding:24px">暂无卖出信号</td></tr>'

rec_html = "".join(_rc(it,"buy","🟢","买入") for it in rec_buy)
rec_html += "".join(_rc(it,"watch","👁","关注") for it in rec_watch)
rec_html += "".join(_rc(it,"sell","🔴","卖出") for it in rec_sell)
if not rec_html: rec_html = '<div class="rc-empty">暂无明确操作建议</div>'

_af = []
for it in rec_buy:
    code=it["code"]; lim=_get_limit(code)
    _af.append({"code":code,"name":it["name"][:20],"score":it.get("score_total",0) or 0,"buy_count":it.get("buy_count",0),"day_limit":float(lim) if lim and lim!=float('inf') else 999999,"is_qdii":"QDII" in it["name"],"my_hold":code in _my_codes})
_aj = json.dumps(_af,ensure_ascii=False)

# Build comparison data (top funds side by side)
_compare = []
for code, s in top[:4]:
    _compare.append({
        "code": code,
        "name": _code_to_name.get(code, code)[:12],
        "quality": s.get("quality", 0),
        "cost": s.get("cost", 0),
        "manager": s.get("manager", 0),
        "momentum": s.get("momentum", 0),
        "smart_money": s.get("smart_money", 0),
        "total": s.get("total", 0),
    })

def _cmp_bar(v, label, color):
    pct = min(v/5*100, 100)
    return f'<div class="cmp-row"><span class="cmp-l">{label}</span><div class="cmp-t"><div class="cmp-f" style="width:{pct:.0f}%;background:{color}"></div></div><span class="cmp-v">{v:.1f}</span></div>'

_compare_html = ""
for c in _compare:
    _compare_html += f'<div class="cmp-card"><div class="cmp-h"><span class="cmp-name">{c["name"]}</span><span class="cmp-code">{c["code"]}</span><span class="cmp-total">{c["total"]:.1f}</span></div>'
    _compare_html += _cmp_bar(c["quality"], "质量", "#2563eb")
    _compare_html += _cmp_bar(c["cost"], "成本", "#16a34a")
    _compare_html += _cmp_bar(c["manager"], "经理", "#d97706")
    _compare_html += _cmp_bar(c["momentum"], "动量", "#8b5cf6")
    _compare_html += _cmp_bar(c["smart_money"], "聪明钱", "#ec4899")
    _compare_html += '</div>'

# Check index quotes for market overview
_index_quotes = ""
try:
    from jd_finance_api import get_stock_quotes
    iq = get_stock_quotes(["SH-000001", "SZ-399001", "SZ-399006", "HK-HSI", "AMEX-IXIC", "SH-000300"])
    if iq:
        idx_names = {"SH-000001": "上证指数", "SZ-399001": "深证成指", "SZ-399006": "创业板指",
                     "HK-HSI": "恒生指数", "AMEX-IXIC": "纳斯达克", "SH-000300": "沪深300"}
        _index_quotes = "<table><tr><th>指数</th><th>点位</th><th>涨跌幅</th></tr>"
        for code, d in iq.items():
            color = "#dc2626" if d.get("change_pct", 0) < 0 else "#16a34a"
            _index_quotes += f'<tr><td>{idx_names.get(code, code)}</td><td>{d.get("last_price", 0):.1f}</td><td style="color:{color}">{d["change_pct"]:.2f}%</td></tr>'
        _index_quotes += "</table>"
except: pass

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Berkshire 基金扫描 — {today}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei","PingFang SC",sans-serif;background:#f8fafc;color:#1e293b;padding:32px 24px;max-width:1100px;margin:auto}}
h1{{font-size:22px;font-weight:700;color:#1e293b;margin-bottom:2px}}
.subtitle{{color:#64748b;font-size:13px;margin-bottom:20px}}
.sg{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}}
.si{{background:#fff;border-radius:8px;padding:14px;text-align:center;border:1px solid #e2e8f0}}
.si .n{{font-size:26px;font-weight:700;color:#2563eb}}
.si .l{{font-size:11px;color:#64748b;margin-top:2px}}
.rc-list{{display:flex;flex-direction:column;gap:6px;margin:12px 0}}
.rc{{display:flex;align-items:center;gap:8px;background:#fff;border-radius:6px;padding:10px 12px;border:1px solid #e2e8f0;font-size:13px}}
.rc-icon{{font-size:16px;width:24px}}
.rc-label{{font-size:11px;font-weight:600;width:32px;flex-shrink:0}}
.rc-name{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.rc-code{{font-family:monospace;font-size:11px;color:#64748b;width:80px}}
.rc-score{{font-weight:700;width:32px;text-align:right}}
.rc-limit{{font-size:10px;color:#d97706;width:60px;text-align:right}}
.rc-reason{{font-size:11px;color:#64748b;width:120px;text-align:right}}
.rc-hold{{display:inline-block;font-size:9px;background:#dbeafe;color:#2563eb;padding:0 4px;border-radius:3px;margin-left:4px;vertical-align:middle}}
.rc-buy .rc-label{{color:#16a34a}}
.rc-watch .rc-label{{color:#d97706}}
.rc-sell .rc-label{{color:#dc2626}}
.rc-empty{{text-align:center;color:#94a3b8;padding:20px}}
.tr-up{{font-size:10px;color:#16a34a;font-weight:600;margin-left:2px}}
.tr-down{{font-size:10px;color:#dc2626;font-weight:600;margin-left:2px}}
.tr-flat{{font-size:10px;color:#94a3b8;margin-left:2px}}
table{{width:100%;border-collapse:collapse;margin:6px 0;font-size:13px}}
th{{background:#f1f5f9;color:#475569;padding:7px 8px;text-align:left;font-size:11px;font-weight:600;border-bottom:2px solid #e2e8f0}}
td{{padding:6px 8px;border-bottom:1px solid #f1f5f9;font-size:12px}}
tr:hover{{background:#f8fafc}}
tr.sb td:first-child{{color:#2563eb;font-weight:700}}
.tb{{display:inline-block;background:#dcfce7;color:#16a34a;padding:1px 7px;border-radius:3px;font-size:11px;font-weight:600}}
.ts{{background:#fef2f2;color:#dc2626;padding:1px 7px;border-radius:3px;font-size:11px;font-weight:600}}
.tg{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:9px;margin:0 1px;font-weight:500}}
.tg-QDII{{background:#eff6ff;color:#2563eb}}
.tg-指{{background:#f0fdf4;color:#16a34a}}
.tg-C{{background:#faf5ff;color:#9333ea}}
.sb{{color:#2563eb;font-weight:700}}
.sw{{color:#d97706}}
.sp{{color:#9ca3af}}
.sn{{color:#e2e8f0}}
.ss{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin:10px 0}}
.sc{{background:#fff;border-radius:8px;padding:12px;border:1px solid #e2e8f0}}
.sh{{display:flex;align-items:center;gap:6px;margin-bottom:8px}}
.scode{{font-size:11px;color:#64748b;font-family:monospace}}
.sname{{font-size:12px;color:#1e293b;margin-left:6px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}}
.st{{font-size:20px;font-weight:700;color:#2563eb;margin-left:auto}}
.sv{{font-size:10px;padding:2px 8px;border-radius:8px;font-weight:600}}
.sv-buy{{background:#dcfce7;color:#16a34a}}
.sv-watch{{background:#fef3c7;color:#d97706}}
.sv-pass{{background:#f1f5f9;color:#94a3b8}}
.db{{display:flex;align-items:center;gap:4px;margin:2px 0}}
.dl{{font-size:10px;color:#64748b;width:36px;flex-shrink:0}}
.dt{{flex:1;height:5px;background:#f1f5f9;border-radius:2px;overflow:hidden}}
.df{{height:100%;border-radius:2px}}
.dv{{font-size:10px;font-weight:600;width:20px;text-align:right;color:#475569}}
h2{{font-size:16px;color:#1e293b;margin:22px 0 8px;padding-bottom:6px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:6px}}
h2 .bd{{background:#f1f5f9;color:#64748b;font-size:10px;padding:1px 7px;border-radius:8px}}
.note{{color:#64748b;font-size:12px;margin:6px 0}}
.al{{background:#fff;border-radius:8px;padding:14px;margin:10px 0;border:1px solid #e2e8f0}}
.al h3{{font-size:14px;margin-bottom:10px}}
.al-row{{display:flex;align-items:center;gap:10px;margin:8px 0;flex-wrap:wrap}}
.al-input{{font-size:16px;padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;width:160px;outline:none}}
.al-input:focus{{border-color:#2563eb;box-shadow:0 0 0 2px rgba(37,99,235,0.1)}}
.al-btn{{background:#2563eb;color:#fff;border:none;padding:7px 18px;border-radius:6px;font-size:14px;cursor:pointer}}
.al-btn:hover{{background:#1d4ed8}}
.al-table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}}
.al-table th{{background:#f1f5f9;color:#475569;padding:6px 8px;text-align:left;font-size:11px;border-bottom:2px solid #e2e8f0}}
.al-table td{{padding:5px 8px;border-bottom:1px solid #f1f5f9;font-size:12px}}
.al-amt{{font-weight:700;color:#16a34a}}
.al-dca{{font-size:11px;color:#d97706}}
.al-total{{font-size:14px;font-weight:700;color:#1e293b;margin-top:6px}}
.al-detail{{font-size:11px;color:#64748b;margin-top:4px;line-height:1.5}}
.cmp-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;margin:10px 0}}
.cmp-card{{background:#fff;border-radius:8px;padding:12px;border:1px solid #e2e8f0}}
.cmp-h{{display:flex;align-items:center;gap:6px;margin-bottom:8px}}
.cmp-name{{font-size:12px;font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.cmp-code{{font-family:monospace;font-size:10px;color:#64748b}}
.cmp-total{{font-size:18px;font-weight:700;color:#2563eb}}
.cmp-row{{display:flex;align-items:center;gap:4px;margin:2px 0}}
.cmp-l{{font-size:9px;color:#64748b;width:32px;flex-shrink:0}}
.cmp-t{{flex:1;height:5px;background:#f1f5f9;border-radius:2px;overflow:hidden}}
.cmp-f{{height:100%;border-radius:2px}}
.cmp-v{{font-size:10px;font-weight:600;width:18px;text-align:right;color:#475569}}
.footer{{text-align:center;color:#9ca3af;font-size:11px;margin-top:36px;padding-top:12px;border-top:1px solid #e2e8f0}}
</style>
</head>
<body>

<h1>AI Berkshire 基金扫描</h1>
<p class="subtitle">{today} · {"交易日" if is_td else "非交易日"} · 跟踪{status.get("user_count",21)}位大佬 · {len(fund_scores)} 只基金已评分</p>

<div class="sg">
<div class="si"><div class="n">{len(rec_buy)}</div><div class="l">建议买入</div></div>
<div class="si"><div class="n">{len(rec_watch)}</div><div class="l">值得关注</div></div>
<div class="si"><div class="n">{len(rec_sell)}</div><div class="l">卖出信号</div></div>
<div class="si"><div class="n">{len(strong_buy)}</div><div class="l">强共识买入</div></div>
</div>

<h2>操作建议 <span class="bd">{len(rec_buy)+len(rec_watch)+len(rec_sell)}</span></h2>
<div class="rc-list">{rec_html}</div>
<p class="note">🟢 买入 = 评分≥3.3 + 大佬共识 · 👁 关注 = 评分≥3.3 · 🔴 卖出 = 卖出信号 · ↑↓ 较昨日变化</p>

<h2>你的持仓 <span class="bd">{len(my_holdings)}</span></h2>
<table>
<tr><th>基金</th><th>代码</th><th>持有金额</th><th>收益率</th><th>大佬买入</th><th>大佬卖出</th><th>评分</th><th>限购</th></tr>
{"".join(_my_row(h) for h in my_holdings[:20]) if my_holdings else '<tr><td colspan="8" style="text-align:center;color:#9ca3af;padding:16px">暂无持仓数据</td></tr>'}
</table>

<h2>资金分配器 <span class="bd">凯利公式</span></h2>
<div class="al">
<h3>输入闲钱，自动计算推荐投入</h3>
<div class="al-row">
<span>金额：</span>
<input type="number" class="al-input" id="cashInput" value="10000" oninput="calcAlloc()" min="0" step="1000"><span>元</span>
<button class="al-btn" onclick="calcAlloc()">计算</button>
</div>
<p class="note">凯利公式 f*=(p×b-q)/b · 预留20%现金 · 单只≤总资金15% · 日限约束</p>
<div id="allocResult"></div>
</div>
<script>
var FUNDS = {_aj};
function calcAlloc(){{
var t=parseFloat(document.getElementById('cashInput').value)||0,a=t*0.8,r=[],gt=0;
for(var f of FUNDS){{if(f.score<3.3)continue;var p=f.score/5.0,b=Math.max(p*2,0.5),k=Math.max(0,Math.min((p*b-(1-p))/b,0.2));f._s=Math.round(Math.min(a*k*f.score/5,f.day_limit<999999?f.day_limit:999999,t*0.15)/100)*100;f._k=k;}}
FUNDS.sort(function(a,b){{return b.score-a.score;}});var al=0;
for(var f of FUNDS){{if(f.score<3.3||al>=a)continue;if(al+f._s>a)f._s=Math.round((a-al)/100)*100;if(f._s<100)continue;al+=f._s;gt+=f._s;var ht=f.my_hold?' (已持有)':'',dc='';if(f.day_limit<999999&&f._s>f.day_limit){{var dcaAmt=Math.min(f.day_limit,Math.max(100,Math.round(f._s/20/100)*100));dc='<span class="al-dca">→ 建议日定投 ¥'+dcaAmt+'/天</span>';}}r.push('<tr><td>'+f.name+ht+'</td><td style="font-family:monospace">'+f.code+'</td><td>'+f.score.toFixed(2)+'</td><td class="al-amt">¥'+f._s.toLocaleString()+'</td><td>'+dc+'</td></tr>');}}
var h=r.length?'<table class="al-table"><tr><th>基金</th><th>代码</th><th>评分</th><th>建议金额</th><th>执行策略</th></tr>'+r.join('')+'</table><div class="al-total">建议总投入：¥'+gt.toLocaleString()+' / 可用 ¥'+Math.round(a).toLocaleString()+'（留存 ¥'+Math.round(t*0.2).toLocaleString()+'）</div>':'<p style="color:#94a3b8;padding:12px;text-align:center">暂无评分达标的基金</p>';
document.getElementById('allocResult').innerHTML=h;
}}
calcAlloc();
</script>

<h2>强共识买入 <span class="bd">{len(strong_buy)}</span></h2>
<table>
<tr><th>#</th><th>基金</th><th>代码</th><th>共识</th><th>评分</th><th>类型</th><th>参与大佬</th></tr>
{sb_rows}
</table>

<h2>五维评分详情 <span class="bd">{len(fund_scores)}</span></h2>
<p class="note">质量×25% + 成本×20% + 经理×20% + 动量×15% + 聪明钱×20% + 穿透估值(质量子项10%)</p>
<div class="ss">{score_html if score_html else '<div class="sc" style="text-align:center;color:#9ca3af;padding:20px">今日无评分≥3.3的基金</div>'}</div>

<h2>多基金对比 <span class="bd">TOP {len(_compare)}</span></h2>
<p class="note">五维评分横向对比，维度条越长表示该维度评分越高</p>
<div class="cmp-grid">{_compare_html}</div>

<h2>市场指数 <span class="bd">实时行情</span></h2>
<div class="al" style="padding:10px">{_index_quotes if _index_quotes else '<p style="color:#94a3b8;text-align:center;padding:8px">暂无数据</p>'}</div>

<h2>卖出信号</h2>
<table><tr><th>基金</th><th>代码</th><th>信号</th><th>评分</th><th>卖出大佬</th></tr>{sell_rows}</table>

<div class="footer">
<p>AI Berkshire · 京东金融API · 五维评分 v1.2 · 穿透估值已接入 · {today}</p>
<p style="margin-top:2px">⚠️ 不构成投资建议。大佬买 ≠ 你该买。</p>
</div>

</body></html>'''

html_path = REPORTS_DIR / f"scan-{today}.html"
html_path.parent.mkdir(parents=True, exist_ok=True)
html_path.write_text(html, encoding="utf-8")
print(f"HTML: {html_path}")