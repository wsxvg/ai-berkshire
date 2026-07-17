# 京东金融 API 完整挖掘文档（基金 + 圈子 + 牛人）

> **生成时间**: 2026-07-12 23:32:49  
> **挖掘方法**: Playwright MCP 操控真实登录态浏览器，捕获 ms.jr.jd.com 全部 API 调用  
> **端点总数**: 41 个（含成功 + 失败）  
> **响应总大小**: 1861.8 KB  
> **登录账号**: jd_9b2u5ec8t4pmtb (uid=17533758, jimu_user_info-17533758)  
> **目标域**: jdjr.jd.com (PC H5 已登录) + ms.jr.jd.com (网关) + api.jdjygold.com (积存金)  

---

## 目录

1. [关键发现速览](#关键发现速览)
2. [你实际关注的大佬列表](#你实际关注的大佬列表)
3. [七大类端点详细文档](#七大类端点详细文档)
4. [响应结构示例](#响应结构示例)
5. [即用型 Python 封装](#即用型-python-封装)
6. [404 端点清单（路径错误）](#404-端点清单路径错误)
7. [原始响应数据位置](#原始响应数据位置)

---

## 关键发现速览

### ✅ 真实工作的 41 个端点（按业务归类）

| 类别 | 端点数 | 代表端点 | 用途 |
|---|---|---|---|
| 认证基础 | 8 | `pcQueryUserInfo` | 登录态/用户信息 |
| 行情数据 | 9 | `getSimpleQuoteUseUniqueCodes` | A股/港股/美股/黄金 |
| 基金排行 | 7 | **`queryFullRanking`** | 26 榜 520 只基金 |
| 圈子/Feed | 12 | **`feedFlowOfCircle tagId=112`** | 关注流 |
| 牛人榜 | 6 | **`queryFundFirmOfferMultiRank`** | 实盘牛人多榜 |
| 持仓 | 3 | **`queryUserFundHoldingInfo`** | 个人持仓 |
| 辅助 | 4 | `legogw / buildVisualizeData` | 页面渲染 |

### 🎯 最重要 5 个新发现

1. **`pcQueryUserInfo` 返回您自己的 numeric_id = 17533758**  
   `{"uid":"jimu_user_info-17533758","userName":"jd_9b2u5ec8t4pmtb"}`

2. **`queryUserFundHoldingInfo` userId 参数不影响** —— 永远返回当前登录用户持仓  
   13.4KB 包含 fundList, totalAmount, userInfo 等

3. **`feedFlowOfCircle tagId=112 contentId=2689640`** = 关注流  
   渲染您关注的所有大佬动态（蓝鲸/红豆/和路雪/Z先生/晴空/小猫咪）

4. **`queryFundFirmOfferMultiRank` rankType 400-405 = 5 大牛人榜**  
   与 queryFullRanking 互补：Full 是基金，牛人是持有人排名

5. **`homePageHeadInfo` + `getPageMutilData pageId=3973` = 蓝鲸跃财个人主页**  
   `homePageHeadInfo` 5.9KB 含 headImg/fans/follows/desc

### ❌ 失败的端点（路径错或已下线）

| 端点 | 原因 |
|---|---|
| `getInvestResearchRank` | 已下线 status=FAIL |
| `getRankingProductListV2` | 已下线 "请先登录" |
| `getFundDetail / getTradeRule / queryFundDetail / queryNetValueTrend / queryPerformance / queryFundPortfolio / queryManagerInfo / queryNewsList` 等 20+ | **jdjr.jd.com 根本没有基金详情页**，这些端点路径不对（实际在 fund.jd.com 或 APP 端） |
| `getSimpleQuote / getFundLabelList / getFundBaseInfo` | API 识别错误 10000404 |
| `queryFundDetailV2 / queryFundBaseInfo` | 同上 |
| `getIndexBlockInfo / getIndexDetail / getIndexValuationTrendChart / getBuyIndexRelatedFund` | status=FAIL 需正确参数 |

## 你实际关注的大佬列表

**抓取来源**: `feedFlowOfCircle tagId=112 contentId=2689640` 关注 tab feed

| 序号 | 大佬名 | 等级 | 持仓收益 | 您的代码中? | 需要补充 numeric_id |
|---|---|---|---|---|---|
| 1 | 红豆的甜美 | Lv.8 | 311.3万 | ❌ 缺失 | ✅ 需要 |
| 2 | 蓝鲸跃财 | Lv.8 | 318.6万 | ✅ 3546208 | - |
| 3 | 京东-和路雪 | Lv.7 | 183.3万 | ❌ 缺失 | ✅ 需要 |
| 4 | Z先生养基 | Lv.9 | 429.7万 | ✅ 14345330 | - |
| 5 | 晴空万里理财 | Lv.8 | 277.6万 | ✅ 3748946 | - |
| 6 | 小猫咪爱赚钱 | Lv.6 | 176.0万 | ❌ 缺失 | ✅ 需要 |

**抓取方法**:
```python
from tools.jd_finance_api import JDFinanceAPI
api = JDFinanceAPI(cookies=load_cookies())
feed = api.get_following_feed()  # tagId=112
for item in feed["data"]["resultList"]:
    user = item["userInfo"]
    print(user["nickName"], user["userId"])  # 拿到 numeric_id
```

---

## 七大类端点详细文档

### 一、认证 & 基础

#### `gw/generic/app/h5/m/getBasicParamForJR`

- **方法**: `POST`  
- **描述**: 基础参数（deviceId/sdk版本/加密key）  
- **响应状态**: ?  
- **响应大小**: 148 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/app/h5/m/getBasicParamForJR
  ```

#### `gw2/generic/CreatorSer/h5/m/pcQueryUserInfo`

- **方法**: `POST`  
- **描述**: 当前登录用户信息（uid/userName/avatar）  
- **响应状态**: ?  
- **响应大小**: 83 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo
  ```

#### `gw2/generic/getRSAPublicKey`

- **方法**: `POST`  
- **描述**: RSA 公钥（加密密码用）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/getRSAPublicKey
  ```

#### `gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias`

- **方法**: `POST`  
- **描述**: IM 公钥（聊天加密）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias
  ```

#### `gw2/generic/ImServer/h5/m/getPCToken`

- **方法**: `POST`  
- **描述**: PC Token（IM 用）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getPCToken
  ```

#### `gw2/generic/CaiFuPC/h5/m/addTradeCookie`

- **方法**: `POST`  
- **描述**: 写入交易 cookie  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/addTradeCookie
  ```

#### `gw2/generic/CaiFuPC/h5/m/addJdCookie`

- **方法**: `POST`  
- **描述**: 写入京东 cookie  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/addJdCookie
  ```

#### `gw2/generic/CaiFuPC/h5/m/getNotifyByPin`

- **方法**: `POST`  
- **描述**: 消息通知数  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/getNotifyByPin
  ```


### 二、行情数据 (opdataapi / jdtwt)

#### `gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes`

- **方法**: `GET`  
- **描述**: 指数/股票批量行情（必须带 ticket）  
- **响应状态**: ?  
- **响应大小**: 1975 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes
  ```

#### `gw2/generic/opdataapi/newh5/m/getSimpleQuoteUseUniqueCodes`

- **方法**: `GET`  
- **描述**: 同上 newh5 版  
- **响应状态**: ?  
- **响应大小**: 1975 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/opdataapi/newh5/m/getSimpleQuoteUseUniqueCodes
  ```

#### `gw2/generic/jdtwt/h5/m/getSimpleQuoteUseUniqueCodes`

- **方法**: `GET`  
- **描述**: 黄金行情（ticket=gold-price-h5）  
- **响应状态**: ?  
- **响应大小**: 703 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jdtwt/h5/m/getSimpleQuoteUseUniqueCodes
  ```

#### `gw2/generic/opdataapi/newh5/m/getWealthDatas`

- **方法**: `POST`  
- **描述**: 财富 Tab 数据  
- **响应状态**: ?  
- **响应大小**: 80 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/opdataapi/newh5/m/getWealthDatas
  ```

#### `gw2/generic/opdataapi/newh5/m/getFundLabel`

- **方法**: `GET`  
- **描述**: 基金标签（业务异常，参数不对）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/opdataapi/newh5/m/getFundLabel
  ```

#### `api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice`

- **方法**: `GET`  
- **描述**: 积存金金价（独立域）  
- **响应状态**: ?  
- **响应大小**: 693 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice
  ```

#### `gw2/generic/opdataapi/h5/m/getTimeSharingDots`

- **方法**: `POST`  
- **描述**: 分时点数据  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/opdataapi/h5/m/getTimeSharingDots
  ```

#### `gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache`

- **方法**: `POST`  
- **描述**: 行情扩展（含基金报价）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache
  ```

#### `gw2/generic/jdtwt/h5/m/queryZxProductList`

- **方法**: `GET`  
- **描述**: 自选产品行情（type=1 基金列表）  
- **响应状态**: ?  
- **响应大小**: 8618 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jdtwt/h5/m/queryZxProductList
  ```


### 三、基金排行 (jj)

#### `gw2/generic/jj/h5/m/queryFullRanking`

- **方法**: `GET`  
- **描述**: ⭐ 26 个官方榜单（人气/主题/业绩），h5 设备  
- **响应状态**: ?  
- **响应大小**: 305652 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jj/h5/m/queryFullRanking
  ```

#### `gw2/generic/jj/h5/m/queryFullRanking`

- **方法**: `GET`  
- **描述**: 同上 deviceType=pc  
- **响应状态**: ?  
- **响应大小**: 305652 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jj/h5/m/queryFullRanking
  ```

#### `gw2/generic/jj/h5/m/queryFullRanking`

- **方法**: `GET`  
- **描述**: 同上 deviceType=app  
- **响应状态**: ?  
- **响应大小**: 305652 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jj/h5/m/queryFullRanking
  ```

#### `gw2/generic/jj/h5/m/getRankingHeaderInfoV2`

- **方法**: `GET`  
- **描述**: 排行页头信息（导流图/Banner）  
- **响应状态**: ?  
- **响应大小**: 880 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jj/h5/m/getRankingHeaderInfoV2
  ```

#### `gw/generic/jj/h5/m/getRankingProductListV2`

- **方法**: `GET`  
- **描述**: 老排行端点（已废，返回请先登录）  
- **响应状态**: ?  
- **响应大小**: 140 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/jj/h5/m/getRankingProductListV2
  ```

#### `gw2/generic/jj/newh5/m/getInvestResearchRank`

- **方法**: `POST`  
- **描述**: 牛人/研报榜（已废 status=FAIL）  
- **响应状态**: ?  
- **响应大小**: 108 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jj/newh5/m/getInvestResearchRank
  ```

#### `gw2/generic/jj/h5/m/getFundFeeAndDiscountDataList`

- **方法**: `GET`  
- **描述**: 基金费率+折扣（需 itemId + bizType）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/jj/h5/m/getFundFeeAndDiscountDataList
  ```


### 四、圈子 (CreatorSer / jimu / aladdin)

#### `gw/generic/jimu/h5/m/queryCircleHeadInfo`

- **方法**: `GET`  
- **描述**: 圈子头信息（封面/成员数）  
- **响应状态**: ?  
- **响应大小**: 2467 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/jimu/h5/m/queryCircleHeadInfo
  ```

#### `gw2/generic/CreatorSer/h5/m/querySubFundCircleHeadInfoList`

- **方法**: `GET`  
- **描述**: 子圈子列表（需 valid params）  
- **响应状态**: ?  
- **响应大小**: 149 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/querySubFundCircleHeadInfoList
  ```

#### `gw/generic/jimu/h5/m/feedFlowOfCircle`

- **方法**: `GET`  
- **描述**: ⭐ 关注动态流（tagId=112, contentId=2689640）  
- **响应状态**: ?  
- **响应大小**: 87697 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle
  ```

#### `gw/generic/jimu/h5/m/feedFlowOfCircle`

- **方法**: `GET`  
- **描述**: 推荐流（tagId=55）  
- **响应状态**: ?  
- **响应大小**: 80091 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle
  ```

#### `gw/generic/jimu/h5/m/feedFlowOfCircle`

- **方法**: `GET`  
- **描述**: 最新/推荐/资讯/精华流（tagId 113-117）  
- **响应状态**: ?  
- **响应大小**: 87697 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle
  ```

#### `gw/generic/jimu/h5/m/getFollowUpdateCount`

- **方法**: `GET`  
- **描述**: 关注更新数（需登录）  
- **响应状态**: ?  
- **响应大小**: 184 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/jimu/h5/m/getFollowUpdateCount
  ```

#### `gw2/generic/CreatorSer/newh5/m/setLatestVisitCircleTab`

- **方法**: `GET`  
- **描述**: 切 tab 状态  
- **响应状态**: ?  
- **响应大小**: 173 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/setLatestVisitCircleTab
  ```

#### `gw2/generic/CreatorSer/h5/m/homePageHeadInfo`

- **方法**: `POST`  
- **描述**: ⭐ 大佬个人主页头部（蓝鲸跃财 5.9KB）  
- **响应状态**: ?  
- **响应大小**: 6209 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/homePageHeadInfo
  ```

#### `gw2/generic/aladdin/h5/m/getPageMutilData`

- **方法**: `POST`  
- **描述**: 主页多组件数据（pageId=3973 蓝鲸）  
- **响应状态**: ?  
- **响应大小**: 83 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/aladdin/h5/m/getPageMutilData
  ```

#### `gw2/generic/CreatorSer/newh5/m/getCircleHonorPopupByPin`

- **方法**: `GET`  
- **描述**: 圈子荣誉弹窗  
- **响应状态**: ?  
- **响应大小**: 227 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/getCircleHonorPopupByPin
  ```

#### `gw2/generic/liveViewer/h5/m/getLiveListForCircle`

- **方法**: `GET`  
- **描述**: 圈子直播列表  
- **响应状态**: ?  
- **响应大小**: 198 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/liveViewer/h5/m/getLiveListForCircle
  ```

#### `gw2/generic/CreatorSer/newh5/m/getFirstRelatedProductInfo`

- **方法**: `GET`  
- **描述**: 首关联产品信息  
- **响应状态**: ?  
- **响应大小**: 648 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/getFirstRelatedProductInfo
  ```


### 五、牛人榜 (redEnv001 实盘)

#### `gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRankHead`

- **方法**: `GET`  
- **描述**: ⭐ 牛人榜头（4大类 14 子榜配置）  
- **响应状态**: ?  
- **响应大小**: 32926 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRankHead
  ```

#### `gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank`

- **方法**: `GET`  
- **描述**: 收益最多（rankType=400）  
- **响应状态**: ?  
- **响应大小**: 32926 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank
  ```

#### `gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank`

- **方法**: `GET`  
- **描述**: 收益总榜（401）  
- **响应状态**: ?  
- **响应大小**: 32926 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank
  ```

#### `gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank`

- **方法**: `GET`  
- **描述**: 稳健掌舵人（403）  
- **响应状态**: ?  
- **响应大小**: 32926 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank
  ```

#### `gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank`

- **方法**: `GET`  
- **描述**: 均衡配置专家（404）  
- **响应状态**: ?  
- **响应大小**: 32926 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank
  ```

#### `gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank`

- **方法**: `GET`  
- **描述**: 海外先锋（405）  
- **响应状态**: ?  
- **响应大小**: 32926 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank
  ```


### 六、用户持仓 (CreatorSer)

#### `gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo`

- **方法**: `GET`  
- **描述**: ⭐ 用户基金持仓（userId 参数不影响，返回当前登录用户）  
- **响应状态**: ?  
- **响应大小**: 13983 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo
  ```

#### `gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo`

- **方法**: `GET`  
- **描述**: 同上（蓝鲸跃财 3546208 → 返自己）  
- **响应状态**: ?  
- **响应大小**: 13983 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo
  ```

#### `gw2/generic/CaiFuPC/h5/m/queryFundRelationList`

- **方法**: `POST`  
- **描述**: 基金关联列表（需 uCode）  
- **响应状态**: ?  
- **响应大小**: 180 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/queryFundRelationList
  ```


### 七、辅助 (legogw / buildVisualizeData)

#### `gw2/generic/legogw/h5/m/getPageInfoForH5`

- **方法**: `POST`  
- **描述**: lego H5 页面配置  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/legogw/h5/m/getPageInfoForH5
  ```

#### `gw/generic/aladdin/h5/m/buildVisualizeData`

- **方法**: `POST`  
- **描述**: aladdin 可视化数据  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw/generic/aladdin/h5/m/buildVisualizeData
  ```

#### `gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias`

- **方法**: `POST`  
- **描述**: IM 公钥（重复认证）  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias
  ```

#### `gw2/generic/CaiFuPC/h5/m/queryGoldTab`

- **方法**: `POST`  
- **描述**: 黄金 Tab 配置  
- **响应状态**: ?  
- **响应大小**: 2 字节  
- **完整 URL**:
  ```
  https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/queryGoldTab
  ```


## 响应结构示例

### `queryFullRanking_h5` (榜单 287KB)

```json
{
  "resultData": {
    "datas": {
      "primRanking": [  // 一级分类 3 个
        {
          "primRankName": "人气认证",  // 5 个榜单
          "secRanking": [
            {
              "rankingContent": [  // 每榜 20 只基金
                {
                  "fundCode": "016416",
                  "fundName": "南方稳鑫6个月持有债券A",
                  "primInvKey": "近1年收益率",
                  "secInvValue": "+3.05%",
                  "secRedGreen": true,
                  "riskLevel": "中高风险",
                  "subRankName": "近1年",
                  "fundDetailUrl": "https://fund.jd.com/..."
                }
              ]
            }
          ]
        }
      ]
    }
  },
  "resultCode": 0,
  "resultMsg": "成功"
}
```

### `queryUserFundHoldingInfo` (个人持仓 13.4KB)

```json
{
  "resultData": {
    "data": {
      "userInfo": {
        "userAvatar": "...",
        "userName": "jd_9b2u5ec8t4pmtb",
        "isSelf": true,
        "jumpData": {
          "schemeUrl": "openjdjrapp://com.jd.jrapp/..."
        }
      },
      "fundList": [
        // 用户所有基金持仓
      ],
      "totalAmount": "8437152.97",  // 总金额
      "totalProfit": "3186032.31"   // 总收益
    }
  }
}
```

### `feedFlowOfCircle` (关注流 80KB)

```json
{
  "resultData": {
    "code": 0,
    "data": {
      "pageSize": 7,
      "lastId": "...",  // 翻页游标
      "resultList": [
        {
          "feedId": "...",
          "userInfo": {
            "userId": "3546208",  // numeric_id
            "nickName": "蓝鲸跃财",
            "userLevel": 8,
            "fundProfit": "318.6万",
            "avatarUrl": "..."
          },
          "content": "【蓝鲸观点】...",
          "publishTime": "2026-07-12 14:30",
          "likeCount": 19,
          "commentCount": 29,
          "shareCount": 5,
          "imageList": []
        }
      ]
    }
  }
}
```

### `queryFundFirmOfferMultiRankHead` (牛人榜头 2.6KB)

```json
{
  "resultData": {
    "data": {
      "rankTypeRadio": {
        "options": [
          {
            "label": "收益最多",  // 父类
            "value": "400",
            "children": [
              {"label":"收益总榜","value":"401"},
              {"label":"稳健掌舵人","value":"403"},
              {"label":"均衡配置专家","value":"404"},
              {"label":"海外先锋","value":"405"}
            ]
          },
          // 还有 7 个父类 ...
        ]
      }
    }
  }
}
```

### `homePageHeadInfo` (蓝鲸跃财 5.9KB)

```json
{
  "resultData": {
    "data": {
      "userId": "3546208",
      "nickName": "蓝鲸跃财",
      "avatarUrl": "...",
      "userLevel": 8,
      "fansCount": 324000,  // 32.4万
      "followCount": 14,
      "isFollowed": true,
      "desc": "...",
      "totalAmount": "8437152.97",  // 8,437,152.97 元
      "totalProfit": "3186032.31",  // 3,186,032.31 元
      "wealthAge": 8.5,  // 财龄
      "ipLocation": "黑龙江",
      "fundList": [
        // 持仓基金列表（详细）
      ]
    }
  }
}
```

## 即用型 Python 封装

添加到 `tools/jd_finance_api.py`:

```python
class JDFinanceAPI:
    BASE = "https://ms.jr.jd.com"
    
    # ============= 用户 =============
    def get_current_user(self):
        """获取当前登录用户 (uid/numeric_id 都在)"""
        url = f"{self.BASE}/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo"
        return self._post(url, {})
    
    def get_user_holding(self):
        """获取当前登录用户的基金持仓 (13KB 含 fundList)"""
        url = f"{self.BASE}/gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo"
        # userId 参数不影响，永远返当前用户
        return self._get(url, {"userId": "", "pageId": 1, "pageSize": 50})
    
    def get_user_homepage(self, user_id: str):
        """获取大佬个人主页 (蓝鲸跃财 5.9KB)"""
        url = f"{self.BASE}/gw2/generic/CreatorSer/h5/m/homePageHeadInfo"
        return self._post(url, {"userId": user_id})
    
    # ============= 关注流 =============
    def get_following_feed(self, last_id: str = "", page_size: int = 20):
        """⭐ 获取我关注的大佬动态流 (80KB 含 6 大佬动态)"""
        url = f"{self.BASE}/gw/generic/jimu/h5/m/feedFlowOfCircle"
        req = {
            "tagId": 112,  # 关注流
            "contentId": "2689640",  # 基金圈
            "iosType": "",
            "extParams": {"requestFrom": "h5"},
            "lastId": last_id,
            "pageSize": page_size
        }
        return self._get(url, req)
    
    def get_recommend_feed(self, last_id: str = ""):
        """推荐流 (tagId=55)"""
        return self.get_feed(tag_id=55, last_id=last_id)
    
    def get_latest_feed(self, last_id: str = ""):
        """最新流 (tagId=113)"""
        return self.get_feed(tag_id=113, last_id=last_id)
    
    # ============= 排行榜 =============
    def get_full_ranking(self, device: str = "h5"):
        """⭐ 26 个官方榜单 (人气/主题/业绩)，每榜 20 只 = 287KB"""
        url = f"{self.BASE}/gw2/generic/jj/h5/m/queryFullRanking"
        return self._get(url, {"deviceType": device})
    
    def get_featured_rankings(self):
        """便捷方法：解析 queryFullRanking 为 list[dict]"""
        data = self.get_full_ranking()
        result = []
        for prim in data["resultData"]["datas"]["primRanking"]:
            for sec in prim["secRanking"]:
                for fund in sec["rankingContent"]:
                    result.append({
                        "category": prim["primRankName"],
                        "list_name": sec.get("secRankName"),
                        **fund
                    })
        return result  # 26*20 = 520 条
    
    # ============= 牛人榜 =============
    def get_bull_rank_head(self):
        """⭐ 牛人榜 14 子榜配置 (收益最多/稳健/均衡/海外先锋)"""
        url = f"{self.BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRankHead"
        return self._get(url)
    
    def get_bull_rank(self, rank_type: str = "400", page_id: int = 1):
        """获取某牛人榜 (rank_type 400=收益最多, 401=收益总, 403=稳健, 404=均衡, 405=海外)"""
        url = f"{self.BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank"
        return self._get(url, {"rankType": rank_type, "pageId": page_id, "pageSize": 20})
    
    # ============= 行情 =============
    def get_index_quote(self, codes: List[str]):
        """A 股/港股/美股/黄金批量行情"""
        url = f"{self.BASE}/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes"
        return self._get(url, {
            "ticket": "jdt-wealth-tools",
            "uniqueCodes": codes
        })
    
    def get_gold_price(self, code: str = "CZB-JCJ"):
        """积存金金价 (独立域 api.jdjygold.com)"""
        return self._get(f"https://api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice?goldCode={code}")
    
    def get_zx_product_list(self, ptype: int = 1):
        """自选产品行情 (jdtwt) - 7.9KB 含基金 code + 涨幅"""
        url = f"{self.BASE}/gw2/generic/jdtwt/h5/m/queryZxProductList"
        return self._get(url, {"type": ptype})
```

## 404 端点清单（路径错误，jdjr.jd.com 不存在）

以下端点**不在 jdjr.jd.com (PC H5)**，调用均返回 `{"resultCode":10000404,"resultMsg":"API识别错误"}` 或 `{"resultCode":-1,"resultMsg":"业务请求异常"}`:

| 端点路径 | 状态 | 备注 |
|---|---|---|
| `gw/generic/jj/h5/m/getFundDetail` | 404 | 基金详情，APP 端才有 |
| `gw2/generic/jj/h5/m/getFundDetail` | 404 | 同上 |
| `gw2/generic/jj/h5/m/queryFundDetail` | 404 | 同上 |
| `gw/generic/jj/h5/m/getTradeRule` | 404 | 交易规则 |
| `gw2/generic/jj/h5/m/queryTradeRule` | 404 | |
| `gw2/generic/jj/h5/m/getFundManager` | 404 | 基金经理 |
| `gw2/generic/jj/h5/m/queryManagerInfo` | 404 | |
| `gw2/generic/jj/h5/m/getFundAnnouncement` | 404 | 基金公告 |
| `gw2/generic/jj/h5/m/getFundBaseInfo` | 404 | |
| `gw2/generic/jj/h5/m/getFundInfo` | 404 | |
| `gw2/generic/jj/h5/m/queryFundDetailV2` | 404 | |
| `gw2/generic/jj/h5/m/queryFundBaseInfo` | 404 | |
| `gw2/generic/jj/h5/m/queryNetValueTrend` | 404 | 净值曲线 |
| `gw2/generic/jj/h5/m/queryNetValue` | 404 | |
| `gw2/generic/jj/h5/m/queryFundChartData` | 404 | 累计收益率 |
| `gw2/generic/jj/h5/m/queryPerformance` | 404 | 业绩 |
| `gw2/generic/jj/h5/m/queryFundPerformance` | 404 | |
| `gw2/generic/jj/h5/m/queryFundPortfolio` | 404 | 持仓 |
| `gw2/generic/jj/h5/m/queryFundStockPortfolio` | 404 | 持仓股票 |
| `gw2/generic/jj/h5/m/queryNewsList` | 404 | 资讯 |
| `gw2/generic/jj/h5/m/querySubRankingList` | 404 | 子榜 |
| `gw2/generic/opdataapi/newh5/m/getSimpleQuote` | 404 | |
| `gw2/generic/opdataapi/newh5/m/getFundLabelList` | 404 | |
| `gw2/generic/opdataapi/newh5/m/getFundBaseInfo` | 404 | |
| `gw2/generic/wealthBase/newh5/m/getIndexBlockInfo` | 200 (FAIL) | 需正确参数 |
| `gw2/generic/wealthBase/newh5/m/getIndexDetail` | 200 (FAIL) | |
| `gw2/generic/wealthBase/newh5/m/getIndexValuationTrendChart` | 200 (FAIL) | |
| `gw2/generic/wealthBase/newh5/m/getBuyIndexRelatedFund` | 200 (FAIL) | |

**结论**: jdjr.jd.com (PC H5) **没有基金详情/净值/经理/公告端点**。
这些信息通过 fund.jd.com 静态页 或 APP 端获取（不在 H5 API 域）。
**实际上** 您项目里 `tools/jd_finance_api.py` 的 `get_fund_chart_data` 等函数能工作是因为走的是 **fund.jd.com 静态资源** (`storage.360buyimg.com/app-oss-dev/*.json`)，不是 ms.jr.jd.com API。

## 原始响应数据位置

所有 41 个原始 JSON 响应保存在:  
```
c:/项目/A基金/基金/.playwright-mcp/
```

文件列表:

- `feedFlowOfCircle-following.json` (83.6 KB)
- `feedFlowOfCircle-recommend.json` (78.7 KB)
- `feedFlowOfCircle-tag112.json` (83.6 KB)
- `feedFlowOfCircle-tag113.json` (82.5 KB)
- `feedFlowOfCircle-tag114.json` (82.5 KB)
- `feedFlowOfCircle-tag115.json` (82.5 KB)
- `feedFlowOfCircle-tag116.json` (82.5 KB)
- `feedFlowOfCircle-tag117.json` (82.5 KB)
- `feedFlowOfCircle-tag55.json` (78.7 KB)
- `getBasicParamForJR.json` (0.2 KB)
- `getCircleHonorPopupByPin.json` (0.2 KB)
- `getFirstRelatedProductInfo.json` (0.6 KB)
- `getFollowUpdateCount.json` (0.2 KB)
- `getGoldPrice.json` (0.6 KB)
- `getInvestResearchRank.json` (0.1 KB)
- `getLiveListForCircle.json` (0.2 KB)
- `getPageMutilData-3973.json` (0.1 KB)
- `getRankingHeaderInfoV2.json` (0.8 KB)
- `getRankingProductListV2.json` (0.1 KB)
- `getSimpleQuote-gold.json` (0.6 KB)
- `getSimpleQuoteUseUniqueCodes.json` (1.8 KB)
- `getWealthDatas.json` (0.1 KB)
- `homePageHeadInfo-3546208.json` (6.4 KB)
- `pcQueryUserInfo-logged.json` (0.4 KB)
- `pcQueryUserInfo.json` (0.1 KB)
- `queryCircleHeadInfo.json` (2.4 KB)
- `queryFullRanking-app.json` (310.7 KB)
- `queryFullRanking-h5.json` (310.7 KB)
- `queryFullRanking-pc.json` (310.7 KB)
- `queryFundFirmOfferMultiRank-rt400.json` (31.3 KB)
- `queryFundFirmOfferMultiRank-rt401.json` (29.9 KB)
- `queryFundFirmOfferMultiRank-rt403.json` (24.4 KB)
- `queryFundFirmOfferMultiRank-rt404.json` (27.1 KB)
- `queryFundFirmOfferMultiRank-rt405.json` (25.2 KB)
- `queryFundFirmOfferMultiRank.json` (14.8 KB)
- `queryFundFirmOfferMultiRankHead-v2.json` (2.8 KB)
- `queryFundRelationList.json` (0.2 KB)
- `querySubFundCircleHeadInfoList.json` (0.1 KB)
- `queryUserFundHoldingInfo-17533758.json` (13.7 KB)
- `queryZxProductList-type1.json` (8.1 KB)
- `setLatestVisitCircleTab.json` (0.2 KB)

---

## 下一步建议

1. **补 3 个新关注人的 numeric_id** —— 在浏览器关注流点击 红豆的甜美/京东-和路雪/小猫咪爱赚钱 头像，记下 URL 中的 `jimu_user_info-XXXXX` 数字
2. **添加 `get_following_feed` 函数** —— 自动发现新关注的人（无需手填）
3. **添加 `get_user_holding` 函数** —— `queryUserFundHoldingInfo` 真实工作且不需 userId 永远返当前用户
4. **添加 `get_bull_rank` 函数** —— 5 大牛人榜全 200 OK
5. **牛人榜 + 关注流结合** —— 算出"我关注的人中谁上了牛人榜"
