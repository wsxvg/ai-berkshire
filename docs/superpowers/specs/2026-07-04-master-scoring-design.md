# 四大师评分修正层 — 实施规划

## 现状

策略 D 的评分系统是 5 维加权：

```
总分 = 质量×0.25 + 成本×0.20 + 经理×0.20 + 动量×0.15 + 聪明钱×0.20
```

缺少：**多维视角交叉验证**。一只基金 5 维分数高，不一定代表它真的适合你。

## 方案：四大师修正层

在现有 5 维评分基础上，叠加 4 个大师视角的修正分，最终得分 = 5维基础分 + 大师修正。

```
最终分 = 5维基础分 + 段永平修正 + 巴菲特修正 + 芒格修正 + 李录修正

约束：每个大师修正范围 [-0.5, +0.5]
      总修正范围 [-1.5, +1.5]（极端情况下不会超过2分）
```

## 每个大师的修正逻辑

### 1. 段永平修正 — 商业模式质量

核心问题：这只基金底层买了什么生意？

```python
# 从持仓穿透数据获取
def duanyongping_modifier(code, holdings_data):
    stocks = holdings_data.get("top_stocks", [])
    sectors = [detect_stock_sector(s) for s in stocks]
    
    # 好生意加分：消费、科技、医药
    good_biz = ["消费", "科技", "医药", "互联网"]
    good_ratio = sum(1 for s in sectors if s in good_biz) / max(len(sectors), 1)
    
    # 差生意扣分：周期、地产、大宗商品
    bad_biz = ["地产", "煤炭", "钢铁", "化工", "传统制造"]
    bad_ratio = sum(1 for s in sectors if s in bad_biz) / max(len(sectors), 1)
    
    modifier = good_ratio * 0.5 - bad_ratio * 0.5
    return max(-0.5, min(0.5, modifier))
```

| 条件 | 修正 |
|------|------|
| 前10持仓中 60%+ 是消费/科技/医药 | +0.3 ~ +0.5 |
| 前10持仓中 40%+ 是周期/地产/大宗 | -0.3 ~ -0.5 |
| 混合型，无明显倾向 | 0 |
| 无明显持仓数据 | 0（不惩罚） |

### 2. 巴菲特修正 — 费率与价值

核心问题：这基金管理费贵不贵？值得买吗？

```python
def buffett_modifier(code, rules):
    manage_fee = float(rules.get("manage_fee", 1.2))
    purchase_fee = float(rules.get("purchase_fee", 0.15))
    
    modifier = 0
    if manage_fee < 0.5: modifier += 0.3    # 指数级低费率
    elif manage_fee < 0.8: modifier += 0.1  # 较低
    elif manage_fee > 1.5: modifier -= 0.3  # 太贵了
    
    if purchase_fee == 0: modifier += 0.2   # C类免申购费
    if purchase_fee > 1.0: modifier -= 0.2  # 申购费太贵
    
    return max(-0.5, min(0.5, modifier))
```

| 条件 | 修正 |
|------|------|
| 管理费 < 0.5%（指数基金） | +0.3 |
| 管理费 < 0.8% | +0.1 |
| 管理费 > 1.5% | -0.3 |
| C 类（0申购费） | +0.2 |
| A 类原始申购费 > 1% | -0.2 |

### 3. 芒格修正 — 赛道拥挤度

核心问题：这基金是不是大家都买了？太拥挤的地方没有超额收益。

```python
def munger_modifier(code, fund_name, holders_count):
    sector, _ = detect_sector(fund_name, code)
    
    # 拥挤赛道扣分
    crowded = {"半导体", "AI", "新能源", "白酒"}
    if sector in crowded and holders_count > 5:
        modifier = -0.3  # 热门赛道 + 多人持有 = 拥挤
    elif sector in crowded and holders_count <= 3:
        modifier = -0.1  # 热门但还不太拥挤
    elif sector not in crowded and holders_count > 5:
        modifier = +0.2  # 非热门但多人看好 = 有道理
    else:
        modifier = 0
    
    return max(-0.5, min(0.5, modifier))
```

| 条件 | 修正 |
|------|------|
| 热门赛道（半导体/AI）+ ≥5人持有 | -0.3（太拥挤） |
| 热门赛道 + ≤3人持有 | -0.1 |
| 冷门赛道 + ≥5人持有 | +0.2（非共识正确） |
| 冷门赛道 + 少人持有 | +0.1 |

