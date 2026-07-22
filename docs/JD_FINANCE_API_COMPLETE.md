# 京东金融 Web API 接口完整文档

> 生成时间: 2026-07-22 00:50:00
> 数据源: Playwright MCP 浏览器抓包 + JS Bundle 源码静态分析
> 覆盖页面: 7 个独立应用 × 34 个微服务 = 360 个去重 API
> 抓取方法: webpack chunk 清单提取 → 逐文件 fetch → 正则匹配 API 路径

## 抓取页面清单

| 页面 | URL | JS Bundle 数 | 发现 API 数 |
|------|-----|:---:|:---:|
| PC 主站 | `jdjr.jd.com` | 47 chunks | 76 |
| H5 基金详情(新版) | `lc.jr.jd.com/finance/funddetail/home/` | 5 | 16 |
| H5 业绩表现 | `lc.jr.jd.com/finance/fund/latestdetail/achievement/` | 3 | 43 |
| H5 基金档案 | `lc.jr.jd.com/finance/fund/latestdetail/fundArchives/` | 3 | 36 |
| H5 基金公告 | `lc.jr.jd.com/finance/fund/latestdetail/notice/` | 3 | 36 |
| 基金经理详情 | `lc.jr.jd.com/finance/fund/funddetail/newmanager-detail/` | 2 | 32 |
| 基金PK | `mse.jd.com/fund/fund-compare/` | 2 | 9 |
| 老版基金详情 | `lc.jr.jd.com/finance/fund/funddetail/` | 2 | 32 |
| 黄金交易首页 | `dingpan.jd.com/finance-gold/newgold/home/` | 18 | 211 |

## API 基础信息

### 请求地址

| Base URL | 说明 |
|----------|------|
| `https://ms.jr.jd.com` | 主 API 网关 (gw/generic/... 和 gw2/generic/...) |
| `https://dingpan.jd.com` | PC 版基金/黄金页面 |
| `https://lc.jr.jd.com` | H5 基金交易页面 |
| `https://mse.jd.com` | 基金PK页面 |
| `https://jdjr.jd.com` | 京东金融 PC 主站 |
| `https://m.jdjygold.com` | 黄金组件 CDN |

### 请求方式

- **POST** (大多数 API): `application/x-www-form-urlencoded`，body 为 `reqData={"key":"value"}` JSON 字符串
- **GET** (部分行情 API): 参数通过 URL query string 传递
- **Cookie**: 基金详情/净值/排行等公开数据不需要 cookie；持仓/交易/关注等需要登录 cookie
- **Referer/Origin**: PC 站接口需要 `Referer: https://jdjr.jd.com/`

### 响应格式

```json
{
  "success": true,
  "resultCode": "0000",
  "resultMessage": "操作成功",
  "resultData": {
    "datas": { ... }
  }
}
```

### 微服务分布

| 微服务 | API 数 | 说明 |
|--------|:---:|------|
| hj | 107 | 黄金交易（开户/买卖/充值/提现/银行卡） |
| jrm | 71 | 金融交易（黄金标准版交易/开户/订单） |
| jj | 58 | 基金（详情/净值/业绩/排行/自选/提醒/PK） |
| CaiFuPC | 26 | 财富PC站（自选/搜索/通知/Tab/反馈） |
| CreatorSer | 12 | 创作者服务（关注/内容/持仓/弹幕） |
| CfGoldWeb | 12 | 黄金Web（工作日/产品/银行卡/交易积分） |
| jimu | 9 | 社区积木（圈子/话题/Feed流） |
| koi | 9 | 加密接口（自选组/股票组/图表） |
| base | 8 | 基础服务（搜索/奖品/财富资产） |
| life | 7 | 生活/基金（详情页/业绩/资产变动） |
| quotegate | 5 | 行情网关（金价/ETF/央行储备/国家） |
| fcc | 5 | 金融中心（黄金翻倍/卡片/弹窗） |
| opdataapi | 4 | 行情数据（指数/净值/财富数据） |
| CfCoupon | 3 | 财富优惠券（批量领奖/活动查询/领奖） |
| ImServer | 2 | IM服务（公钥/Token） |
| legogw | 2 | 乐高网关（页面信息/限流） |
| uc | 2 | 用户中心（计数/显示） |
| wq | 2 | 问卷（关闭提示/获取） |
| 6440 | 1 | 黄金摊位 |
| app | 1 | App基础参数 |
| appOrigin | 1 | App来源 |
| integrated | 1 | 集成服务（交易跳转） |
| hyqy | 1 | 会员权益（领卡） |
| rabbitbff | 1 | BFF服务（分组添加） |
| redEnv001 | 1 | 红包（黄金交易活动） |
| touchFish | 1 | 摸鱼（板块排行） |
| jdtwt | 1 | 专题（自选产品列表） |
| gbetf | 1 | 金豆ETF（弹窗检查） |
| cfslink | 1 | 活动链接（可用活动） |
| 0019205 | 1 | 授权URL |
| jdxjk | 1 | 京东小金库（黄金鉴权） |
| aladdin | 1 | 阿拉丁（页面数据） |
| bx | 1 | 保险（用户状态） |
| getRSAPublicKey | 1 | RSA公钥 |

---

## 一、jj 服务 — 基金 (58 个)

### 基金详情

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 1 | `/gw/generic/jj/h5/m/fundDetail` | POST | 基金详情（综合） | 否 |
| 2 | `/gw/generic/jj/h5/m/getFundDetailPageInfo` | POST | 基金详情页信息 | 否 |
| 3 | `/gw/generic/jj/h5/m/getFundDetailChartPageInfo` | POST | 基金详情图表页信息 | 否 |
| 4 | `/gw/generic/jj/h5/m/getFundDetailProfilePageInfo` | POST | 基金档案页信息 | 否 |
| 5 | `/gw/generic/jj/h5/m/getFundValuationInfo` | POST | 基金估值信息 | 否 |
| 6 | `/gw/generic/jj/h5/m/queryProductSummary` | POST | 产品摘要 | 否 |
| 7 | `/gw/generic/jj/h5/m/queryRadarInfo` | POST | 雷达信息 | 否 |
| 8 | `/gw/generic/jj/h5/m/queryAssertDetail` | POST | 资产详情 | 是 |
| 9 | `/gw/generic/jj/h5/m/switchFundDetailVersion` | POST | 切换基金详情版本 | 否 |

### 基金净值与走势

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 10 | `/gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo` | POST | 历史净值页信息 | 否 |
| 11 | `/gw/generic/jj/h5/m/getFundHistoryList1` | POST | 历史净值列表 | 否 |
| 12 | `/gw/generic/jj/h5/m/getFundNetValueTrendChart` | POST | 净值走势图 | 否 |
| 13 | `/gw/generic/jj/h5/m/getFundIncomeRateTrendChart` | POST | 收益率走势图 | 否 |
| 14 | `/gw/generic/jj/h5/m/getFundHBMillionTrendChart` | POST | 华夏百万走势图 | 否 |
| 15 | `/gw/generic/jj/h5/m/getFundHBSevenTrendChart` | POST | 华夏七日走势图 | 否 |

