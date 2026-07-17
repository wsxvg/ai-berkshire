# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.



## 常用命令



```bash

# 一键监控（每日运行，输出持仓择时分析）

py -3.10 run.py



# 每日自动管道（抓取JD数据+评分+生成报告）

py -3.10 scripts/auto-pipeline.py

py -3.10 scripts/auto-pipeline.py --offline  # 仅用缓存



# 回测验证

py -3.10 scripts/validate_backtest.py --quick



# 单次回测（自定义参数）

py -3.10 -c "from backtest.engine.backtest import run_backtest; run_backtest({...})"



# 安装ML依赖

py -3.10 -m pip install lightgbm scikit-learn numpy chinese_calendar

```



Python 必须用 3.10（`py -3.10`），不要用系统默认的 3.14。



## 核心架构



### 数据流



```

京东金融API → holdings_snapshot.json (大佬持仓)

           → trading_records_*.json (大佬交易流水)

           → fund_charts.json (273只基金累计收益率曲线)



auto-pipeline.py → 聚合交易信号 → 五维评分 → 生成MD/HTML报告



backtest/engine/backtest.py → 回测引擎 → 评分+择时+止盈止损 → 验证策略

```



### 关键数据文件



| 文件 | 说明 | 位置 |

|------|------|------|

| `holdings_snapshot_YYYY-MM-DD.json` | **大佬持仓快照**（非用户自己的持仓） | `data/` |

| `trading_history_fixed.json` | 所有大佬交易记录（8856条，2024-03~2026-07） | `backtest/data/` |

| `trading_by_date_fixed.json` | 按日聚合的交易记录（448个交易日） | `backtest/data/` |

| `fund_charts.json` | 273只基金累计收益率曲线，yAxis=自成立来累计收益率% | `backtest/data/` |

| `fund_name_map.json` | 基金名→代码映射（433条，81.2%覆盖） | `data/` |

| `data/fund_cache/` | 基金详情缓存（profile/rules/manager/holdings） | `data/` |



**关键区分**：`holdings_snapshot` 存的是京东金融上大佬的持仓，**不是用户自己的持仓**。用户的实盘通过 `get_user_holdings(None)` 实时获取。



**⚠️ 反复踩坑的数据陷阱**：

1. `fund_charts.json` 的 `yAxis` = 基金自成立来的累计收益率%，**不能用来算用户盈亏**

2. API的 `amount` = **当前市值**（亏了数字就变小），不是投入成本。投入 = `amount / (1 + profit_rate_pct/100)`

3. API的 `profit_rate` / `profit` = 用户的真实盈亏，**直接用，不要自己算**



### 五维评分系统 (`tools/fund_scorer.py`)



| 维度 | 权重 | 数据来源 | 函数 |

|------|------|---------|------|

| Quality | 25% | chart/perf | `score_quality` — 1年排名、3年排名、回撤、夏普、估值 |

| Cost | 20% | trade_rules | `score_cost` — 管理费+托管费+申购费 |

| Manager | 20% | fund_manager | `score_manager` — 任职年限、历史业绩 |

| Momentum | 15% | chart | `score_momentum` — 20日均线、60日斜率、回撤恢复 |

| Smart Money | 20% | trading_history | `score_smart_money` — 大佬买入数、频率、一致性 |



回测版在 `backtest/engine/backtest.py` 中有对应的 `_backtest` 后缀函数，使用日期截断防止未来函数。



### 技术择时模块 (`tools/technical_indicators.py`)



融合 QuantDinger 开源项目的算法，**这是防止高位接盘的核心模块**：



- `compute_rsi(nav_values, period=14)` — RSI指标，>70超买，<30超卖

- `compute_overbought_score(nav_values)` — 综合超买评分（RSI+布林带+涨幅），返回负数扣分值

- `compute_mean_reversion_score(nav_values)` — 均值回归评分，RSI 30-50且趋势向上时给奖励

- `compute_entry_timing_score(chart_points, cutoff_date)` — 综合择时评分，返回dict含rsi/overbought_penalty/mean_reversion_bonus/trend/entry_score/should_warn



在回测引擎中通过 `timing_filter: True` 启用，RSI>75扣1.0分，RSI>80扣1.5分。



### 回测引擎 (`backtest/engine/backtest.py`)



入口：`run_backtest(config)` (约第900行)



**数据加载**(第904-960行)：