### 4. 李录修正 — 经理稳定性

核心问题：基金经理靠谱吗？经验够吗？

```python
def lilu_modifier(code, manager_data):
    managers = manager_data.get("managers", [])
    if not managers:
        return 0  # 无数据不惩罚
    
    # 取任职年限最长的经理
    longest_tenure = max([m.get("tenure_years", 0) for m in managers])
    
    if longest_tenure >= 8: modifier = +0.3   # 资深经理
    elif longest_tenure >= 5: modifier = +0.1  # 较稳定
    elif longest_tenure >= 3: modifier = 0     # 一般
    elif longest_tenure >= 1: modifier = -0.2  # 经验不足
    else: modifier = -0.5                       # 新上任
    
    return max(-0.5, min(0.5, modifier))
```

| 条件 | 修正 |
|------|------|
| 任职 ≥8年 | +0.3 |
| 任职 ≥5年 | +0.1 |
| 任职 ≥3年 | 0 |
| 任职 ≥1年 | -0.2 |
| 任职 <1年或无数据 | -0.3 |

## 实施步骤

### Step 1：在 fund_scorer.py 中加 4 个修正函数

```python
# 新增函数（约 80 行代码）
def duanyongping_modifier(code, holdings_data): ...
def buffett_modifier(code, fund_rules): ...
def munger_modifier(code, fund_name, holders_count, sector_map): ...
def lilu_modifier(code, manager_data): ...

def compute_master_modifiers(code, fund_name, fund_rules, manager_data, holdings_data, holders_count):
    """计算四大师总修正"""
    dyp = duanyongping_modifier(code, holdings_data)
    bt = buffett_modifier(code, fund_rules)
    mg = munger_modifier(code, fund_name, holders_count)
    ll = lilu_modifier(code, manager_data)
    
    total = dyp + bt + mg + ll
    return max(-1.5, min(1.5, total)), {"dyp": dyp, "buffett": bt, "munger": mg, "lilu": ll}
```

### Step 2：在 backtest.py 的 score_fund_backtest() 中调用

在 `score_fund_backtest()` 计算完 5 维基础分后，加入：

```python
# 计算四大师修正
master_mod, master_detail = compute_master_modifiers(
    fund_code, fund_name, rules, mgr,
    allocation_data,  # 持仓穿透
    len(buy_users)    # 持有者数
)
fs.total = max(0.5, min(5.0, fs.total + master_mod))
```

### Step 3：在 auto-pipeline.py 的信号输出中加大师分析

在每日信号报告中增加四大师评价：

```
## 四大师视角
段永平：持仓消费占比60% → ✅ 好生意 +0.3
巴菲特：管理费1.2% → ⚠️ 偏贵 -0.1
芒格：半导体赛道+6人持有 → ⚠️ 拥挤 -0.3
李录：经理任职7年 → ✅ 稳定 +0.1
总修正：0.0
```

### Step 4：回测验证

用策略 D 的完整回测框架跑一遍，比较：

| 版本 | 收益 | 回撤 | 选基差异 |
|------|------|------|---------|
| 无大师修正（当前） | +35.99% | 3.9% | — |
| 有大师修正 | 待测 | 待测 | 待测 |

## 预计工作量

| 任务 | 代码量 | 难度 | 时间 |
|------|-------|------|------|
| 4个修正函数 | 80行 | 低 | 30min |
| backtest.py 集成 | 10行 | 低 | 10min |
| 持仓数据接口集成 | 20行 | 低 | 15min |
| pipeline报告集成 | 30行 | 低 | 15min |
| 回测验证 | — | 中 | 30min |
| **总计** | **~140行** | **低** | **~1.5h** |

## 是否改变决策逻辑

**不改。** 大师修正只是 5 维评分的补充微调（±1.5分以内），不改变现有的：
- 选基逻辑（仍然由评分驱动）
- 仓位管理（半凯利+硬上限）
- 卖出逻辑（止损/回撤止盈/动量）
- 定投和季度检视

修正分的作用：同样是 4.0 分的基金，一个持仓消费+费率高+经理稳定 vs 一个持仓周期+费率低+经理不稳 → 大师修正会让它们的最终分差达到 1-2 分，从而影响选基优先级。

## 要不要开始实施？