### 基金业绩

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 16 | `/gw/generic/jj/h5/m/getFundHistoryPerformancePageInfo` | POST | 历史业绩页信息 | 否 |
| 17 | `/gw/generic/jj/h5/m/getFundHistoryProfitPageInfo` | POST | 历史收益页信息 | 否 |
| 18 | `/gw/generic/jj/h5/m/getFundYearPerformancePageInfo` | POST | 年度业绩页信息 | 否 |
| 19 | `/gw/generic/jj/h5/m/getHistoryAchievement1` | POST | 历史业绩 | 否 |
| 20 | `/gw/generic/jj/h5/m/getFundInvestmentDistributionPageInfo` | POST | 投资分布页信息 | 否 |
| 21 | `/gw2/generic/jj/h5/m/getFundInvestmentDistributionTwoVersionPageInfo` | POST | 投资分布（双版本） | 否 |

### 基金排行与筛选

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 22 | `/gw/generic/jj/h5/m/getFundRateRankListPageInfo` | POST | 收益排行列表 | 否 |
| 23 | `/gw2/generic/jj/h5/m/getFundSimilarRank` | POST | 相似基金排行 | 否 |
| 24 | `/gw2/generic/jj/newh5/m/getInvestResearchRank` | POST | 投研排行 | 否 |
| 25 | `/gw/generic/jj/h5/m/getFundHotCompareListPageInfo` | POST | 热门对比列表 | 否 |

### 交易规则与费率

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 26 | `/gw/generic/jj/h5/m/getFundTradeRulesPageInfo` | POST | 交易规则页信息 | 否 |
| 27 | `/gw/generic/jj/h5/m/getTradeRulesInfo` | POST | 交易规则详情 | 否 |
| 28 | `/gw/generic/jj/h5/m/fundWhetherOnSale` | POST | 基金是否在售 | 否 |

### 持仓分布与穿透

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 29 | `/gw/generic/jj/h5/m/getStockInfo` | POST | 股票/持仓信息 | 否 |
| 30 | `/gw2/generic/jj/h5/m/getFundDiagnosisTabPage` | POST | 基金诊断页 | 否 |

### 基金经理

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 31 | `/gw/generic/jj/h5/m/getFundManagerListPageInfo` | POST | 基金经理列表页 | 否 |
| 32 | `/gw/generic/jj/h5/m/getFundManagerDetailPageInfo` | POST | 基金经理详情页 | 否 |
| 33 | `/gw/generic/jj/h5/m/managerList` | POST | 经理列表 | 否 |
| 34 | `/gw/generic/jj/h5/m/getCompanyManagerInfo` | POST | 公司经理信息 | 否 |
| 35 | `/gw/generic/jj/h5/m/getCurrentManagerInfos` | POST | 当前经理信息 | 否 |

### 基金公告与分红

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 36 | `/gw/generic/jj/h5/m/getFundNoticesPageInfo` | POST | 基金公告页信息 | 否 |
| 37 | `/gw/generic/jj/h5/m/getNotices` | POST | 公告列表 | 否 |
| 38 | `/gw/generic/jj/h5/m/getFundDividendPageInfo` | POST | 分红页信息 | 否 |
| 39 | `/gw/generic/jj/h5/m/findDividendHistoryInfos` | POST | 历史分红信息 | 否 |
| 40 | `/gw/generic/jj/h5/m/getFundSharesSplitPageInfo` | POST | 份额拆分页信息 | 否 |
| 41 | `/gw/generic/jj/h5/m/findConvertInfos` | POST | 转换信息 | 否 |

### 自选与关注

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 42 | `/gw/generic/jj/h5/m/allZxGroups` | POST | 所有自选分组 | 是 |
| 43 | `/gw/generic/jj/h5/m/addAndModifyZxGroup` | POST | 添加/修改自选分组 | 是 |
| 44 | `/gw/generic/jj/h5/m/addFundZxProduct` | POST | 添加基金到自选 | 是 |
| 45 | `/gw/generic/jj/h5/m/cancelFundZxProduct` | POST | 取消自选基金 | 是 |
| 46 | `/gw/generic/jj/h5/m/addZxProductsToAnotherGroup` | POST | 移至其他分组 | 是 |
| 47 | `/gw/generic/jj/h5/m/createFdAttentionPerson` | POST | 关注基金经理 | 是 |
| 48 | `/gw/generic/jj/h5/m/deleteFdAttentionPerson` | POST | 取消关注基金经理 | 是 |

### 提醒

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 49 | `/gw/generic/jj/h5/m/createRemind` | POST | 创建提醒 | 是 |
| 50 | `/gw/generic/jj/h5/m/cancelRemind` | POST | 取消提醒 | 是 |

### 基金PK

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 51 | `/gw/generic/jj/h5/m/addFundCompare` | POST | 添加基金对比 | 否 |
| 52 | `/gw/generic/jj/h5/m/getFundComparePageInfo` | POST | 对比页信息 | 否 |
| 53 | `/gw/generic/jj/h5/m/getFundCompareZxProductPageInfo` | POST | 对比自选产品页 | 否 |
| 54 | `/gw/generic/jj/h5/m/getFundDetailChartListPageInfo` | POST | 对比图表列表页 | 否 |

### 优惠券

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 55 | `/gw/generic/jj/h5/m/getFundCouponInfo` | POST | 基金优惠券信息 | 是 |
| 56 | `/gw2/generic/jj/h5/m/getFundCouponList` | POST | 基金优惠券列表 | 是 |
| 57 | `/gw/generic/jj/h5/m/findProDetailPlusCardConfig` | POST | 产品详情Plus卡配置 | 否 |

### 其他

| # | API 路径 | 方法 | 说明 | 登录 |
|---|---------|:---:|------|:---:|
| 58 | `/gw2/generic/jj/h5/m/operationRecordsToCache` | POST | 操作记录缓存 | 否 |

---

## 二、hj 服务 — 黄金交易 (107 个)