1. `trading_by_date_fixed.json` → 按日聚合交易

2. `trading_history_fixed.json` → 全部交易记录

3. `fund_charts.json` → 基金净值曲线

4. `fund_cache/*.json` → 费率/经理/持仓缓存

5. `fund_name_map.json` → 名称映射 + 三步模糊匹配



**每日循环**(第1060行起)：

1. `detect_market_state()` — 用沪深300(110020)判断牛/熊/中性

2. 动态评分门槛 — 牛市min_score=2.5，熊市=3.5

3. 熊市过滤 — `bear_market_no_buy=True`时跳过所有买入

4. 候选评分 — 五维评分 + 技术择时 + ML信号

5. 相关性过滤 — 与已持仓基金相关系数>0.85则排除

6. 卖出逻辑 — 止损/止盈/移动止盈/动量崩溃/仓位过重

7. 冷却期 — 止盈卖10天后可重新买入，止损卖30天



**Portfolio类**：管理持仓、T+N确认、申购费/赎回费、滑点模拟。



### ML信号增强 (`tools/ml_signal.py`)



LightGBM分类器，16维特征（五维评分+近期收益+回撤+波动率+规模+费率+共识+市场状态+基金年龄），标签为30日前瞻收益>3%。Walk-forward训练，每30天重训，`pretrain`方法严格检查前瞻数据不超过截止日（防前视偏差）。



### auto-pipeline.py



105KB，有重复的`_generate_report`函数（已知问题）。流程：

1. 加载cookies → 调JD API抓取大佬持仓和交易记录

2. `_aggregate_trading_signals` — 聚合买卖信号（买入=+1，卖出=-1）

3. 五维评分 → 生成MD报告（`reports/auto/daily-YYYY-MM-DD.md`）

4. 生成HTML报告（`reports/auto/scan-YYYY-MM-DD.html`）



**已知缺陷（初始版ai-berkshire-main的问题，本项目已修复）**：

- 初始版仅凭2人买入就生成"买入信号"，不检查RSI/超买/估值

- 导致用户在高位跟买华夏全球科技先锋(024239)，亏损-15.87%

- 本项目增加了 `timing_filter` 和 `block_overbought` 参数解决此问题



### JD金融API 全量清单



> 通过Playwright浏览器登录+自动化遍历17个页面，共捕获 **82个去重API端点**，覆盖 **28个命名空间**，分布在 **2个网关域名**。  

> **gw2**: `https://ms.jr.jd.com/gw2/generic` (57个端点)  

> **gw**: `https://ms.jr.jd.com/gw/generic` (25个端点)



---



#### 🔴 用户持仓类（最核心，直接返回你的/大佬的盈亏）



| 路径 | 方法 | 用途 | 关键返回字段 |

|------|------|------|------------|

| `CreatorSer/h5/m/queryUserFundHoldingInfo` | POST | **你的持仓**(searchType=3) / 大佬持仓(searchType=2+targetUid) | `holdings[]`: `name, code, amount(当前市值), profit_rate(盈亏%), profit(盈亏金额)` |

| `CreatorSer/h5/m/queryUserFundHoldingInfo` | POST | 大佬持仓+周期收益 | `holdings{}` + `period_returns{近1周,近1月,近1年}` |

| `CreatorSer/h5/m/pcQueryUserInfo` | POST | 当前登录用户信息 | `nickName, uid` |

| `CaiFuPC/h5/m/queryFundRelationList` | POST | 基金关系列表 | 用户相关的基金 |



**⚠️ `amount`=当前市值不是投入。投入=`amount/(1+profit_rate_pct/100)`**



---



#### 🟢 自选/分组类（已登录才能用）



| 路径 | 返回 |

|------|------|

| `jdtwt/h5/m/queryZxProductList` | **你的自选基金列表**。每只返回: `fundNo, fundName, newValue(最新净值), dayRiseRate, weekRiseRate, monthRiseRate, yearRiseRate, allIncome(持仓盈亏%), fundType, fundId, url`。还返回分组列表(groupList) |

| `koi/h5/m/executeEncrypted?command=STOCK_GROUP_INFO` | 股票分组配置(沪深/板块/港股/黄金/美股等) |

| `koi/h5/m/lcExecuteEncrypted?tags=RequestGroupAndList` | 理财分组和列表 |

| `koi/h5/m/lcExecuteEncrypted?stag=lineChartRequest` | 折线图数据 |



