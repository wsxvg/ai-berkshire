# -*- coding: utf-8 -*-
"""三年全周期对比报告生成器
读取 _results_3y/*.json + 解析 _test_regime_3y_result.txt
按加权分排名, 输出《三年全周期对比报告》

加权分 = 全周期收益×0.3 + 段A×0.15 + 段B×0.15 + 段C×0.2 + 月胜率×0.1 + 卡玛×0.1
"""
import json, os, re, glob

OUT_DIR = '_results_3y'
REPORT_PATH = 'reports/backtest/三年全周期对比报告.md'

# ── 权重 ──
W_FULL = 0.30
W_A = 0.15
W_B = 0.15
W_C = 0.20
W_WIN = 0.10
W_CALMAR = 0.10


def load_json_results():
    """从 _results_3y/*.json 读取所有批次结果"""
    all_results = []
    for fp in sorted(glob.glob(os.path.join(OUT_DIR, '*.json'))):
        try:
            data = json.load(open(fp, 'r', encoding='utf-8'))
            all_results.extend(data)
            print(f'[加载] {fp}: {len(data)} 个策略')
        except Exception as e:
            print(f'[错误] {fp}: {e}')
    return all_results


def parse_regime_3y(skip_labels=None):
    """从 _test_regime_3y_result.txt 解析策略3,17,17b的3年期结果
    skip_labels: set of already-known labels to skip (去重)
    """
    fp = '_test_regime_3y_result.txt'
    if not os.path.exists(fp):
        return []
    text = open(fp, 'r', encoding='utf-8').read()
    skip_labels = skip_labels or set()

    # TXT label → JSON label 的映射（用于去重）
    label_map = {
        '3Y-策略3 baseline': '策略3_Champion+dynSL',
        '3Y-策略17 regime默认': '策略17_regime默认',
        '3Y-策略17b regime激进': '策略17b_regime激进',
    }

    results = []
    # 按 === 分割各策略
    blocks = re.split(r'=== (.+?) ===', text)
    # blocks = [前置文本, label1, block1, label2, block2, ...]
    for i in range(1, len(blocks) - 1, 2):
        raw_label = blocks[i].strip()
        block = blocks[i + 1]

        # 映射到标准 label
        json_label = label_map.get(raw_label, raw_label)
        # 去重：如果 JSON 中已有该策略（或有同关键词的），跳过
        if json_label in skip_labels:
            print(f'[跳过] {raw_label} (JSON已有)')
            continue
        # 模糊匹配去重：检查 skip_labels 中是否包含相同策略编号
        strategy_num = re.search(r'策略(\d+[a-c]?)', json_label)
        if strategy_num:
            num = strategy_num.group(1)
            if any(f'策略{num}' in sl for sl in skip_labels):
                print(f'[跳过] {raw_label} (JSON已有策略{num})')
                continue

        # 提取 Return, MaxDD, Trades, Sharpe, Calmar
        ret = re.search(r'Return:\s*[+\-]?([\d.]+)%', block)
        dd = re.search(r'MaxDD:\s*([\d.]+)%', block)
        tc = re.search(r'Trades:\s*(\d+)', block)
        sharpe = re.search(r'Sharpe:\s*([\d.]+)', block)
        calmar = re.search(r'Calmar:\s*([\d.]+)', block)
        ann = re.search(r'Annualized:\s*[+\-]?([\d.]+)%', block)

        # 提取最后的汇总行
        summary = re.search(r'收益:\s*([\d.]+)%\s*回撤:\s*([\d.]+)%\s*交易:\s*(\d+)笔', block)

        if ret or summary:
            r = {
                "label": json_label,
                "total_return": float(ret.group(1)) if ret else float(summary.group(1)) if summary else 0,
                "max_drawdown": float(dd.group(1)) if dd else float(summary.group(2)) if summary else 0,
                "trade_count": int(tc.group(1)) if tc else int(summary.group(3)) if summary else 0,
                "sharpe": float(sharpe.group(1)) if sharpe else 0,
                "calmar": float(calmar.group(1)) if calmar else 0,
                "annualized": float(ann.group(1)) if ann else 0,
                "segments": {"A_熊市": None, "B_震荡": None, "C_牛市": None},
                "monthly_win_rate": None,
                "signal_utilization": None,
                "note": "从 _test_regime_3y_result.txt 解析, 无分段数据(待补跑)",
            }
            results.append(r)
            print(f'[解析] {json_label}: {r["total_return"]:.2f}% / {r["max_drawdown"]:.2f}%dd')
    return results