### 开户

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw/generic/hj/h5/m/beforeOpenElecAccount` | 开户前检查 | 是 |
| 2 | `/gw/generic/hj/h5/m/openElecAccount` | 开立电子账户 | 是 |
| 3 | `/gw/generic/hj/h5/m/openElecAccountV2` | 开立电子账户V2 | 是 |
| 4 | `/gw2/generic/hj/h5/m/openElecAccountStdNew` | 标准开户(新) | 是 |
| 5 | `/gw2/generic/hj/h5/m/openElecAccountV3` | 开户V3 | 是 |
| 6 | `/gw/generic/hj/h5/m/completeOpenAcc` | 完成开户 | 是 |
| 7 | `/gw2/generic/hj/h5/m/completeOpenAccNew` | 完成开户(新) | 是 |
| 8 | `/gw2/generic/hj/h5/m/cfOpenAccountCommon` | 通用开户 | 是 |
| 9 | `/gw/generic/hj/h5/m/isGoOpenAccount` | 是否需要开户 | 是 |
| 10 | `/gw/generic/hj/h5/m/isOpenAcc` | 是否已开户 | 是 |
| 11 | `/gw/generic/hj/h5/m/getAccUserStuts` | 账户用户状态 | 是 |
| 12 | `/gw2/generic/hj/h5/m/getAccOpenUserStatus` | 开户用户状态 | 是 |
| 13 | `/gw2/generic/hj/h5/m/getAccOpenUserStatusForTrade` | 交易开户状态 | 是 |
| 14 | `/gw/generic/hj/h5/m/queryAccInfo` | 查询账户信息 | 是 |
| 15 | `/gw/generic/hj/h5/m/repSendMsmByOpenAcc` | 开户短信验证码 | 是 |
| 16 | `/gw/generic/hj/h5/m/sendAuthCode` | 发送验证码 | 是 |
| 17 | `/gw2/generic/hj/h5/m/upladPhotoHold` → `/gw/generic/hj/h5/m/upladPhotoHold` | 上传持证件照 | 是 |
| 18 | `/gw2/generic/hj/h5/m/upladIdCardPhotosStd` → `/gw/generic/jrm/h5/m/upladIdCardPhotosStd` | 上传身份证(标准) | 是 |
| 19 | `/gw2/generic/hj/h5/m/upladIdCardPhotosV2` → `/gw/generic/jrm/h5/m/upladIdCardPhotosV2` | 上传身份证V2 | 是 |

### 买卖交易

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 20 | `/gw/generic/hj/h5/m/buyGold` | 买入黄金 | 是 |
| 21 | `/gw/generic/hj/h5/m/sellGoldV2` | 卖出黄金V2 | 是 |
| 22 | `/gw/generic/hj/h5/m/elecBuyGold` | 电子买入 | 是 |
| 23 | `/gw/generic/hj/h5/m/elecSellGold` | 电子卖出 | 是 |
| 24 | `/gw/generic/hj/h5/m/createBuyOrder` | 创建购买订单 | 是 |
| 25 | `/gw/generic/hj/h5/m/buyGoldResultQuery3` | 买入结果查询 | 是 |
| 26 | `/gw/generic/hj/h5/m/sellGoldResultQuery3` | 卖出结果查询 | 是 |
| 27 | `/gw2/generic/hj/h5/m/stdBuGoldCreateOrderNew` | 标准买入下单(新) | 是 |
| 28 | `/gw2/generic/hj/h5/m/stdSellGoldNew` | 标准卖出(新) | 是 |
| 29 | `/gw2/generic/hj/h5/m/stdRechargeAndBuyGoldNew` | 标准充值买入(新) | 是 |
| 30 | `/gw/generic/hj/h5/m/elecPayProtocol` | 电子支付协议 | 是 |
| 31 | `/gw/generic/hj/h5/m/checkPayPassword` | 检查支付密码 | 是 |
| 32 | `/gw/generic/hj/h5/m/generalPoll` | 通用轮询 | 是 |
| 33 | `/gw/generic/hj/h5/m/orderProfit` | 订单盈亏 | 是 |
| 34 | `/gw/generic/hj/h5/m/getValidOrderInfo` | 有效订单信息 | 是 |
| 35 | `/gw2/generic/hj/h5/m/queryLimitPurchaseTotalOrderAmount` | 限购总额 | 是 |

### 行情价格

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 36 | `/gw/generic/hj/h5/m/todayPrices` | 今日价格 | 否 |
| 37 | `/gw/generic/hj/h5/m/todayLatestPrices` | 今日最新价格 | 否 |
| 38 | `/gw/generic/hj/h5/m/historyPrices` | 历史价格 | 否 |
| 39 | `/gw2/generic/hj/h5/m/cfGetLatestPriceInfo` | 最新价格信息 | 否 |
| 40 | `/gw2/generic/hj/h5/m/cfWsGetLatestPriceInfo` | WS最新价格 | 否 |
| 41 | `/gw2/generic/hj/h5/m/cfGetPriceTrendChart` | 价格走势图 | 否 |
| 42 | `/gw2/generic/hj/h5/m/cfGetQuotesPriceKLine` | K线数据 | 否 |
| 43 | `/gw2/generic/hj/h5/m/getKlineAndAvgLine` | K线及均线 | 否 |
| 44 | `/gw2/generic/hj/h5/m/gxGoldLatestPrice` | 国新黄金最新价 | 否 |
| 45 | `/gw/generic/hj/h5/m/queryMarketTdPriceListNoPin` | 市场价格(免登录) | 否 |
| 46 | `/gw/generic/hj/h5/m/queryQHChartList` | 期货行情列表 | 否 |
| 47 | `/gw2/generic/hj/h5/m/queryTradeAvgPrice` | 交易均价 | 否 |

### 持仓与资产

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 48 | `/gw/generic/hj/h5/m/getHoldingStat` | 持仓统计 | 是 |
| 49 | `/gw/generic/hj/h5/m/getHoldingStat1` | 持仓统计V1 | 是 |
| 50 | `/gw/generic/hj/h5/m/getAccountDetail` | 账户详情 | 是 |
| 51 | `/gw/generic/hj/h5/m/queryAccountAssets` | 账户资产 | 是 |
| 52 | `/gw/generic/hj/h5/m/queryAccountAssetsDetail` | 账户资产详情 | 是 |
| 53 | `/gw/generic/hj/h5/m/queryAccountAssetsV2` | 账户资产V2 | 是 |
| 54 | `/gw/generic/hj/h5/m/chargeAccountAssets` | 充值账户资产 | 是 |
| 55 | `/gw/generic/hj/h5/m/chargeAccountAssetsAmountLimit` | 充值限额 | 是 |
| 56 | `/gw/generic/hj/h5/m/withdrawAccountAssets` | 提现账户资产 | 是 |
| 57 | `/gw2/generic/hj/h5/m/stdChargeAssetsNew` | 标准充值(新) | 是 |
| 58 | `/gw/generic/hj/h5/m/getInterestList` | 收益列表 | 是 |
| 59 | `/gw/generic/hj/h5/m/getLastInterest` | 最新收益 | 是 |

### 银行卡

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 60 | `/gw/generic/hj/h5/m/getBuyGoldCardList` | 买入银行卡列表 | 是 |
| 61 | `/gw/generic/hj/h5/m/queryUserCard` | 用户银行卡 | 是 |
| 62 | `/gw/generic/hj/h5/m/queryUserHoldCardList` | 用户持有卡列表 | 是 |
| 63 | `/gw/generic/hj/h5/m/queryUserWithBindCardInfo` | 用户绑卡信息 | 是 |
| 64 | `/gw/generic/hj/h5/m/queryBankCardNo` | 银行卡号 | 是 |
| 65 | `/gw/generic/hj/h5/m/changeBindCard` | 更换绑卡 | 是 |
| 66 | `/gw/generic/hj/h5/m/applyChangerCard` | 申请换卡 | 是 |
| 67 | `/gw/generic/hj/h5/m/confirmChanggerCard` | 确认换卡 | 是 |
| 68 | `/gw/generic/hj/h5/m/changerTo2account` | 换卡转账户 | 是 |
| 69 | `/gw/generic/hj/h5/m/changgerCardResultQuery` | 换卡结果查询 | 是 |
| 70 | `/gw2/generic/hj/h5/m/changgerCardResultQueryForIndex` | 换卡结果(首页) | 是 |
| 71 | `/gw2/generic/hj/h5/m/getBindCardListNew` | 绑卡列表(新) | 是 |
| 72 | `/gw/generic/hj/newh5/m/getBindCardListNew` | 绑卡列表(新版) | 是 |
| 73 | `/gw2/generic/hj/h5/m/bankTagListSort` | 银行标签排序 | 是 |
| 74 | `/gw2/generic/hj/h5/m/getWithDrawPayMethods` | 提现支付方式 | 是 |
| 75 | `/gw/generic/hj/h5/m/updateBankPhone` | 更新银行手机 | 是 |

### 交易时间与限制

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 76 | `/gw/generic/hj/h5/m/getTradePeriod` | 交易时间段 | 否 |
| 77 | `/gw/generic/hj/h5/m/queryIsTradingTime` | 是否交易时间 | 否 |
| 78 | `/gw/generic/hj/h5/m/isWorkTime` | 是否工作时间 | 否 |
| 79 | `/gw/generic/hj/h5/m/getTradeAndOrderPlaceTimeStatus` | 交易下单时间状态 | 否 |
| 80 | `/gw2/generic/hj/h5/m/getCgbTradePeriodBy` | 广发交易时段 | 否 |
| 81 | `/gw2/generic/hj/h5/m/getCibTradePeriodBy` | 兴业交易时段 | 否 |
| 82 | `/gw/generic/hj/h5/m/getUserLimit` | 用户限额 | 是 |
| 83 | `/gw/generic/hj/h5/m/getUserTradeLimit` | 用户交易限额 | 是 |
| 84 | `/gw/generic/hj/h5/m/getUserMobile` | 用户手机号 | 是 |

### 优惠券与营销

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 85 | `/gw/generic/hj/h5/m/goldCoupons` | 黄金优惠券 | 是 |
| 86 | `/gw/generic/hj/h5/m/queryCouponList` | 优惠券列表 | 是 |
| 87 | `/gw/generic/hj/h5/m/queryCouponDetail` | 优惠券详情 | 是 |
| 88 | `/gw/generic/hj/h5/marketingList` → `/gw/generic/hj/h5/m/marketingList` | 营销列表 | 是 |
| 89 | `/gw/generic/hj/h5/m/marketingTop` | 营销顶部 | 是 |
| 90 | `/gw/generic/hj/h5/m/queryRedPacketByJrid` | 红包(按JrId) | 是 |
| 91 | `/gw/generic/hj/h5/m/queryTradeListResourceV3` | 交易列表资源V3 | 否 |
| 92 | `/gw2/generic/hj/h5/m/queryTrdPrizeTradeList` | 交易奖品列表 | 是 |

### 价格提醒

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 93 | `/gw/generic/hj/h5/m/myPriceRemindV2` | 我的提醒V2 | 是 |
| 94 | `/gw/generic/hj/h5/m/setPriceRemindV2` | 设置提醒V2 | 是 |
| 95 | `/gw/generic/hj/h5/m/getWelfareRemind` | 福利提醒 | 是 |

### 其他 hj

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 96 | `/gw/generic/hj/h5/m/isLogin` | 是否登录 | 是 |
| 97 | `/gw/generic/hj/h5/m/isCheckAuth` | 是否鉴权 | 是 |
| 98 | `/gw/generic/hj/h5/m/isWhiteUser` | 是否白名单 | 是 |
| 99 | `/gw/generic/hj/h5/m/autoCastRuleQuery` | 定投规则查询 | 是 |
| 100 | `/gw/generic/hj/h5/m/queryGoldProductInfo` | 黄金产品信息 | 否 |
| 101 | `/gw/generic/hj/h5/m/queryCgbTradePoints` | 广发交易积分 | 是 |
| 102 | `/gw/generic/hj/h5/m/queryCibTradePoints` | 兴业交易积分 | 是 |
| 103 | `/gw/generic/hj/h5/m/queryTradePoints` | 交易积分 | 是 |
| 104 | `/gw/generic/hj/h5/m/queryChargeWithdrawResult` | 充提结果 | 是 |
| 105 | `/gw/generic/hj/h5/m/queryUserInfo` | 用户信息 | 是 |
| 106 | `/gw2/generic/hj/h5/m/cacheBrowseRecord` | 缓存浏览记录 | 否 |
| 107 | `/gw2/generic/hj/h5/m/handleBizRiskParamGold` | 业务风控参数 | 否 |

---

## 三、jrm 服务 — 金融交易 (71 个)

### 黄金标准版交易

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/jrm/h5/m/stdBuGoldCreateOrder` | 标准买入下单 | 是 |
| 2 | `/gw2/generic/jrm/h5/m/stdSellGold` | 标准卖出 | 是 |
| 3 | `/gw2/generic/jrm/h5/m/stdRechargeAndBuyGold` | 标准充值买入 | 是 |
| 4 | `/gw2/generic/jrm/h5/m/stdChargeAssets` | 标准充值 | 是 |
| 5 | `/gw2/generic/jrm/h5/m/stdChargeAccountAssetsAmountLimit` | 标准充值限额 | 是 |
| 6 | `/gw2/generic/jrm/h5/m/buyGoldCreateOrder` | 买入下单 | 是 |
| 7 | `/gw2/generic/jrm/h5/m/rechargeAndBuyGold` | 充值买入 | 是 |
| 8 | `/gw2/generic/jrm/h5/m/rechargeAndBuyGoldResultQuery` | 充值买入结果 | 是 |
| 9 | `/gw2/generic/jrm/h5/m/buyOrSellTradeResultQuery` | 买卖结果查询 | 是 |