---



#### 🟡 基金详情类（最全的数据源）



| 路径前缀 | 端点 | 返回 |

|---------|------|------|

| `life/h5/m/` | `getFundDetailPageInfoWithPin` | **登录版基金详情(数据最全)**。包含: headerOfItem(净值/评级/排名/标签), performanceOfItem(净值历史/年度业绩/同业排名), investmentDistributionNewOfItem(资产配置/前10重仓/行业分布), fundManagerOfItem(基金经理/任职/业绩/规模), fundProfileOfItem(成立日期/规模/公司), fundDiagnosisOfItem(诊断:收益/回撤/波动率/夏普), purchaseProcessOfItem(购买流程), bottomButtonOfItem(买入按钮/费率), noticeOfItem(公告) |

| `life/h5/m/` | `getFundDetailPageInfoWithNoPin` | 未登录版基金详情(数据略少) |

| `jj/newh5/m/` | `getFundDetailPageInfo` | 基金详情(旧版封装) |

| `jj/newh5/m/` | `getFundDetailChartPageInfo` | 净值曲线图数据 |

| `jj/newh5/m/` | `getFundProfile` | 基金概况 |

| `jj/newh5/m/` | `getFundHistoryPerformance` | 历史业绩+同业排名 |

| `jj/newh5/m/` | `getFundTradeRules` | 费率/T+N确认日/申购限额 |

| `jj/newh5/m/` | `getFundHoldingsDistribution` | 持仓分布+前10重仓股 |

| `jj/newh5/m/` | `getFundManagerDetailPageInfo` | 基金经理(任职日期/历史业绩) |

| `jj/newh5/m/` | `getFundFeeAndDiscountDataList` | 管理费/托管费/申购费/赎回费/折扣 |

| `jj/newh5/m/` | `getFundNotices` | 基金公告(分红/限购/清盘) |

| `jj/newh5/m/` | `getFundLabel` | 基金标签(如"半导体主题") |

| `jj/newh5/m/` | `getFundData` | 汇总: profile+perf+holdings+manager+rules |

| `jj/newh5/m/` | `batchGetFundData` | 批量多只基金数据 |

| `jmServer/h5/m/` | `getFundChart` | 基金图表(净值/收益曲线) |



**`getFundDetailPageInfoWithPin` 是数据最全的单一端点**，一次返回: 净值历史、历史业绩+排名、持仓分布+前10重仓、基金经理、诊断(收益/回撤/波动率/夏普)、购买费率、FAQ、公告。



---



#### 🔵 排行/热搜/投研类



| 路径 | 用途 | 关键返回 |

|------|------|---------|

| `jj/h5/m/getRankingProductListV2` | **基金排行(19905只全市场)**。支持按基金类型/时间周期/指标筛选排序 | `totalCount:19905`, `productList[]`: `productCode, productName, slideShowList[近1年涨跌幅, 最大回撤, 夏普比率, 最新净值]`。筛选维度: 股票型/混合型/债券型/指数型/QDII/FOF/货币型。排序: 近1周/1月/3月/6月/1年/3年/5年/今年以来/成立以来。精选标签: 月月正收益/长期高盈率/低回撤/高夏普/低波动 |

| `jj/h5/m/getRankingHeaderInfoV2` | 排行页导航 | 排行类型(业绩/定投/净值), 搜索入口 |

| `jj/newh5/m/getInvestResearchRank` | 投研排行(首页多个榜单的数据源) | 季季正收益榜、连续跑赢大盘榜、持仓盈利多榜、今日热搜榜等 |

| `opdataapi/newh5/m/getWealthDatas` | 财富数据面板 | 各类排行聚合数据 |

| `opdataapi/newh5/m/getFundLabel` | 基金标签 | 每只基金的标签(如"半导体主题""高夏普""低回撤") |

| `opdataapi/newh5/m/getConfigs` | 页面配置 | 榜单/排行页的配置数据 |



---



#### 🟣 指数/行情/市场类



| 路径 | 用途 |

|------|------|

| `opdataapi/h5/m/getSimpleQuoteUseUniqueCodes` | 指数实时行情(上证/深证/创业板/恒生/纳斯达克/中证500/沪深300/科创50/上证50) |

| `opdataapi/h5/m/getTimeSharingDots` | 分时图数据点 |