def calc_weighted_score(s):
    """计算加权分"""
    seg = s.get("segments", {})
    full = s.get("total_return", 0)
    a = seg.get("A_熊市") if seg.get("A_熊市") is not None else 0
    b = seg.get("B_震荡") if seg.get("B_震荡") is not None else 0
    c = seg.get("C_牛市") if seg.get("C_牛市") is not None else 0
    win = s.get("monthly_win_rate") if s.get("monthly_win_rate") is not None else 50
    calmar = s.get("calmar", 0)

    score = (full * W_FULL + a * W_A + b * W_B + c * W_C +
             win * W_WIN + calmar * W_CALMAR)
    return round(score, 2)


def check_thresholds(s):
    """检查是否通过阈值门槛, 返回通过/未通过的标记列表"""
    seg = s.get("segments", {})
    checks = []
    full = s.get("total_return", 0)
    dd = s.get("max_drawdown", 999)
    a = seg.get("A_熊市")
    b = seg.get("B_震荡")
    c = seg.get("C_牛市")
    win = s.get("monthly_win_rate")

    checks.append(("全周期≥基线", full >= 0))  # 基线待填
    checks.append(("回撤≤20%", dd <= 20))
    if a is not None:
        checks.append(("段A≥-10%", a >= -10))
    if b is not None:
        checks.append(("段B≥0%", b >= 0))
    if c is not None:
        checks.append(("段C≥30%", c >= 30))
    if win is not None:
        checks.append(("月胜率≥50%", win >= 50))
    return checks


