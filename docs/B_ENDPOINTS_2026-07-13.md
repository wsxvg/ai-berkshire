# 新 API 端点修复结论 (2026-07-13)

## 排查结果

3 个新端点 5 种参数组合全部返回 `resultData.status: FAIL`:

| 端点 | 测试结果 |
|------|---------|
| `gw2/generic/jj/newh5/m/getInvestResearchRank` | FAIL (5 种参数) |
| `gw2/generic/opdataapi/newh5/m/getFundLabel` | code=0000 空响应 |
| `gw2/generic/wealthBase/newh5/m/getIndexValuationTrendChart` | FAIL (5 种参数) |

**已穷尽**:
- 29 条完整 cookies ✅
- 5 种 referer (jdjr.jd.com / ms.jr.jd.com / m.jd.com / 等) ✅
- 5 种参数 (uniqueCodes 不同格式 / deviceType / rankType / period / 全字段) ✅

**根因**: 端点风控/下线, 业务层返 `status: FAIL`, 不是代码问题。

## 建议

- **放弃新 API** — 抓包 1.txt 是 2026-07-12 之前的快照, 端点可能 A/B 测试结束
- **专注现有 5 维评分 + 跟单信号** — 数据充足, 已验证有效
- **未来如果端点复活** — 代码自动可用 (零改动)