| `CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache` | 扩展行情(含今开/昨收/最高/最低/成交额等) |

| `CaiFuPC/h5/m/queryAllStockHistory` | 股票历史数据 |

| `opdataapi/h5/m/getIndexValuationTrendChart` | 指数PE/PB百分位(当前/历史) |

| `opdataapi/h5/m/getBuyIndexRelatedFund` | 跟踪该指数的基金列表(场内+场外) |

| `aladdin/h5/m/buildVisualizeData` | 可视化图表数据 |

| `wealthBase/newh5/m/getIndexDetail` | 行业指数详情。返回: 关联ETF(涨跌幅/成交额/30日涨跌)、关联场外基金(近1年收益/超额收益/3年/5年收益)、行业描述、trackTypeName | 

| `wealthBase/newh5/m/getIndexBlockInfo` | **行业投资信号+10年估值百分位**。三维共振模型(趋势10%+景气30%+估值60%)→0-100综合评分; PE/PB百分位日级历史(2016至今); 投资信号分级(0-50观望/51-75中性/76-100有机会); 估值判断(高估/中性/低估)。**用于行业级择时** |



---



#### ⚪ 社区/实盘/圈子类



| 路径 | 用途 |

|------|------|

| `CreatorSer/h5/m/querySubFundCircleHeadInfoList?circleId=2689640` | 基金圈头部信息 |

| `CreatorSer/newh5/m/getCircleHonorPopupByPin?circleId=2689640` | 圈子荣誉弹窗 |

| `aladdin/h5/m/getPageMutilData?pageId=11567` | **大佬实盘交易feed**(登录版)。每笔返回: 基金名、金额、方向、时间、状态 |

| `aladdin/h5/m/getPageMutilDataNotLogin?pageId=11567` | 同上，但不需要登录 |

| `liveViewer/h5/m/getLiveListForCircle` | 圈子直播列表 |



**getPageMutilData 关键字段(抓包实测)**:

- `allAmount` — 交易金额/份额

- `tradeType` — 1=买入, 2=卖出

- `tradeTime` — 交易时间戳(ms)

- `statusCode` — COMPLETE/PAY_SUCC/REDEEM

- `productId` → 京东内部编码(`1024975`→`024975`)

- `jumpUrl` → 含公募基金代码



---



#### ⚫ 账户/财富/辅助类



| 路径 | 用途 |

|------|------|

| `CaiFuPC/h5/m/queryGoldTab` | 黄金/积存金相关 |

| `CaiFuPC/h5/m/addTradeCookie` | 交易cookie同步 |

| `CaiFuPC/h5/m/addJdCookie` | JD cookie同步 |

| `CaiFuPC/h5/m/getNotifyByPin` | 用户通知 |

| `CaiFuPC/h5/m/queryMissionStatus` | 任务状态 |

| `CaiFuPC/h5/m/queryPcTab` | PC标签查询 |

| `CfCoupon/h5/m/skuActivityQuery` | 费率优惠/活动查询 |

| `legogw/h5/m/getPageInfoForH5` | 页面配置(导航/布局) |

| `legogw/h5/m/getPopTemplateDataForH5` | 弹窗模板数据 |

| `ImServer/h5/m/getSMPublicKeyByAlias` | 即时通讯密钥 |

| `ImServer/h5/m/getPCToken` | 即时通讯token |

| `getRSAPublicKey` | RSA公钥 |

| `bge/h5/m/res-ms` | 埋点/行为统计 |

| `inteActive/newh5/m/listAttitudeComments` | 态度评论列表 |

| `mkt/newh5/m/collectGeeseIfPrized` | 营销活动 |

| `redEnv001/h5/m/packetInfo` | 红包信息 |



#### 🟤 黄金/贵金属类



| 路径 | 用途 |

|------|------|

| `produTools/h5/m/getGoldPrice` | 实时金价 |

| `hj/h5/m/cfGetLatestPriceInfo` | 最新金价信息 |

| `hj/h5/m/indexDataCib` | 黄金指数数据 |

| `hj/h5/m/getCibFictitiousHoldingStat` | 黄金持仓统计 |

| `hj/h5/m/bankTagListSort` | 银行标签排序 |

| `hj/h5/m/cfQueryConditionWaittingNum` | 黄金条件等待数 |

| `quotegate/h5/m/getGoldQuoteAndSpreads` | 黄金报价+价差 |