### 开户（标准版）

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 10 | `/gw2/generic/jrm/h5/m/completeOpenAccStd` | 完成开户(标准) | 是 |
| 11 | `/gw2/generic/jrm/h5/m/queryAccOpenResultStd` | 开户结果(标准) | 是 |
| 12 | `/gw2/generic/jrm/h5_m/getAccUserStutsStd` → `/gw2/generic/jrm/h5/m/getAccUserStutsStd` | 账户状态(标准) | 是 |
| 13 | `/gw2/generic/jrm/h5/m/repSendMsmByOpenAccStd` | 开户短信(标准) | 是 |
| 14 | `/gw2/generic/jrm/h5/m/sendAuthCodeV2` | 发送验证码V2 | 是 |
| 15 | `/gw2/generic/jrm/h5/m/elecPayProtocolStd` | 电子协议(标准) | 是 |

### 银行卡（标准版）

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 16 | `/gw2/generic/jrm/h5/m/getStdBuyGoldCardList` | 标准买入银行卡 | 是 |
| 17 | `/gw2/generic/jrm/h5/m/getStdBuyGoldCardListManyPayMethod` | 标准多支付方式 | 是 |
| 18 | `/gw2/generic/jrm/h5/m/getBuyGoldCardListAndManyPayMethod` | 买入卡+多支付 | 是 |

