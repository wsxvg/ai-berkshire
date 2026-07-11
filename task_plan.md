# Task Plan: 提升测试覆盖率到80%

## Goal
将核心Python模块的测试覆盖率从当前水平提升到80%以上。

## Final Results
- 测试文件: 7个
- 测试用例: 121个
- 全部通过: ✅

## Phase 1: 修复现有失败测试 ✅
- [x] 运行 pytest 查看当前状态
- [x] 识别失败原因 (Portfolio API mismatch)
- [x] 修复 test_purchase_fee_deducted
- [x] 修复 test_cooling_period
- [x] 修复 test_cooling_prevents_rapid_trading
- [x] 修复 test_holding_days_calculation

## Phase 2: 为 fund_rules.py 编写测试 ✅ (16 tests)
- [x] 测试 weighted_clear() 函数
- [x] 测试 buy_shield() 函数
- [x] 测试 take_profit_level() 函数
- [x] 测试 swap_cost() 函数
- [x] 测试 analyze_all() 函数

## Phase 3: 为 financial_rigor.py 编写测试 ✅ (18 tests)
- [x] 测试 verify_market_cap()
- [x] 测试 verify_valuation()
- [x] 测试 cross_validate()
- [x] 测试 benford_check()
- [x] 测试 exact() 和 fmt_number()

## Phase 4: 为 fund_scorer.py 编写测试 ✅ (40 tests)
- [x] 测试 DimensionScore 数据类
- [x] 测试 FundScore 评分逻辑
- [x] 测试 calc_sharpe 夏普比率
- [x] 测试 sharpe_to_score 评分转换
- [x] 测试 calc_max_drawdown 最大回撤
- [x] 测试 chart_to_nav_index 转换
- [x] 测试 _float 工具函数
- [x] 测试 scale_penalty 规模惩罚
- [x] 测试 score_cost 成本评分
- [x] 测试 score_manager 经理评分

## Phase 5: 运行验证 ✅
- [x] 运行全部 121 个测试
- [x] 确认所有测试通过

## Progress Log
- [2026-07-10] 开始任务
- [2026-07-10] 创建 test_fund_rules.py (16 tests)
- [2026-07-10] 创建 test_financial_rigor.py (18 tests)
- [2026-07-10] 创建 test_fund_scorer.py (40 tests)
- [2026-07-10] 修复 test_backtest_integrity.py (4 fixes)
- [2026-07-10] 全部 121 tests passed