| `quotegate/h5/m/getHistoryETFSpreads` | ETF历史价差 |

| `quotegate/h5/m/getHistoryGoldCentralBankReserve` | 央行黄金储备历史 |

| `quotegate/newh5/m/getGoldCountryList` | 黄金国家列表 |

| `6440/h5/m/queryStallForGold` | 黄金摊位查询 |

| `CreatorSer/h5/m/pcQueryGoldQuote` | PC端黄金报价 |

| `redEnv001/newh5/m/queryGoldRegularRankFooter` | 黄金定投排行底部 |

| `redEnv001/newh5/m/queryGoldRegularRankInfo` | 黄金定投排行信息 |



#### 🔶 gw网关专属（社区/投研/搜索）



| 路径 | 用途 |

|------|------|

| `jimu/h5/m/feedFlowOfCircle` | 圈子动态流 |

| `jimu/h5/m/homeFeedFlow` | 首页动态流 |

| `jimu/h5/m/getFollowUpdateCount` | 关注更新数 |

| `jimu/h5/m/listQuotation` | 行情列表 |

| `jimu/h5/m/queryCircleHeadInfo` | 圈子头部信息 |

| `jrm/h5/m/getUnderrateIndexChart` | **低估指数图表**(估值洼地发现) |

| `jrm/h5/m/queryStallNew` | 新品查询 |

| `jj/h5/m/getFundDiagnosisPageInfo` | **基金诊断页数据**(gw版) |

| `jj/h5/m/getFundCompareZxProductPageInfo` | **基金对比页数据** |

| `jj/h5/m/getFundHotCompareListPageInfo` | 热门基金对比列表 |

| `aladdin/h5/m/getPageMultiDataForH5` | H5多数据聚合 |

| `base/h5/m/getSearchResultCompletionWord` | **搜索补全**(输入联想) |

| `app/h5/m/getBasicParamForJR` | 基本参数 |

| `bt/h5/m/currMaterielFloor` | 当前物料楼层 |



#### 🆕 本轮新发现（共82端点）



| 命名空间 | 端点 | 对系统价值 |

|---------|------|-----------|

| `CreatorSer/` | `queryProductBigTradeInfoList` | 大佬在某产品的大额交易明细 |

| `CreatorSer/` | `queryShortlistedFundRankList` | 入围/精选基金排行 |

| `CreatorSer/` | `queryMarketInformation` | 市场资讯 |

| `CreatorSer/` | `queryActivityFloatWindow` | 活动弹窗 |

| `touchFish/` | `getPlateRank` | 板块排行（新版） |

| `ope/` | `pageInfo` | 运营页面信息 |

| `opdataapi/` | `getData` | 通用数据获取 |



---



### 🎯 对我们系统有用的API精选（按使用频率排序）



#### 每日监控必需（run.py 每天调用）



| 优先级 | API端点 | 函数 | 用途 |

|--------|---------|------|------|

| P0 | `CreatorSer/queryUserFundHoldingInfo` searchType=3 | `get_user_holdings(None)` | 你的实盘：name, code, 市值, 盈亏%, 盈亏金额 |

| P0 | `CreatorSer/queryUserFundHoldingInfo` searchType=2 | `get_user_holdings(uid)` | 大佬持仓：同样字段 |

| P0 | `jdtwt/queryZxProductList` | **未封装** | 自选列表：净值、日/周/月涨幅、添加后盈亏% |

| P1 | `life/getFundDetailPageInfoWithPin` | **未封装** | 基金全量数据(净值/排名/持仓/诊断/经理)—最强端点 |

| P1 | `aladdin/getPageMutilData?pageId=11567` | **未封装** | 大佬实时交易feed—替代`get_trading_records` |



#### 评分引擎用（五维评分各维度）



| 维度 | API端点 | 提取数据 |

|------|---------|---------|

| Quality | `getFundDetailPageInfoWithPin.performanceOfItem` | 近1/3/6/12月收益+同类排名+年度业绩 |

| Quality | `getFundDetailPageInfoWithPin.fundDiagnosisOfItem` | 收益能力/投资性价比/抗跌能力/抗波动(含夏普/回撤) |

| Cost | `getFundTradeRules` / `getFundFeeAndDiscountDataList` | 管理费/托管费/申购费/赎回费/折扣 |

| Manager | `getFundDetailPageInfoWithPin.fundManagerOfItem` | 任职年限/任期回报/管理规模 |