### 订单与持仓

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 19 | `/gw2/generic/jrm/h5/m/getStdValidOrderInfo` | 标准有效订单 | 是 |
| 20 | `/gw2/generic/jrm/h5/m/getFictitiousHoldingStat` | 虚拟持仓统计 | 是 |
| 21 | `/gw2/generic/jrm/h5/m/getTotalHoldingStat` | 总持仓统计 | 是 |
| 22 | `/gw2/generic/jrm/h5/m/orderValidator` | 订单校验 | 是 |
| 23 | `/gw2/generic/jrm/h5/m/queryActivityOrder` | 活动订单 | 是 |
| 24 | `/gw2/generic/jrm/h5/m/queryStdRechargeAndBuyGoldResult` | 标准充值买入结果 | 是 |
| 25 | `/gw2/generic/jrm/h5/m/queryStdChargeWithdrawResult` | 标准充提结果 | 是 |

### 交易时间

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 26 | `/gw2/generic/jrm/h5/m/isWorkTimeStd` | 工作时间(标准) | 否 |
| 27 | `/gw2/generic/jrm/h5/m/getTradePeriodStd` | 交易时段(标准) | 否 |
| 28 | `/gw2/generic/jrm/h5/m/getTradePeriodIcbc` | 工行交易时段 | 否 |

### 优惠券与积分

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 29 | `/gw2/generic/jrm/h5/m/queryCouponList` | 优惠券列表 | 是 |
| 30 | `/gw2/generic/jrm/h5/m/queryStdCouponList` | 标准优惠券 | 是 |
| 31 | `/gw2/generic/jrm/h5/m/queryStdCouponAndEquityCardList` | 标准券+权益卡 | 是 |
| 32 | `/gw2/generic/jrm/h5/m/queryGoldCouponAndEquityCardList` | 黄金券+权益卡 | 是 |
| 33 | `/gw2/generic/jrm/h5/m/queryStdTradePoints` | 标准交易积分 | 是 |
| 34 | `/gw2/generic/jrm/h5/m/queryIcbcTradePoints` | 工行积分 | 是 |
| 35 | `/gw2/generic/jrm/h5/m/queryStdRedPacketPrize` | 标准红包奖品 | 是 |
| 36 | `/gw2/generic/jrm/h5/m/queryStdUserIdentityByCoupon` | 券用户身份 | 是 |
| 37 | `/gw2/generic/jrm/h5/m/doDoublePrize` | 双倍奖品 | 是 |
| 38 | `/gw2/generic/jrm/h5/m/queryMyDoublePrize` | 我的双倍奖品 | 是 |

### 资产

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 39 | `/gw2/generic/jrm/h5/m/queryStdAssetsBal` | 标准资产余额 | 是 |
| 40 | `/gw2/generic/jrm/h5/m/queryStdAssetsBalV2` | 标准资产余额V2 | 是 |
| 41 | `/gw2/generic/jrm/h5/m/querySellAccountTypeInfo` | 卖出账户类型 | 是 |

### 定投规则

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 42 | `/gw2/generic/jrm/h5/m/saveOrderRule` | 保存订单规则 | 是 |
| 43 | `/gw2/generic/jrm/h5/m/cancelOrderRule` | 取消订单规则 | 是 |
| 44 | `/gw2/generic/jrm/h5/m/chargeOrderRule` | 充值订单规则 | 是 |
| 45 | `/gw2/generic/jrm/h5/m/chargeRuleResultQuery` | 充值规则结果 | 是 |
| 46 | `/gw2/generic/jrm/h5/m/queryConditionalRuleList` | 条件规则列表 | 是 |

### 用户信息

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 47 | `/gw2/generic/jrm/h5/m/getUserMultiElementsInfo` | 用户多要素信息 | 是 |
| 48 | `/gw2/generic/jrm/h5/m/verifyNineElements` | 九要素验证 | 是 |
| 49 | `/gw2/generic/jrm/h5/m/updateCompany` | 更新公司 | 是 |
| 50 | `/gw2/generic/jrm/h5/m/updateRemindStauts` | 更新提醒状态 | 是 |
| 51 | `/gw2/generic/jrm/h5/m/updateStdRemindStatus` | 更新标准提醒 | 是 |

### 行情与产品

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 52 | `/gw2/generic/jrm/h5/m/indexData` | 指数数据 | 否 |
| 53 | `/gw2/generic/jrm/h5/m/tradeIndex` | 交易指数 | 否 |
| 54 | `/gw2/generic/jrm/h5/m/tradeIndexStd` | 标准交易指数 | 否 |
| 55 | `/gw2/generic/jrm/h5/m/jumpQuotationOne` | 跳转行情 | 否 |
| 56 | `/gw2/generic/jrm/h5/m/queryGoldProductInfo` | 黄金产品信息 | 否 |
| 57 | `/gw2/generic/jrm/h5/m/queryProductInfo` | 产品信息 | 否 |
| 58 | `/gw2/generic/jrm/h5/m/queryTradeDescStd` | 交易描述(标准) | 否 |
| 59 | `/gw2/generic/jrm/newh5/m/indexData` | 指数数据(新版) | 否 |
| 60 | `/gw2/generic/jrm/newh5/m/queryCommunityTradeGuide` | 社区交易引导 | 否 |

### 支付收银台

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 61 | `/gw/generic/jrm/h5/m/getNewOldCashierMethod` | 新旧收银方式 | 是 |
| 62 | `/gw/generic/jrm/h5/m/getPreCashierDefaultMethod` | 默认收银方式 | 是 |
| 63 | `/gw/generic/jrm/h5/m/getPreCashierMethodList` | 收银方式列表 | 是 |
| 64 | `/gw/generic/jrm/h5/m/judgeNeedCheckAuth` | 是否需要鉴权 | 是 |

### 摊位与调查

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 65 | `/gw/generic/jrm/h5/m/queryStallNew` | 查询摊位(新) | 否 |
| 66 | `/gw/generic/jrm/h5/m/getWmpStallList` | WMP摊位列表 | 否 |
| 67 | `/gw/generic/jrm/h5/m/getWmpStallListNoLogin` | WMP摊位(免登录) | 否 |
| 68 | `/gw/generic/jrm/h5/m/findLastSurvey1` | 最近调查 | 是 |

### 行情指数

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 69 | `/gw/generic/jrm/h5/m/getUnderrateIndexChart` | 低估指数图表 | 否 |

### 身份证上传

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 70 | `/gw2/generic/jrm/h5/m/upladIdCardPhotosStd` | 身份证(标准) | 是 |
| 71 | `/gw2/generic/jrm/h5/m/upladIdCardPhotosV2` | 身份证V2 | 是 |

