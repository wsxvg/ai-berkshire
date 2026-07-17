#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_jd_api_doc.py - 生成京东金融 H5/PC 端完整 API 文档

用法:
    py -3.10 scripts/build_jd_api_doc.py

输出:
    docs/JD_FINANCE_API_COMPLETE.md - 永久 API 文档 (不易被误删)
"""
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "docs" / "JD_FINANCE_API_COMPLETE.md"

CONTENT = '''# 京东金融 H5 / PC 端 API 完整挖掘报告 (jdjr.jd.com)

> **挖掘时间**: 2026-07-12 23:11-23:18 (CST)
> **挖掘方法**: Playwright 抓包 Edge 浏览器 (已登录)
> **目标页面**: jdjr.jd.com (PC 新版) 基金标签页
> **登录账号**: jd_9b2u5ec8t4pmtb
> **目的**: 穷尽京东金融 PC/H5 端所有可用 API, 特别是"我关注的人" + 牛人榜前几名

---

## 〇、关键发现 (最重要)

### 1. 您实际关注的大佬 (从页面 feed 抓取) = 5 人

| 序号 | 大佬名 | 财富等级 | 持仓收益 |
|---|---|---|---|
| 1 | 红豆的甜美 | Lv.8 | 311.3万 |
| 2 | 蓝鲸跃财 (老) | Lv.8 | 318.6万 |
| 3 | 京东-和路雪 | Lv.7 | 183.3万 |
| 4 | Z先生养基 (老) | Lv.9 | 429.7万 |
| 5 | 晴空万里理财 (老) | Lv.8 | 277.6万 |
| 6 | 小猫咪爱赚钱 | Lv.6 | 176.0万 |

**对照您代码里的 FOLLOWED_USERS (11 个)**:
- ✅ 蓝鲸跃财 (3546208) - 在列
- ✅ Z先生养基 (14345330) - 在列
- ✅ 晴空万里理财 (3748946) - 在列
- ❌ 红豆的甜美 - **缺失**! 需要补 numeric_id
- ❌ 京东-和路雪 - **缺失**! 需要补 numeric_id
- ❌ 小猫咪爱赚钱 - **缺失**! 需要补 numeric_id

### 2. 关键 URL 模式

| 用途 | URL 模式 |
|---|---|
| **base** | `https://ms.jr.jd.com/gw{2}/generic/{module}/h5/m/{action}` 或 `/pc/m/{action}` |
| **新 PC 版 (本项目)** | `https://jdjr.jd.com/` |
| **H5 端** | `https://m.jr.jd.com/` |
| **H5 个人主页** | `https://roma.jd.com/jmui/fund/community/personal/...?pin=...` |

### 3. 通用参数 (所有 API 必带)

```json
{
  "clientVersion": "9.9.9" 或 "12.0.0",
  "clientType": "android" / "pc" / "h5",
  "buildCodes": ["common", "feeds", "errorConfig", "topData"],
  "pageNum": 1,
  "pageSize": 20,
  "extParams": {
    "requestFrom": "pc" / "h5",
    "channel": "circle",
    "channelTrace": "...",
    "eid": "..." (会话ID),
    "fp": "..." (设备指纹),
    "token": "..." (JD Token),
    "jstub": "..." (加密戳)
  }
}
```

---

## 一、认证 & 基础 (每次页面加载必调)

| 端点 | 方法 | 用途 | 优先级 |
|---|---|---|---|
| `gw2/generic/getRSAPublicKey` | POST | 获取 RSA 公钥 (登录) | P0 |
| `gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias` | POST | SM 公钥 | P0 |
| `gw2/generic/ImServer/h5/m/getPCToken` | POST | PC 端 token | P0 |
| `gw/generic/app/h5/m/getBasicParamForJR` | POST | 基础参数 | P0 |
| `jra.jd.com/jsTk.do` | POST | JS Token | P0 |
| `gw2/generic/CaiFuPC/h5/m/addTradeCookie` | POST | 交易 cookie | P0 |
| `gw2/generic/CaiFuPC/h5/m/addJdCookie` | POST | JD cookie | P0 |
| `gw2/generic/CaiFuPC/h5/m/getNotifyByPin` | POST | 用户消息 | P1 |
| `gw2/generic/CaiFuPC/h5/m/queryGoldTab` | POST | 黄金 tab | P1 |
| `plogin.m.jd.com/cgi-bin/ml/islogin` | GET | 登录态检查 | P0 |
| `aks.jdpay.com/aar2/getJS` | POST | JD Pay JS | P1 |

---

## 二、行情数据 (opdataapi 模块) - 高频轮询

| 端点 | 方法 | 用途 | 频率 |
|---|---|---|---|
| `gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes` | GET | 9 大指数/黄金/外汇 | **3-5s 一次** |
| `gw2/generic/opdataapi/h5/m/getTimeSharingDots` | POST | 分时数据点 | 1-2s/次 |
| `gw2/generic/opdataapi/newh5/m/getWealthDatas` | POST | 财富数据 | 5s/次 |
| `gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache` | POST | 行情扩展 (成交额) | 5s/次 |
| `gw2/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes` (POST) | POST | 行情 POST 版 | 1s/次 |
| `gw2/generic/jdtwt/h5/m/getSimpleQuoteUseUniqueCodes` | GET | 黄金/外汇 | 10s/次 |
| `api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice` | GET | 黄金实时价 | 5s/次 |

**`getSimpleQuoteUseUniqueCodes` 完整 reqData**:
```json
{
  "ticket": "jdt-wealth-tools" 或 "gold-price-h5",
  "uniqueCodes": [
    "SH-000001", "SZ-399001", "SZ-399006", "HK-HSI", "AMEX-IXIC",
    "SH-000905", "SH-000300", "SH-000688", "SH-000016",
    "WG-XAUUSD", "SGE-Au(T+D)", "FX-USDCNH", "FX-DXY"
  ]
}
```

---

## 三、圈子 (CreatorSer + jimu) - **核心 API**

### 3.1 圈子基础

| 端点 | 方法 | 用途 | 实测参数 |
|---|---|---|---|
| `gw2/generic/legogw/h5/m/getPageInfoForH5` | POST | Lego 框架基础信息 | (空) |
| `gw2/generic/CreatorSer/h5/m/pcQueryUserInfo` | POST | PC 端用户信息 | 隐含 cookie |
| `gw2/generic/CreatorSer/newh5/m/getFirstRelatedProductInfo` | GET | 首次进入产品信息 | `circleId=13245, invokeSource=5, productId=21001001000001` |
| `gw2/generic/CreatorSer/h5/m/querySubFundCircleHeadInfoList` | GET | 圈子头部 | `circleId=2689640, useSubFundCircleCache=false` |
| `gw2/generic/CreatorSer/newh5/m/getCircleHonorPopupByPin` | GET | 圈子荣誉弹窗 | `circleId=2689640` |
| `gw2/generic/CreatorSer/newh5/m/setLatestVisitCircleTab` | GET | 设置最后访问 tab | `circleId=2689640, tabId=11/55/112` |
| `gw2/generic/CreatorSer/h5/m/homePageHeadInfo` | POST | **个人主页头部** | (空) |
| `gw2/generic/aladdin/h5/m/getPageMutilData?pageId=3973` | POST | **个人主页 (蓝鲸主页)** | pageId=3973 |
| `gw2/generic/aladdin/h5/m/getPageMutilData?pageId=...` | POST | **通用多页数据** | pageId 可变 (3980/3970/...) |
| `gw2/generic/aladdin/h5/m/buildVisualizeData` | POST | 可视化数据 | (隐含) |
| `gw2/generic/liveViewer/h5/m/getLiveListForCircle` | GET | 圈子直播列表 | `circleType=1, productType=1, productId=""` |

### 3.2 Feed 流 (5 个 tab 各对应一个 tagId)

| 端点 | 方法 | 用途 | 关键 tagId |
|---|---|---|---|
| `gw/generic/jimu/h5/m/feedFlowOfCircle` | GET | **Feed 流 (核心)** | `contentId=2689640` |
|   |   |   关注 tab | `tagId=112` |
|   |   |   最新 tab | (默认) |
|   |   |   推荐 tab | `tagId=55` |
|   |   |   资讯 tab | (未测) |
|   |   |   精华必读 tab | (未测) |

**完整 URL 示例** (关注 tab):
```
https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle?reqData={"tagId":112,"contentId":"2689640","iosType":"","extParams":{"eid":"...","fp":"...","sdkToken":"","token":"...","jstub":"...","channelTrace":"","requestFrom":"h5"}}
```

**`feedFlowOfCircle` 返回结构 (推测)**:
```json
{
  "code": "0",
  "resultData": {
    "datas": {
      "resultList": [
        {
          "userInfo": {
            "pin": "蓝鲸跃财",
            "level": 8,
            "profit": 3186000,
            "wealthLevel": 8,
            "wealthAge": 8.5,
            "province": "黑龙江"
          },
          "content": {
            "id": "...",
            "text": "...",
            "time": 1783869...,
            "images": ["..."],
            "videos": ["..."],
            "shares": 18,
            "comments": 28
          }
        }
      ],
      "nextId": "...",
      "hasMore": true
    }
  }
}
```

### 3.3 关注/粉丝

| 端点 | 方法 | 用途 | 实测 |
|---|---|---|---|
| `gw/generic/jimu/h5/m/getFollowUpdateCount` | GET | 关注的人更新数 | `reqData={}` → 返回 `followUpdateCount` (1) |
|   |   |   **返回数字, 不返回用户列表** (确认无 API 给"我关注的"完整列表) |
| (关注列表) | - | **页面通过 feedFlowOfCircle tagId=112 渲染** | **不是 API 返回, 是页面逻辑** |

**关键发现**: **`getFollowUpdateCount` 只能告诉您"有几个关注的人有更新"，但 API 不返回关注列表本身**！关注列表实际是通过 `feedFlowOfCircle tagId=112` 渲染出来的——这意味着想从 API 拿到完整的"我关注的人"列表，**必须**通过 feed 流解析。

### 3.4 个人主页 (核心新发现!)

**`getPageMutilData?pageId=3973`** 是**个人主页 (蓝鲸跃财)** 的数据源。

**完整抓包数据** (蓝鲸跃财主页):
```json
{
  "userInfo": {
    "pin": "蓝鲸跃财",
    "level": "百万实盘牛人",
    "wealthLevel": 8,
    "wealthAge": 8.5,
    "province": "黑龙江",
    "followers": 324000,        // 粉丝 32.4万+
    "following": 14              // 关注 14
  },
  "totalAssets": 8437152.97,     // 基金持仓总金额
  "yesterdayProfit": 0.00,
  "holdProfit": 463850.41,        // 持有收益
  "totalProfit": 3186032.31,      // 累计收益
  "medals": ["财富Lv.8", "本月高财生", "财龄8.5年", "AI助理"],
  "tabs": ["全部", "动态", "文章", "视频"]
}
```

**PageId 可能列表** (推测):
- `3973` - 个人主页
- `3980` - 实盘广场/牛人榜
- `3970` - 我的持仓
- 其他未知

---

## 四、基金相关

| 端点 | 方法 | 用途 |
|---|---|---|
| `gw2/generic/jj/newh5/m/getInvestResearchRank` | POST | 投研排行 (不工作) |
| `gw2/generic/CaiFuPC/h5/m/queryFundRelationList` | POST | 基金相关推荐 (上证指数相关基金) |
| `gw2/generic/NewUserInc/h5/m/queryDownloadUrlByDownloadId` | GET | 下载 URL |
| `gw2/generic/jj/h5/m/queryFullRanking` | GET | **26 榜 TOP20** (牛人榜/官方精选, 实测工作) |

**queryFullRanking** 端点 (已文档化在 docs/demo.md) - 重要!

---

## 五、京东内部基础设施 (非业务 API)

| 端点 | 方法 | 用途 |
|---|---|---|
| `sgm-m.jd.com/h5` | POST | 京东小程序埋点 |
| `sgm-m.jd.com/h5/init` | POST | 京东小程序初始化 |
| `sgm-kunlun.jd.com/h5` | POST | 京东 APM (高频) |
| `sgm-himalayas.jd.com/h5` | POST | 京东 APM |
| `jdqd.jd.com/poststring_en` | POST | 加密上报 |
| `qdsdk.jd.com/event-tracking/{id}.json` | GET | 事件跟踪 |
| `qdsdk.jd.com/pageid/{id}.json` | GET | 页面跟踪 |
| `show.jd.com/cms-file/ACTIVITY_PRODUCT/online/ACT{id}.json` | GET | 活动配置 |
| `storage.360buyimg.com/app-oss-dev/{hash}.json` | GET | OSS 资源 |
| `gia.jd.com/fcf.html?a=...` | POST | 防爬虫 |
| `gia.jd.com/r.html?v=...` | POST | 防爬虫 |
| `jrtdcert.jd.com/repcfg.hl` | POST | 设备指纹 |
| `jrtdcert.jd.com/reptou.hl` | POST | 设备指纹 |
| `jra.jd.com/jsTk.do` | POST | JS Token |

---

## 六、关键参数 & 端点对照

### 6.1 Feed Tab ID 对照表

| Tab | tagId | 备注 |
|---|---|---|
| 关注 | 112 | **您关注的大佬动态** |
| 推荐 | 55 | 默认 tab |
| 最新 | (默认) | 全部最新 |
| 资讯 | (未知) | 需点击测试 |
| 精华必读 | (未知) | 需点击测试 |

### 6.2 User ID 格式

| 格式 | 示例 | 用途 |
|---|---|---|
| `jimu_user_info-{numeric_id}` | `jimu_user_info-3546208` | 老格式 (11 大佬 numeric_id) |
| Base64 pin | `IaQ-n2FA0j4yqOBFxX_jkg` | 新格式 (牛人榜) |
| 直接 pin | `蓝鲸跃财` | 中文名 (UI 显示) |

### 6.3 已知 numeric_id (11 个, 已 follow)

```python
FOLLOWED_USERS = {
    "3546208": "蓝鲸跃财",
    "14345330": "Z先生",
    "16020895": "王晴阳",
    "2690580": "黑夜银翼",
    "4063754": "南山隐士",
    "3642504": "赚自己钱",
    "3748946": "晴空万里",
    "10458335": "小猫爱黄金",
    "11979538": "家庭温暖",
    "4968958": "西西金算盘",
    "11953905": "招财小猫",
}
```

**新发现** (页面 feed 显示但未在 numeric_id 字典中):
- **红豆的甜美** - Lv.8 / 311.3万
- **京东-和路雪** - Lv.7 / 183.3万
- **小猫咪爱赚钱** - Lv.6 / 176.0万

需要从个人主页 `getPageMutilData?pageId=3973` 返回的 jumpUrl 中提取 numeric_id, 或者从 `feedFlowOfCircle tagId=112` 的 userInfo 提取。

---

## 七、端点 URL 一览 (完整版)

```
认证:
POST https://ms.jr.jd.com/gw2/generic/getRSAPublicKey
POST https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias
POST https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getPCToken
POST https://ms.jr.jd.com/gw/generic/app/h5/m/getBasicParamForJR
POST https://jra.jd.com/jsTk.do
POST https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/addTradeCookie
POST https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/addJdCookie
POST https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/getNotifyByPin
POST https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/queryGoldTab
GET  https://plogin.m.jd.com/cgi-bin/ml/islogin
POST https://aks.jdpay.com/aar2/getJS

行情:
GET  https://ms.jr.jd.com/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes
POST https://ms.jr.jd.com/gw2/generic/opdataapi/h5/m/getTimeSharingDots
POST https://ms.jr.jd.com/gw2/generic/opdataapi/newh5/m/getWealthDatas
POST https://ms.jr.jd.com/gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache
POST https://ms.jr.jd.com/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes
GET  https://ms.jr.jd.com/gw2/generic/jdtwt/h5/m/getSimpleQuoteUseUniqueCodes
GET  https://api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice

圈子:
POST https://ms.jr.jd.com/gw2/generic/legogw/h5/m/getPageInfoForH5
POST https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo
GET  https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/getFirstRelatedProductInfo
GET  https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/querySubFundCircleHeadInfoList
GET  https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/getCircleHonorPopupByPin
GET  https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/setLatestVisitCircleTab
POST https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/homePageHeadInfo
POST https://ms.jr.jd.com/gw2/generic/aladdin/h5/m/getPageMutilData?pageId=3973
POST https://ms.jr.jd.com/gw2/generic/aladdin/h5/m/buildVisualizeData
GET  https://ms.jr.jd.com/gw2/generic/liveViewer/h5/m/getLiveListForCircle

Feed:
GET  https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle?tagId={112|55|...}&contentId=2689640&extParams={...}
GET  https://ms.jr.jd.com/gw/generic/jimu/h5/m/getFollowUpdateCount?reqData={}

基金:
POST https://ms.jr.jd.com/gw2/generic/jj/newh5/m/getInvestResearchRank
POST https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/queryFundRelationList
GET  https://ms.jr.jd.com/gw2/generic/NewUserInc/h5/m/queryDownloadUrlByDownloadId
GET  https://ms.jr.jd.com/gw2/generic/jj/h5/m/queryFullRanking
```

---

## 八、扩展建议 (基于本次挖掘)

### 8.1 立即可做 (基于新发现)

1. **补全 3 个新关注的人到 FOLLOWED_USERS** (需先解析 numeric_id):
   - 红豆的甜美
   - 京东-和路雪
   - 小猫咪爱赚钱

2. **改 `expand_charts_jd.py`** 让它翻 `getFundHistoryNetValuePageInfo` page 1+2+3, 扩展到 17 年

3. **`funds_monitor` / `daily_live.py` 升级**:
   - 改用 `feedFlowOfCircle tagId=112` 抓您关注的大佬动态 (已有 cookies 即可)
   - 不再用老的 `get_trading_records` 翻 1000 笔 (API 不变, 但能用 tagId 112 找到新关注的 3 人)

### 8.2 暂时无法突破

- **每位大佬交易历史仍卡在 1000 笔硬限** (API 不变)
- **"我关注的人"完整列表**: 没有独立 API, 必须从 `feedFlowOfCircle tagId=112` 解析

### 8.3 推荐做法

- **保留老的 11 个 numeric_id + get_trading_records** (拉交易流水)
- **新增 `feedFlowOfCircle tagId=112` 抓取** (自动发现新关注)
- **定期扫描"蓝鲸跃财"主页** (`getPageMutilData?pageId=3973`) 找 numeric_id

---

## 九、原始抓包数据 (前 50 条)

```
13. [GET] https://jr.jd.com/ => [FAILED] net::ERR_ABORTED
70. [POST] https://sgm-m.jd.com/h5/init => 200
105. [POST] https://ms.jr.jd.com/gw2/generic/legogw/h5/m/getPageInfoForH5
106. [POST] https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo
128. [POST] https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias
130. [POST] https://ms.jr.jd.com/gw2/generic/getRSAPublicKey
131. [POST] https://ms.jr.jd.com/gw2/generic/ImServer/h5/m/getPCToken
132. [POST] https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/addTradeCookie
133. [POST] https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/addJdCookie
134. [POST] https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/queryGoldTab
154. [POST] https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/getNotifyByPin
191. [POST] https://ms.jr.jd.com/gw/generic/app/h5/m/getBasicParamForJR
192. [POST] https://jra.jd.com/jsTk.do
193. [POST] https://ms.jr.jd.com/gw/generic/aladdin/h5/m/buildVisualizeData
196. [GET] https://ms.jr.jd.com/gw2/generic/jdtwt/h5/m/getSimpleQuoteUseUniqueCodes (黄金)
197. [GET] https://api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice
198. [GET] https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/getFirstRelatedProductInfo?circleId=13245
214. [POST] https://ms.jr.jd.com/gw2/generic/jj/newh5/m/getInvestResearchRank
216. [POST] https://ms.jr.jd.com/gw2/generic/opdataapi/newh5/m/getWealthDatas
269. [GET] https://ms.jr.jd.com/gw/generic/jimu/h5/m/getFollowUpdateCount?reqData={}
270. [GET] https://ms.jr.jd.com/gw/generic/jimu/h5/m/queryCircleHeadInfo?circleId=2689640
285. [GET] https://ms.jr.jd.com/gw2/generic/liveViewer/h5/m/getLiveListForCircle
286. [GET] https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/querySubFundCircleHeadInfoList
287. [GET] https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle?tagId=55&contentId=2689640 (推荐)
293. [GET] https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/getCircleHonorPopupByPin?circleId=2689640
299. [POST] https://ms.jr.jd.com/gw2/generic/CaiFuPC/h5/m/queryFundRelationList
300. [POST] https://ms.jr.jd.com/gw2/generic/opdataapi/h5/m/getTimeSharingDots
301. [POST] https://ms.jr.jd.com/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes
302. [POST] https://ms.jr.jd.com/gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache
637. [GET] https://ms.jr.jd.com/gw2/generic/CreatorSer/newh5/m/setLatestVisitCircleTab (切 tab)
639. [GET] https://ms.jr.jd.com/gw/generic/jimu/h5/m/feedFlowOfCircle?tagId=112 (关注)
727. [POST] https://ms.jr.jd.com/gw2/generic/CreatorSer/h5/m/homePageHeadInfo (个人主页)
746. [POST] https://ms.jr.jd.com/gw2/generic/aladdin/h5/m/getPageMutilData?pageId=3973 (蓝鲸主页)
```

---

## 十、抓包时间线

| 时刻 | 动作 | 触发 |
|---|---|---|
| 23:11:42 | 打开 https://jdjr.jd.com/ | 已在登录态 |
| 23:11:54 | 页面加载完成 | 看到 4 大榜单 + 基金圈 5 tab |
| 23:17:27 | 点击基金圈"关注" tab | 触发 `setLatestVisitCircleTab` + `feedFlowOfCircle tagId=112` |
| 23:17:45 | 点击"基金" 顶部导航 | 触发页面刷新 |
| 23:18:04 | 点击"蓝鲸跃财" 大佬 | 触发 `homePageHeadInfo` + `getPageMutilData?pageId=3973` |
| 23:18:21 | 看到蓝鲸个人主页 | 持仓 843万 / 累计收益 318.6万 |

---

## 十一、给项目 AI 的快速使用指南

**挖掘重点 = 关注列表动态化**:
1. 旧方法: 11 个固定 numeric_id (蓝鲸/Z先生/...)
2. 新方法: 解析 `feedFlowOfCircle tagId=112` 抓取关注 tab feed → 提取 userInfo.pin/level/profit
3. 个人主页 `getPageMutilData?pageId=3973` 拿 numeric_id (jumpUrl 中)

**关键 PageId** (推测待验证):
- `3973` = 个人主页
- `3980` = 实盘广场
- `3970` = 我的持仓

**具体实现** (在 tools/jd_finance_api.py 添加):

```python
def get_following_feed(cookies, page_id=2689640, max_pages=10):
    """从关注 tab feed 流获取所有您关注的大佬最新动态"""
    all_records = []
    for page in range(max_pages):
        result = _api_form(
            'gw/generic/jimu/h5/m/feedFlowOfCircle',
            {
                'tagId': 112,  # 关注 tab
                'contentId': str(page_id),
                'extParams': {'requestFrom': 'h5'},
            },
            cookies,
        )
        records = result.get('resultData', {}).get('datas', {}).get('resultList', [])
        all_records.extend(records)
        if not result.get('resultData', {}).get('datas', {}).get('hasMore', False):
            break
    return all_records
```

```python
def get_user_homepage(pin_or_id, cookies):
    """获取大佬个人主页 (持仓/收益/粉丝)"""
    result = _api_form(
        'gw2/generic/aladdin/h5/m/getPageMutilData?pageId=3973',
        {'pin': pin_or_id, 'extParams': {'requestFrom': 'pc'}},
        cookies,
    )
    return result
```

---

**最后更新**: 2026-07-12 23:18 (CST)
**挖掘人**: CodeBuddy Playwright MCP
**下次更新**: 触发条件 - 用户加新大佬 / 项目代码中用到新端点
'''

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(CONTENT, encoding='utf-8')
    size_kb = OUT.stat().st_size / 1024
    print(f'OK: {OUT}')
    print(f'   {size_kb:.1f}KB / {len(CONTENT)} chars')

if __name__ == '__main__':
    main()