| Momentum | `getFundDetailChartPageInfo` / `getFundChart` | 净值曲线(用于计算RSI/MACD/均线) |

| Smart Money | `getPageMutilData` / `queryUserFundHoldingInfo(uid)` | 大佬买卖信号/共识度 |



#### 择时风控用



| API | 数据 |

|-----|------|

| `getSimpleQuoteUseUniqueCodes` (SH-000300等) | 沪深300实时点位—市场牛熊判断 |

| `getIndexValuationTrendChart` (H30184.CSI等) | PE/PB百分位—估值过热预警 |

| `api.jdjygold.com/getGoldPrice` | 国际金价—黄金相关基金择时 |

| `getFundNotices` | 限购/分红/清盘公告—防止踩坑 |



#### 待封装的新端点（Python wrapper未覆盖）



| 端点 | 建议封装函数名 | 数据价值 |

|------|--------------|---------|

| `life/h5/m/getFundDetailPageInfoWithPin` | `get_fund_detail_pin(code)` | **最重要**—替代现有`get_fund_detail`，数据更全更新 |

| `jdtwt/h5/m/queryZxProductList` | `get_watchlist()` | 自选列表—含"添加后涨跌"=用户实盘盈亏 |

| `aladdin/h5/m/getPageMutilData?pageId=11567` | `get_player_trading_feed(uid)` | 大佬交易feed—比`get_trading_records`更可靠 |

| `aladdin/h5/m/getPageMutilDataNotLogin?pageId=11567` | `get_player_trading_feed_public(uid)` | 同上但无需cookie |

| `api.jdjygold.com/produTools/h5/m/getGoldPrice` | `get_gold_price()` | 实时金价 |

| `CaiFuPC/h5/m/queryAllStockHistory` | `get_stock_history(code)` | 股票历史数据(基金重仓股分析) |

| `wealthBase/newh5/m/getIndexDetail` | `get_index_detail(indexCode)` | 行业指数详情(关联ETF+基金+超额收益) |

| `wealthBase/newh5/m/getIndexBlockInfo` | `get_index_block_info(indexCode)` | **10年PE/PB日级百分位+投资信号评分**—行业择时核心 |

| `jj/h5/m/getRankingProductListV2` | `get_fund_ranking(filters)` | 19905只基金排行(按类型/周期/指标筛选) |

| `jj/h5/m/queryFullRanking` | `get_featured_rankings()` | 12个主题榜+5个人气认证榜TOP20 |



---



## 重要注意事项



1. **回测数据已验证正确**：fund_charts的yAxis是基金自成立来累计收益率%，不是用户个人收益。024239在2026-06-29的yAxis=123.40表示该基金从成立到那天涨了123%，用户当时买入后跌到101才导致-15%亏损。



2. **用户买入日RSI验证**：024239买入日RSI=62.7（未超买），013841买入日RSI=98.4（极端超买，系统会拦截），012922买入日RSI=64.4（未超买）。RSI择时能拦截部分但非全部高位买入。



3. **市场状态检测的局限**：`detect_market_state`用沪深300基准判断牛熊，但科技/QDII板块可能在"牛市"中独立回调。需要增加行业级市场状态检测。



4. **AGENTS.md** 已存在，包含兼容性规则和研究质量规则。CODEBUDDY.md补充技术架构信息。



5. **ai-berkshire-main是初始基准版本，不要修改**。所有改进只在当前项目(基金)中进行。



6. **JD金融API返回字段说明（实测验证）**：

   - `get_user_holdings(None)` → 你自己的持仓：`name, code, amount(持仓金额), profit_rate(盈亏%), profit(盈亏金额)` — **直接用，不要自己算**

   - `get_user_holdings(uid)` → 大佬持仓：同上字段

   - `get_fund_detail(code)` → 一键获取全部：`profile(基金类型/晨星评级), fee_info(费率), quotations(净值/涨跌幅), nav_history(净值历史), chart.chart_points(净值曲线), manager(经理), holdings_distribution(持仓分布)` — 比`fund_charts.json`更全更新

   - `get_fund_chart_data(code)` → 仅净值曲线，比get_fund_detail更轻量

   - **关键教训**：profit_rate/profit/amount 来自API直接返回，不要尝试用 fund_charts.json 的 yAxis（基金成立以来累计收益率）去反推用户盈亏，那是错的