---

## 四、CaiFuPC 服务 — 财富PC站 (26 个)

### 自选与搜索

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/CaiFuPC/h5/m/addStockSearchHistory` | 添加搜索历史 | 是 |
| 2 | `/gw2/generic/CaiFuPC/h5/m/delSearchHistory` | 删除搜索历史 | 是 |
| 3 | `/gw2/generic/CaiFuPC/h5/m/delALLSearchHistory` | 删除全部搜索历史 | 是 |
| 4 | `/gw2/generic/CaiFuPC/h5/m/codeListIsAttention` | 代码是否关注 | 是 |

### 通知与提醒

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 5 | `/gw2/generic/CaiFuPC/h5/m/getNotifyByPin` | 按Pin获取通知 | 是 |
| 6 | `/gw2/generic/CaiFuPC/h5/m/saveNotify` | 保存通知 | 是 |
| 7 | `/gw2/generic/CaiFuPC/h5/m/queryRateLimit` | 查询频率限制 | 是 |
| 8 | `/gw2/generic/CaiFuPC/h5/m/saveRateLimit` | 保存频率限制 | 是 |
| 9 | `/gw2/generic/CaiFuPC/h5/m/checkBenefitPop` | 检查福利弹窗 | 是 |

### Tab管理

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 10 | `/gw2/generic/CaiFuPC/h5/m/queryPcTab` | 查询PC Tab | 是 |
| 11 | `/gw2/generic/CaiFuPC/h5/m/addPcTab` | 添加PC Tab | 是 |
| 12 | `/gw2/generic/CaiFuPC/h5/m/delPcTab` | 删除PC Tab | 是 |
| 13 | `/gw2/generic/CaiFuPC/h5/m/updatePcTab` | 更新PC Tab | 是 |
| 14 | `/gw2/generic/CaiFuPC/h5/m/updateOpenedTab` | 更新已打开Tab | 是 |

### 行情图表

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 15 | `/gw2/generic/CaiFuPC/h5/m/getTimeSharingDots` | 分时点数据 | 否 |
| 16 | `/gw2/generic/CaiFuPC/pc/m/getCandleDotsByNumsUseUniqueCode` | K线点数据 | 否 |
| 17 | `/gw2/generic/CaiFuPC/pc/m/getTimeSharingDotsByDateTime` | 分时点(按日期) | 否 |
| 18 | `/gw2/generic/CaiFuPC/h5/m/queryAllStockHistory` | 全部股票历史 | 否 |

### 黄金Tab

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 19 | `/gw2/generic/CaiFuPC/h5/m/queryGoldTab` | 黄金Tab | 否 |

### 任务与反馈

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 20 | `/gw2/generic/CaiFuPC/h5/m/queryMissionStatus` | 任务状态 | 是 |
| 21 | `/gw2/generic/CaiFuPC/h5/m/unlockMission` | 解锁任务 | 是 |
| 22 | `/gw2/generic/CaiFuPC/h5/m/sendFeedback` | 发送反馈 | 是 |

### Cookie与认证

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 23 | `/gw2/generic/CaiFuPC/h5/m/addJdCookie` | 添加JD Cookie | 是 |
| 24 | `/gw2/generic/CaiFuPC/h5/m/addTradeCookie` | 添加交易Cookie | 是 |

### 其他

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 25 | `/gw2/generic/CaiFuPC/h5/m/generatePresignedUrl` | 生成预签名URL | 是 |
| 26 | `/gw2/generic/CaiFuPC/h5/m/deleteInvitationRecord` | 删除邀请记录 | 是 |

---

## 五、CreatorSer 服务 — 创作者/社区 (12 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo` | PC查询用户信息 | 是 |
| 2 | `/gw2/generic/CreatorSer/h5/m/queryUserFundHoldInfo` | 用户基金持仓 | 是 |
| 3 | `/gw2/generic/CreatorSer/h5/m/queryUserGoldHoldInfo` | 用户黄金持仓 | 是 |
| 4 | `/gw2/generic/CreatorSer/h5/m/queryLatestFolloweeContent` | 最新关注内容 | 是 |
| 5 | `/gw2/generic/CreatorSer/h5/m/queryLatestSubscribedGoldTrades` | 最新订阅黄金交易 | 是 |
| 6 | `/gw2/generic/CreatorSer/h5/m/getRecommendContents` | 推荐内容 | 否 |
| 7 | `/gw2/generic/CreatorSer/h5/m/pcQueryGoldProduct` | PC黄金产品 | 否 |
| 8 | `/gw2/generic/CreatorSer/h5/m/pcQueryGoldQuote` | PC黄金行情 | 否 |
| 9 | `/gw2/generic/CreatorSer/pc/m/pcQueryGoldProduct` | PC黄金产品(pc) | 否 |
| 10 | `/gw2/generic/CreatorSer/newh5/m/getCircleBarrageComponent` | 圈子弹幕组件 | 否 |
| 11 | `/gw2/generic/CreatorSer/newh5/m/getCircleContentForBarrage` | 弹幕内容 | 否 |
| 12 | `/gw2/generic/CreatorSer/newh5/m/queryGoldPageDetailComponent` | 黄金页详情组件 | 否 |

---

## 六、jimu 服务 — 社区/积木 (9 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw/generic/jimu/h5/m/homeFeedFlow` | 首页Feed流 | 否 |
| 2 | `/gw/generic/jimu/h5/m/feedFlowOfCircle` | 圈子Feed流 | 否 |
| 3 | `/gw/generic/jimu/h5/m/getMoreRelateMergeTopic` | 更多相关合并话题 | 否 |
| 4 | `/gw/generic/jimu/h5/m/queryCircleHeadInfo` | 圈子头部信息 | 否 |
| 5 | `/gw/generic/jimu/h5/m/queryTopicHeadInfo` | 话题头部信息 | 否 |
| 6 | `/gw/generic/jimu/h5/m/searchCircleHotList` | 搜索圈子热门 | 否 |
| 7 | `/gw/generic/jimu/h5/m/getHaveCommunityAndUnread` | 社区和未读 | 是 |
| 8 | `/gw/generic/jimu/h5/m/recordExternalInterview` | 记录外部访谈 | 否 |
| 9 | `/gw/generic/jimu/h5/m/getRelatedCircleInfo` | 相关圈子信息 | 否 |

---