def generate_report(results):
    """生成 Markdown 报告"""
    # 计算加权分
    for s in results:
        s["weighted_score"] = calc_weighted_score(s)

    # 按加权分排名
    ranked = sorted(results, key=lambda x: x.get("weighted_score", 0), reverse=True)

    lines = []
    lines.append("# 三年全周期策略对比报告")
    lines.append("")
    lines.append(f"> 数据期: 2023-07-17 ~ 2026-07-17 (3整年, 983天)")
    lines.append(f"> 覆盖: 段A(熊市) + 段B(震荡复苏) + 段C(牛市加速)")
    lines.append(f"> 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 策略总数: {len(results)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 排名表 ──
    lines.append("## 排名表")
    lines.append("")
    lines.append("| 排名 | 策略 | 全周期 | 段A | 段B | 段C | 回撤 | 月胜率 | 夏普 | 卡玛 | 加权分 |")
    lines.append("|------|------|--------|-----|-----|-----|------|--------|------|------|--------|")
    for rank, s in enumerate(ranked, 1):
        seg = s.get("segments", {})
        full = f"{s.get('total_return', 0):.2f}%"
        a = f"{seg.get('A_熊市', '?')}%" if seg.get('A_熊市') is not None else "—"
        b = f"{seg.get('B_震荡', '?')}%" if seg.get('B_震荡') is not None else "—"
        c = f"{seg.get('C_牛市', '?')}%" if seg.get('C_牛市') is not None else "—"
        dd = f"{s.get('max_drawdown', 0):.2f}%"
        win = f"{s.get('monthly_win_rate', '?')}%" if s.get('monthly_win_rate') is not None else "—"
        sharpe = f"{s.get('sharpe', 0)}"
        calmar = f"{s.get('calmar', 0)}"
        ws = f"{s.get('weighted_score', 0)}"
        lines.append(f"| {rank} | {s['label']} | {full} | {a} | {b} | {c} | {dd} | {win} | {sharpe} | {calmar} | {ws} |")
    lines.append("")

    # ── 各段最优分析 ──
    lines.append("## 各段行为分析")
    lines.append("")

    # 段A最优(亏损最小)
    seg_a = [(s, s.get("segments", {}).get("A_熊市")) for s in results
             if s.get("segments", {}).get("A_熊市") is not None]
    if seg_a:
        best_a = max(seg_a, key=lambda x: x[1])
        worst_a = min(seg_a, key=lambda x: x[1])
        lines.append(f"### 段A (熊市 2023-07 ~ 2024-06)")
        lines.append(f"- **最优**: {best_a[0]['label']} = {best_a[1]}%")
        lines.append(f"- **最差**: {worst_a[0]['label']} = {worst_a[1]}%")
        lines.append(f"- 有分段数据的策略: {len(seg_a)}个")
    else:
        lines.append(f"### 段A (熊市): 分段数据待补跑")
    lines.append("")

    seg_b = [(s, s.get("segments", {}).get("B_震荡")) for s in results
             if s.get("segments", {}).get("B_震荡") is not None]
    if seg_b:
        best_b = max(seg_b, key=lambda x: x[1])
        lines.append(f"### 段B (震荡 2024-07 ~ 2025-06)")
        lines.append(f"- **最优**: {best_b[0]['label']} = {best_b[1]}%")
    else:
        lines.append(f"### 段B (震荡): 分段数据待补跑")
    lines.append("")

    seg_c = [(s, s.get("segments", {}).get("C_牛市")) for s in results
             if s.get("segments", {}).get("C_牛市") is not None]
    if seg_c:
        best_c = max(seg_c, key=lambda x: x[1])
        lines.append(f"### 段C (牛市 2025-07 ~ 2026-07)")
        lines.append(f"- **最优**: {best_c[0]['label']} = {best_c[1]}%")
    else:
        lines.append(f"### 段C (牛市): 分段数据待补跑")
    lines.append("")

    # ── 阈值检查 ──
    lines.append("## 阈值检查")
    lines.append("")
    lines.append("| 策略 | 全周期≥基线 | 回撤≤20% | 段A≥-10% | 段B≥0% | 段C≥30% | 月胜率≥50% |")
    lines.append("|------|------------|----------|----------|--------|---------|-----------|")
    for s in ranked:
        seg = s.get("segments", {})
        checks = check_thresholds(s)
        marks = []
        for name, passed in checks:
            marks.append("✅" if passed else "❌")
        # 补齐6列
        while len(marks) < 6:
            marks.append("—")
        lines.append(f"| {s['label']} | {' | '.join(marks[:6])} |")
    lines.append("")

    # ── 最终推荐 ──
    lines.append("## 最终推荐")
    lines.append("")
    if ranked:
        top = ranked[0]
        lines.append(f"### 第一选择: {top['label']}")
        lines.append(f"- 全周期: {top.get('total_return', 0):.2f}%")
        lines.append(f"- 回撤: {top.get('max_drawdown', 0):.2f}%")
        lines.append(f"- 夏普: {top.get('sharpe', 0)}  卡玛: {top.get('calmar', 0)}")
        seg = top.get("segments", {})
        if seg.get("A_熊市") is not None:
            lines.append(f"- 段A: {seg['A_熊市']}%  段B: {seg['B_震荡']}%  段C: {seg['C_牛市']}%")
        lines.append(f"- 加权分: {top.get('weighted_score', 0)}")
        lines.append("")

        if len(ranked) > 1:
            second = ranked[1]
            lines.append(f"### 第二选择(备用): {second['label']}")
            lines.append(f"- 全周期: {second.get('total_return', 0):.2f}%  回撤: {second.get('max_drawdown', 0):.2f}%")
            lines.append("")

        # 不推荐
        bad = [s for s in ranked if s.get('max_drawdown', 0) > 20 or
               (s.get('segments', {}).get('A_熊市') is not None and s['segments']['A_熊市'] < -10)]
        if bad:
            lines.append("### 不推荐")
            for s in bad:
                reason = []
                if s.get('max_drawdown', 0) > 20:
                    reason.append(f"回撤{s['max_drawdown']:.1f}%>20%")
                if s.get('segments', {}).get('A_熊市') is not None and s['segments']['A_熊市'] < -10:
                    reason.append(f"段A={s['segments']['A_熊市']}%<-10%")
                lines.append(f"- {s['label']}: {', '.join(reason)}")
            lines.append("")

    # ── 备注 ──
    lines.append("---")
    lines.append("")
    lines.append("### 备注")
    lines.append("- 加权分 = 全周期×0.3 + 段A×0.15 + 段B×0.15 + 段C×0.2 + 月胜率×0.1 + 卡玛×0.1")
    lines.append("- 标注'—'的字段表示该策略未跑分段数据(待补跑)")
    lines.append("- 段A: 2023-07-17~2024-06-30(熊市)  段B: 2024-07-01~2025-06-30(震荡)  段C: 2025-07-01~2026-07-17(牛市)")
    lines.append("- 本报告为学习研究, 非投资建议")

    return '\n'.join(lines)


def main():
    print('=== 三年全周期对比报告生成器 ===')

    # 1. 读取 JSON 结果
    results = load_json_results()
    print(f'从JSON加载: {len(results)} 个策略')

    # 2. 解析 regime 3年期结果(策略17,17b)，跳过JSON中已有的
    json_labels = {r['label'] for r in results}
    regime_results = parse_regime_3y(skip_labels=json_labels)
    results.extend(regime_results)
    print(f'总计: {len(results)} 个策略')

    if not results:
        print('无结果数据, 请先运行回测')
        return

    # 3. 生成报告
    report = generate_report(results)

    # 4. 保存
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'\n[已保存] {REPORT_PATH}')

    # 5. 打印排名表
    print('\n=== 排名表 ===')
    for s in sorted(results, key=lambda x: x.get('weighted_score', 0), reverse=True):
        seg = s.get("segments", {})
        a = seg.get("A_熊市", "—")
        b = seg.get("B_震荡", "—")
        c = seg.get("C_牛市", "—")
        print(f"  {s['label']:<35} 全{s.get('total_return',0):>7.2f}% "
              f"A={a} B={b} C={c} 回撤{s.get('max_drawdown',0):.1f}% "
              f"加权{s.get('weighted_score',0)}")


if __name__ == '__main__':
    main()