## 七、koi 服务 — 加密接口 (9 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/koi/h5/m/executeEncrypted?command=GROUP_CREATE` | 创建分组 | 是 |
| 2 | `/gw2/generic/koi/h5/m/executeEncrypted?command=GROUP_DELETE` | 删除分组 | 是 |
| 3 | `/gw2/generic/koi/h5/m/executeEncrypted?command=GROUP_UPDATE` | 更新分组 | 是 |
| 4 | `/gw2/generic/koi/h5/m/executeEncrypted?command=STOCK_GROUP_DEL` | 股票组删除 | 是 |
| 5 | `/gw2/generic/koi/h5/m/executeEncrypted?command=STOCK_GROUP_INFO` | 股票组信息 | 是 |
| 6 | `/gw2/generic/koi/h5/m/executeEncrypted?command=STOCK_GROUP_REVISE` | 股票组修改 | 是 |
| 7 | `/gw2/generic/koi/h5/m/executeEncrypted?command=STOCK_TOP` | 股票置顶 | 是 |
| 8 | `/gw2/generic/koi/h5/m/lcExecuteEncrypted?stag=lineChartRequest` | 图表请求(加密) | 否 |
| 9 | `/gw2/generic/koi/h5/m/lcExecuteEncrypted?tags=RequestGroupAndList` | 分组列表(加密) | 否 |

---

## 八、base 服务 — 基础 (8 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw/generic/base/h5/m/getSearchResultCompletionWord` | 搜索补全 | 否 |
| 2 | `/gw2/generic/base/h5/m/getSearchResultCompletionWordEncry` | 搜索补全(加密) | 否 |
| 3 | `/gw/generic/base/h5/m/learnAndGetPrize` | 学习领奖 | 是 |
| 4 | `/gw/generic/base/h5/m/canChange` | 是否可兑换 | 是 |
| 5 | `/gw/generic/base/h5/m/changePrize` | 兑换奖品 | 是 |
| 6 | `/gw/generic/base/h5/m/salaryTackPrize` | 工资领奖 | 是 |
| 7 | `/gw2/generic/base/h5/m/getWealthAssetIncome` | 财富资产收益 | 是 |
| 8 | `/gw2/generic/base/h5/m/queryCouponStatus` | 优惠券状态 | 是 |

---

## 九、life 服务 — 基金/生活 (7 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/life/h5/m/getFundDetailPageInfoWithNoPin` | 基金详情(免登录) | 否 |
| 2 | `/gw2/generic/life/h5/m/getFundDetailPageInfoWithPin` | 基金详情(登录) | 是 |
| 3 | `/gw2/generic/life/h5/m/getChangesInNetAssets` | 净资产变动 | 否 |
| 4 | `/gw2/generic/life/h5/m/getMonthPerformance` | 月业绩 | 否 |
| 5 | `/gw2/generic/life/h5/m/getQuarterPerformance` | 季业绩 | 否 |
| 6 | `/gw2/generic/life/h5/m/getMarketGrantPlusCard2` | 市场赠卡 | 是 |
| 7 | `/gw2/generic/life/h5/m/oldPageOrNewPage` | 新旧页面判断 | 否 |

---

## 十、CfGoldWeb 服务 — 黄金Web (12 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/CfGoldWeb/h5/m/cfGetGuideOrgList` | 引导机构列表 | 否 |
| 2 | `/gw2/generic/CfGoldWeb/h5/m/cfGetWorkDay` | 工作日 | 否 |
| 3 | `/gw2/generic/CfGoldWeb/newh5/m/cfGetWorkDay` | 工作日(新版) | 否 |
| 4 | `/gw2/generic/CfGoldWeb/h5/m/cfGoldDefaultRecommendAmount` | 默认推荐金额 | 否 |
| 5 | `/gw2/generic/CfGoldWeb/h5/m/cfQueryBindCardList` | 绑卡列表 | 是 |
| 6 | `/gw2/generic/CfGoldWeb/h5/m/cfQueryBuyResult` | 买入结果 | 是 |
| 7 | `/gw2/generic/CfGoldWeb/h5/m/cfQuerySellResult` | 卖出结果 | 是 |
| 8 | `/gw2/generic/CfGoldWeb/h5/m/cfQueryGoldProductInfo` | 黄金产品信息 | 否 |
| 9 | `/gw2/generic/CfGoldWeb/h5/m/cfQueryTradePoints` | 交易积分 | 是 |
| 10 | `/gw2/generic/CfGoldWeb/h5/m/unlockBankAccount` | 解锁银行账户 | 是 |
| 11 | `/gw2/generic/CfGoldWeb/newh5/m/cfQueryLastTrade` | 最近交易(新版) | 是 |
| 12 | `/gw/generic/CfGoldWeb/h5/m/cfGetGuideOrgList` | 引导机构(gw) | 否 |

---

## 十一、quotegate 服务 — 行情网关 (5 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/quotegate/h5/m/getGoldQuoteAndSpreads` | 金价及点差 | 否 |
| 2 | `/gw2/generic/quotegate/h5/m/getHistoryETFSpreads` | 历史ETF点差 | 否 |
| 3 | `/gw2/generic/quotegate/h5/m/getHistoryGoldCentralBankReserve` | 央行黄金储备 | 否 |
| 4 | `/gw2/generic/quotegate/newh5/m/getGoldCountryList` | 黄金国家列表 | 否 |
| 5 | `/gw2/generic/quotegate/h5/m/getTimeSharingInfo5Day` | 5日分时 | 否 |

---

## 十二、opdataapi 服务 — 行情数据 (4 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes` | 简单行情(按唯一码) | 否 |
| 2 | `/gw/generic/opdataapi/h5/m/getTimeSharingDots` | 分时点数据 | 否 |
| 3 | `/gw2/generic/opdataapi/newh5/m/getWealthDatas` | 财富数据 | 否 |
| 4 | `/gw2/generic/opdataapi/h5/m/getData` | 通用数据 | 否 |

---

## 十三、fcc 服务 — 金融中心 (5 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/fcc/h5/m/doGoldDouble` | 黄金翻倍 | 是 |
| 2 | `/gw2/generic/fcc/h5/m/queryGoldDoublePage` | 黄金翻倍页 | 是 |
| 3 | `/gw2/generic/fcc/h5/m/expandCardHome` | 扩展卡首页 | 是 |
| 4 | `/gw2/generic/fcc/h5/m/goldWidgetCheckCanShow` | 黄金组件检查 | 否 |
| 5 | `/gw2/generic/fcc/h5/m/queryAndCheck` | 查询并检查 | 是 |

---

## 十四、其他服务 (29 个)

### CfCoupon — 优惠券 (3 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/CfCoupon/h5/m/batchLearnAndGetPrize` | 批量学习领奖 | 是 |
| 2 | `/gw2/generic/CfCoupon/h5/m/skuActivityQuery` | SKU活动查询 | 是 |
| 3 | `/gw2/generic/CfCoupon/h5/m/takePrize` | 领奖 | 是 |

### ImServer — IM服务 (2 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias` | SM公钥 | 是 |
| 2 | `/gw2/generic/ImServer/h5/m/getPCToken` | PC Token | 是 |

### legogw — 乐高网关 (2 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw2/generic/legogw/h5/m/getPageInfoForH5` | 页面信息 | 否 |
| 2 | `/gw2/generic/legogw/h5/m/addFieldLimitCountForH5` | 字段限流 | 否 |

### uc — 用户中心 (2 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw/generic/uc/h5/m/addCountForGroup` | 分组计数 | 否 |
| 2 | `/gw/generic/uc/h5/m/isShow` | 是否显示 | 否 |

### wq — 问卷 (2 个)

| # | API 路径 | 说明 | 登录 |
|---|---------|------|:---:|
| 1 | `/gw/generic/wq/h5/m/closeTips` | 关闭提示 | 是 |
| 2 | `/gw/generic/wq/h5/m/getBySourceId` | 按来源获取 | 是 |

### 单个API服务 (16 个)

| # | API 路径 | 服务 | 说明 | 登录 |
|---|---------|------|------|:---:|
| 1 | `/gw/generic/getRSAPublicKey` | RSA | RSA公钥 | 否 |
| 2 | `/gw/generic/app/h5/m/getBasicParamForJR` | app | 基础参数 | 否 |
| 3 | `/gw2/generic/appOrigin/h5/m` | appOrigin | App来源 | 否 |
| 4 | `/gw2/generic/integrated/h5/m/queryOpenOrTradeDealerJumpInfo` | integrated | 交易跳转 | 否 |
| 5 | `/gw/generic/hyqy/h5/m/receivePlusCard` | hyqy | 领卡 | 是 |
| 6 | `/gw2/generic/rabbitbff/h5/m/codesAddByGroupIds` | rabbitbff | 分组添加代码 | 是 |
| 7 | `/gw2/generic/redEnv001/newh5/m/queryGoldTradingActivityStatus` | redEnv001 | 黄金交易活动 | 否 |
| 8 | `/gw2/generic/touchFish/h5/m/getPlateRank` | touchFish | 板块排行 | 否 |
| 9 | `/gw2/generic/jdtwt/h5/m/queryZxProductList` | jdtwt | 自选产品列表 | 否 |
| 10 | `/gw2/generic/6440/h5/m/queryStallForGold` | 6440 | 黄金摊位 | 否 |
| 11 | `/gw2/generic/gbetf/h5/m/checkGoldBeanWidget` | gbetf | 金豆组件检查 | 否 |
| 12 | `/gw2/generic/cfslink/h5/m/queryCanUseAct` | cfslink | 可用活动 | 否 |
| 13 | `/gw2/generic/0019205/h5/m/getAuthUrl` | 0019205 | 授权URL | 是 |
| 14 | `/gw2/generic/jdxjk/newh5/m/goldJudgeNeedCheckAuth` | jdxjk | 黄金鉴权 | 是 |
| 15 | `/gw/generic/aladdin/h5/m/getPageMultiDataForH5` | aladdin | 页面多数据 | 否 |
| 16 | `/gw/generic/bx/h5/m/getUserStatus` | bx | 保险用户状态 | 是 |

---

## 附录：已实现的接口 (jd_finance_api.py)

以下接口已在 `tools/jd_finance_api.py` 中实现并封装：

| CLI 参数 | 对应 API | 说明 |
|---------|---------|------|
| `--test` | Cookie有效性检查 | 测试登录状态 |
| `--trade-rules {code}` | `jj/h5/m/getFundTradeRulesPageInfo` | 交易规则 |
| `--fund-holdings {code}` | `jj/h5/m/getFundInvestmentDistributionPageInfo` | 持仓分布 |
| `--fund-profile {code}` | `jj/h5/m/getFundDetailProfilePageInfo` | 基金档案 |
| `--fund-perf {code}` | `jj/h5/m/getFundHistoryPerformancePageInfo` | 业绩排名 |
| `--fund-manager {code}` | `jj/h5/m/getFundManagerListPageInfo` | 基金经理 |
| `--holdings {uid}` | 用户持仓 | 需登录 |
| `--batch-holdings` | 批量持仓 | 需登录 |
| `--fund-history {code}` | `jj/h5/m/getFundHistoryNetValuePageInfo` | 历史净值 |
| `--fund-dividend {code}` | `jj/h5/m/getFundDividendPageInfo` | 分红送配 |
| `--fund-notices {code}` | `jj/h5/m/getFundNoticesPageInfo` | 基金公告 |
| `--fund-split {code}` | `jj/h5/m/getFundSharesSplitPageInfo` | 份额拆分 |
| `--fund-detail {code}` | `life/h5/m/getFundDetailPageInfoWithNoPin` | 基金详情 |
| `--fund-chart {code}` | `jj/h5/m/getFundDetailChartPageInfo` | 详情图表 |
| `--fund-year-perf {code}` | `jj/h5/m/getFundYearPerformancePageInfo` | 年度业绩 |
| `--fund-profit {code}` | `jj/h5/m/getFundHistoryProfitPageInfo` | 历史收益 |
| `--fund-similar {code}` | `jj/h5/m/getFundSimilarRank` | 相似排行 |
| `--fund-diagnosis {code}` | `jj/h5/m/getFundDiagnosisTabPage` | 基金诊断 |
| `--fund-nav-trend {code}` | `jj/h5/m/getFundNetValueTrendChart` | 净值走势 |
| `--fund-income-trend {code}` | `jj/h5/m/getFundIncomeRateTrendChart` | 收益走势 |
| `--fund-valuation {code}` | `jj/h5/m/getFundValuationInfo` | 估值信息 |
| `--fund-radar {code}` | `jj/h5/m/queryRadarInfo` | 雷达信息 |
| `--fund-coupon {code}` | `jj/h5/m/getFundCouponInfo` | 优惠券 |
| `--fund-stock {code}` | `jj/h5/m/getStockInfo` | 持仓股票 |
| `--fund-convert {code}` | `jj/h5/m/findConvertInfos` | 转换信息 |
| `--fund-assert {code}` | `jj/h5/m/queryAssertDetail` | 资产详情 |
| `--fund-product {code}` | `jj/h5/m/queryProductSummary` | 产品摘要 |
| `--fund-rank {code}` | `jj/h5/m/getFundRateRankListPageInfo` | 收益排行 |
| `--invest-research` | `jj/newh5/m/getInvestResearchRank` | 投研排行 |
| `--offline` | 使用缓存 | 离线模式 |

---

## 附注

1. **数据抓取方法**: 通过 Playwright MCP 浏览器自动化，访问京东金融各个页面，提取所有 JS Bundle 文件，使用正则表达式搜索 API 路径模式 (`/gw/generic/...`, `/gw2/generic/...`, `ms.jr.jd.com/...`)。
2. **覆盖范围**: 本次抓取覆盖了 PC 主站、H5 基金详情、业绩表现、基金档案、基金公告、基金经理详情、基金PK、黄金交易首页共 8 个独立应用。
3. **局限性**: 
   - 部分接口可能需要特定参数才能触发
   - 某些接口可能仅在特定条件下加载（如登录状态、特定基金类型）
   - 移动端 App 专用接口未覆盖
   - 部分接口可能已废弃但仍保留在 JS 代码中
4. **API 命名规律**: `/gw/generic/{服务名}/{平台}/{m}/{方法名}`，其中平台为 `h5`/`newh5`/`na`/`newna`/`pc`。
5. **本文件仅供学习研究使用，不构成投资建议。**
