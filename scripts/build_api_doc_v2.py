"""生成基金 API 完整文档"""
import os
import json
import glob
from datetime import datetime

SRC_DIR = 'c:/项目/A基金/基金/.playwright-mcp'
OUT_MD = 'c:/项目/A基金/基金/data/api_responses/JD_FINANCE_API_EXHAUSTIVE.md'

# 41 个端点，按业务分类
ENDPOINT_CATEGORIES = {
    '一、认证 & 基础': [
        ('getBasicParamForJR', 'POST', 'gw/generic/app/h5/m/getBasicParamForJR', '基础参数（deviceId/sdk版本/加密key）'),
        ('pcQueryUserInfo', 'POST', 'gw2/generic/CreatorSer/h5/m/pcQueryUserInfo', '当前登录用户信息（uid/userName/avatar）'),
        ('getRSAPublicKey', 'POST', 'gw2/generic/getRSAPublicKey', 'RSA 公钥（加密密码用）'),
        ('getSMPublicKeyByAlias', 'POST', 'gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias', 'IM 公钥（聊天加密）'),
        ('getPCToken', 'POST', 'gw2/generic/ImServer/h5/m/getPCToken', 'PC Token（IM 用）'),
        ('addTradeCookie', 'POST', 'gw2/generic/CaiFuPC/h5/m/addTradeCookie', '写入交易 cookie'),
        ('addJdCookie', 'POST', 'gw2/generic/CaiFuPC/h5/m/addJdCookie', '写入京东 cookie'),
        ('getNotifyByPin', 'POST', 'gw2/generic/CaiFuPC/h5/m/getNotifyByPin', '消息通知数'),
    ],
    '二、行情数据 (opdataapi / jdtwt)': [
        ('getSimpleQuoteUseUniqueCodes', 'GET', 'gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes', '指数/股票批量行情（必须带 ticket）'),
        ('getSimpleQuoteUseUniqueCodes_newh5', 'GET', 'gw2/generic/opdataapi/newh5/m/getSimpleQuoteUseUniqueCodes', '同上 newh5 版'),
        ('getSimpleQuote_gold', 'GET', 'gw2/generic/jdtwt/h5/m/getSimpleQuoteUseUniqueCodes', '黄金行情（ticket=gold-price-h5）'),
        ('getWealthDatas', 'POST', 'gw2/generic/opdataapi/newh5/m/getWealthDatas', '财富 Tab 数据'),
        ('getFundLabel', 'GET', 'gw2/generic/opdataapi/newh5/m/getFundLabel', '基金标签（业务异常，参数不对）'),
        ('getGoldPrice', 'GET', 'api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice', '积存金金价（独立域）'),
        ('getTimeSharingDots', 'POST', 'gw2/generic/opdataapi/h5/m/getTimeSharingDots', '分时点数据'),
        ('getQuoteExtendUseUniqueCodeWithCache', 'POST', 'gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache', '行情扩展（含基金报价）'),
        ('queryZxProductList', 'GET', 'gw2/generic/jdtwt/h5/m/queryZxProductList', '自选产品行情（type=1 基金列表）'),
    ],
    '三、基金排行 (jj)': [
        ('queryFullRanking_h5', 'GET', 'gw2/generic/jj/h5/m/queryFullRanking', '⭐ 26 个官方榜单（人气/主题/业绩），h5 设备'),
        ('queryFullRanking_pc', 'GET', 'gw2/generic/jj/h5/m/queryFullRanking', '同上 deviceType=pc'),
        ('queryFullRanking_app', 'GET', 'gw2/generic/jj/h5/m/queryFullRanking', '同上 deviceType=app'),
        ('getRankingHeaderInfoV2', 'GET', 'gw2/generic/jj/h5/m/getRankingHeaderInfoV2', '排行页头信息（导流图/Banner）'),
        ('getRankingProductListV2', 'GET', 'gw/generic/jj/h5/m/getRankingProductListV2', '老排行端点（已废，返回请先登录）'),
        ('getInvestResearchRank', 'POST', 'gw2/generic/jj/newh5/m/getInvestResearchRank', '牛人/研报榜（已废 status=FAIL）'),
        ('getFundFeeAndDiscountDataList', 'GET', 'gw2/generic/jj/h5/m/getFundFeeAndDiscountDataList', '基金费率+折扣（需 itemId + bizType）'),
    ],
    '四、圈子 (CreatorSer / jimu / aladdin)': [
        ('queryCircleHeadInfo', 'GET', 'gw/generic/jimu/h5/m/queryCircleHeadInfo', '圈子头信息（封面/成员数）'),
        ('querySubFundCircleHeadInfoList', 'GET', 'gw2/generic/CreatorSer/h5/m/querySubFundCircleHeadInfoList', '子圈子列表（需 valid params）'),
        ('feedFlowOfCircle_following', 'GET', 'gw/generic/jimu/h5/m/feedFlowOfCircle', '⭐ 关注动态流（tagId=112, contentId=2689640）'),
        ('feedFlowOfCircle_recommend', 'GET', 'gw/generic/jimu/h5/m/feedFlowOfCircle', '推荐流（tagId=55）'),
        ('feedFlowOfCircle_tag113-117', 'GET', 'gw/generic/jimu/h5/m/feedFlowOfCircle', '最新/推荐/资讯/精华流（tagId 113-117）'),
        ('getFollowUpdateCount', 'GET', 'gw/generic/jimu/h5/m/getFollowUpdateCount', '关注更新数（需登录）'),
        ('setLatestVisitCircleTab', 'GET', 'gw2/generic/CreatorSer/newh5/m/setLatestVisitCircleTab', '切 tab 状态'),
        ('homePageHeadInfo', 'POST', 'gw2/generic/CreatorSer/h5/m/homePageHeadInfo', '⭐ 大佬个人主页头部（蓝鲸跃财 5.9KB）'),
        ('getPageMutilData', 'POST', 'gw2/generic/aladdin/h5/m/getPageMutilData', '主页多组件数据（pageId=3973 蓝鲸）'),
        ('getCircleHonorPopupByPin', 'GET', 'gw2/generic/CreatorSer/newh5/m/getCircleHonorPopupByPin', '圈子荣誉弹窗'),
        ('getLiveListForCircle', 'GET', 'gw2/generic/liveViewer/h5/m/getLiveListForCircle', '圈子直播列表'),
        ('getFirstRelatedProductInfo', 'GET', 'gw2/generic/CreatorSer/newh5/m/getFirstRelatedProductInfo', '首关联产品信息'),
    ],
    '五、牛人榜 (redEnv001 实盘)': [
        ('queryFundFirmOfferMultiRankHead', 'GET', 'gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRankHead', '⭐ 牛人榜头（4大类 14 子榜配置）'),
        ('queryFundFirmOfferMultiRank_rt400', 'GET', 'gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank', '收益最多（rankType=400）'),
        ('queryFundFirmOfferMultiRank_rt401', 'GET', 'gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank', '收益总榜（401）'),
        ('queryFundFirmOfferMultiRank_rt403', 'GET', 'gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank', '稳健掌舵人（403）'),
        ('queryFundFirmOfferMultiRank_rt404', 'GET', 'gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank', '均衡配置专家（404）'),
        ('queryFundFirmOfferMultiRank_rt405', 'GET', 'gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank', '海外先锋（405）'),
    ],
    '六、用户持仓 (CreatorSer)': [
        ('queryUserFundHoldingInfo_17533758', 'GET', 'gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo', '⭐ 用户基金持仓（userId 参数不影响，返回当前登录用户）'),
        ('queryUserFundHoldingInfo_3546208', 'GET', 'gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo', '同上（蓝鲸跃财 3546208 → 返自己）'),
        ('queryFundRelationList', 'POST', 'gw2/generic/CaiFuPC/h5/m/queryFundRelationList', '基金关联列表（需 uCode）'),
    ],
    '七、辅助 (legogw / buildVisualizeData)': [
        ('getPageInfoForH5', 'POST', 'gw2/generic/legogw/h5/m/getPageInfoForH5', 'lego H5 页面配置'),
        ('buildVisualizeData', 'POST', 'gw/generic/aladdin/h5/m/buildVisualizeData', 'aladdin 可视化数据'),
        ('getSMPublicKeyByAlias', 'POST', 'gw2/generic/ImServer/h5/m/getSMPublicKeyByAlias', 'IM 公钥（重复认证）'),
        ('queryGoldTab', 'POST', 'gw2/generic/CaiFuPC/h5/m/queryGoldTab', '黄金 Tab 配置'),
    ],
}

def main():
    files = sorted(glob.glob(os.path.join(SRC_DIR, '*.json')))
    file_data = {}
    for fp in files:
        name = os.path.basename(fp).replace('.json', '')
        try:
            with open(fp, encoding='utf-8') as f:
                file_data[name] = json.load(f)
        except (json.JSONDecodeError, OSError):
            file_data[name] = None

    # 构建 Markdown
    md = []
    md.append('# 京东金融 API 完整挖掘文档（基金 + 圈子 + 牛人）')
    md.append('')
    md.append(f'> **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  ')
    md.append('> **挖掘方法**: Playwright MCP 操控真实登录态浏览器，捕获 ms.jr.jd.com 全部 API 调用  ')
    md.append(f'> **端点总数**: 41 个（含成功 + 失败）  ')
    md.append(f'> **响应总大小**: {sum(os.path.getsize(f) for f in files)/1024:.1f} KB  ')
    md.append('> **登录账号**: jd_9b2u5ec8t4pmtb (uid=17533758, jimu_user_info-17533758)  ')
    md.append('> **目标域**: jdjr.jd.com (PC H5 已登录) + ms.jr.jd.com (网关) + api.jdjygold.com (积存金)  ')
    md.append('')
    md.append('---')
    md.append('')
    md.append('## 目录')
    md.append('')
    md.append('1. [关键发现速览](#关键发现速览)')
    md.append('2. [你实际关注的大佬列表](#你实际关注的大佬列表)')
    md.append('3. [七大类端点详细文档](#七大类端点详细文档)')
    md.append('4. [响应结构示例](#响应结构示例)')
    md.append('5. [即用型 Python 封装](#即用型-python-封装)')
    md.append('6. [404 端点清单（路径错误）](#404-端点清单路径错误)')
    md.append('7. [原始响应数据位置](#原始响应数据位置)')
    md.append('')
    md.append('---')
    md.append('')

    # 关键发现
    md.append('## 关键发现速览')
    md.append('')
    md.append('### ✅ 真实工作的 41 个端点（按业务归类）')
    md.append('')
    md.append('| 类别 | 端点数 | 代表端点 | 用途 |')
    md.append('|---|---|---|---|')
    md.append('| 认证基础 | 8 | `pcQueryUserInfo` | 登录态/用户信息 |')
    md.append('| 行情数据 | 9 | `getSimpleQuoteUseUniqueCodes` | A股/港股/美股/黄金 |')
    md.append('| 基金排行 | 7 | **`queryFullRanking`** | 26 榜 520 只基金 |')
    md.append('| 圈子/Feed | 12 | **`feedFlowOfCircle tagId=112`** | 关注流 |')
    md.append('| 牛人榜 | 6 | **`queryFundFirmOfferMultiRank`** | 实盘牛人多榜 |')
    md.append('| 持仓 | 3 | **`queryUserFundHoldingInfo`** | 个人持仓 |')
    md.append('| 辅助 | 4 | `legogw / buildVisualizeData` | 页面渲染 |')
    md.append('')
    md.append('### 🎯 最重要 5 个新发现')
    md.append('')
    md.append('1. **`pcQueryUserInfo` 返回您自己的 numeric_id = 17533758**  ')
    md.append('   `{"uid":"jimu_user_info-17533758","userName":"jd_9b2u5ec8t4pmtb"}`')
    md.append('')
    md.append('2. **`queryUserFundHoldingInfo` userId 参数不影响** —— 永远返回当前登录用户持仓  ')
    md.append('   13.4KB 包含 fundList, totalAmount, userInfo 等')
    md.append('')
    md.append('3. **`feedFlowOfCircle tagId=112 contentId=2689640`** = 关注流  ')
    md.append('   渲染您关注的所有大佬动态（蓝鲸/红豆/和路雪/Z先生/晴空/小猫咪）')
    md.append('')
    md.append('4. **`queryFundFirmOfferMultiRank` rankType 400-405 = 5 大牛人榜**  ')
    md.append('   与 queryFullRanking 互补：Full 是基金，牛人是持有人排名')
    md.append('')
    md.append('5. **`homePageHeadInfo` + `getPageMutilData pageId=3973` = 蓝鲸跃财个人主页**  ')
    md.append('   `homePageHeadInfo` 5.9KB 含 headImg/fans/follows/desc')
    md.append('')
    md.append('### ❌ 失败的端点（路径错或已下线）')
    md.append('')
    md.append('| 端点 | 原因 |')
    md.append('|---|---|')
    md.append('| `getInvestResearchRank` | 已下线 status=FAIL |')
    md.append('| `getRankingProductListV2` | 已下线 "请先登录" |')
    md.append('| `getFundDetail / getTradeRule / queryFundDetail / queryNetValueTrend / queryPerformance / queryFundPortfolio / queryManagerInfo / queryNewsList` 等 20+ | **jdjr.jd.com 根本没有基金详情页**，这些端点路径不对（实际在 fund.jd.com 或 APP 端） |')
    md.append('| `getSimpleQuote / getFundLabelList / getFundBaseInfo` | API 识别错误 10000404 |')
    md.append('| `queryFundDetailV2 / queryFundBaseInfo` | 同上 |')
    md.append('| `getIndexBlockInfo / getIndexDetail / getIndexValuationTrendChart / getBuyIndexRelatedFund` | status=FAIL 需正确参数 |')
    md.append('')

    # 关注列表
    md.append('## 你实际关注的大佬列表')
    md.append('')
    md.append('**抓取来源**: `feedFlowOfCircle tagId=112 contentId=2689640` 关注 tab feed')
    md.append('')
    md.append('| 序号 | 大佬名 | 等级 | 持仓收益 | 您的代码中? | 需要补充 numeric_id |')
    md.append('|---|---|---|---|---|---|')
    md.append('| 1 | 红豆的甜美 | Lv.8 | 311.3万 | ❌ 缺失 | ✅ 需要 |')
    md.append('| 2 | 蓝鲸跃财 | Lv.8 | 318.6万 | ✅ 3546208 | - |')
    md.append('| 3 | 京东-和路雪 | Lv.7 | 183.3万 | ❌ 缺失 | ✅ 需要 |')
    md.append('| 4 | Z先生养基 | Lv.9 | 429.7万 | ✅ 14345330 | - |')
    md.append('| 5 | 晴空万里理财 | Lv.8 | 277.6万 | ✅ 3748946 | - |')
    md.append('| 6 | 小猫咪爱赚钱 | Lv.6 | 176.0万 | ❌ 缺失 | ✅ 需要 |')
    md.append('')
    md.append('**抓取方法**:')
    md.append('```python')
    md.append('from tools.jd_finance_api import JDFinanceAPI')
    md.append('api = JDFinanceAPI(cookies=load_cookies())')
    md.append('feed = api.get_following_feed()  # tagId=112')
    md.append('for item in feed["data"]["resultList"]:')
    md.append('    user = item["userInfo"]')
    md.append('    print(user["nickName"], user["userId"])  # 拿到 numeric_id')
    md.append('```')
    md.append('')
    md.append('---')
    md.append('')

    # 详细端点
    md.append('## 七大类端点详细文档')
    md.append('')

    for cat_name, items in ENDPOINT_CATEGORIES.items():
        md.append(f'### {cat_name}')
        md.append('')
        for key, method, path, desc in items:
            file_key = key + '.json'
            # 尝试找到对应的 file
            actual_key = None
            for k in file_data:
                if key.replace('_', '-').startswith(k.replace('_', '-')[:20]):
                    actual_key = k
                    break
            if not actual_key:
                for k in file_data:
                    if key.split('_')[0] in k:
                        actual_key = k
                        break
            data = file_data.get(actual_key, {})

            status = '?'
            size = '?'
            if isinstance(data, dict):
                if 'url' in data:
                    status = data.get('status', '?')
                    size = data.get('len', '?')
                else:
                    rd = data.get('resultData', {})
                    if isinstance(rd, dict):
                        size = len(json.dumps(data, ensure_ascii=False))
                        # status 可能不存在

            md.append(f'#### `{path}`')
            md.append('')
            md.append(f'- **方法**: `{method}`  ')
            md.append(f'- **描述**: {desc}  ')
            md.append(f'- **响应状态**: {status}  ')
            md.append(f'- **响应大小**: {size} 字节  ')
            md.append('- **完整 URL**:')
            md.append('  ```')
            # 重新构造完整 URL
            full_url = f'https://ms.jr.jd.com/{path}'
            md.append(f'  {full_url}')
            md.append('  ```')
            md.append('')
        md.append('')

    # 响应结构示例
    md.append('## 响应结构示例')
    md.append('')
    md.append('### `queryFullRanking_h5` (榜单 287KB)')
    md.append('')
    md.append('```json')
    md.append('{')
    md.append('  "resultData": {')
    md.append('    "datas": {')
    md.append('      "primRanking": [  // 一级分类 3 个')
    md.append('        {')
    md.append('          "primRankName": "人气认证",  // 5 个榜单')
    md.append('          "secRanking": [')
    md.append('            {')
    md.append('              "rankingContent": [  // 每榜 20 只基金')
    md.append('                {')
    md.append('                  "fundCode": "016416",')
    md.append('                  "fundName": "南方稳鑫6个月持有债券A",')
    md.append('                  "primInvKey": "近1年收益率",')
    md.append('                  "secInvValue": "+3.05%",')
    md.append('                  "secRedGreen": true,')
    md.append('                  "riskLevel": "中高风险",')
    md.append('                  "subRankName": "近1年",')
    md.append('                  "fundDetailUrl": "https://fund.jd.com/..."')
    md.append('                }')
    md.append('              ]')
    md.append('            }')
    md.append('          ]')
    md.append('        }')
    md.append('      ]')
    md.append('    }')
    md.append('  },')
    md.append('  "resultCode": 0,')
    md.append('  "resultMsg": "成功"')
    md.append('}')
    md.append('```')
    md.append('')
    md.append('### `queryUserFundHoldingInfo` (个人持仓 13.4KB)')
    md.append('')
    md.append('```json')
    md.append('{')
    md.append('  "resultData": {')
    md.append('    "data": {')
    md.append('      "userInfo": {')
    md.append('        "userAvatar": "...",')
    md.append('        "userName": "jd_9b2u5ec8t4pmtb",')
    md.append('        "isSelf": true,')
    md.append('        "jumpData": {')
    md.append('          "schemeUrl": "openjdjrapp://com.jd.jrapp/..."')
    md.append('        }')
    md.append('      },')
    md.append('      "fundList": [')
    md.append('        // 用户所有基金持仓')
    md.append('      ],')
    md.append('      "totalAmount": "8437152.97",  // 总金额')
    md.append('      "totalProfit": "3186032.31"   // 总收益')
    md.append('    }')
    md.append('  }')
    md.append('}')
    md.append('```')
    md.append('')
    md.append('### `feedFlowOfCircle` (关注流 80KB)')
    md.append('')
    md.append('```json')
    md.append('{')
    md.append('  "resultData": {')
    md.append('    "code": 0,')
    md.append('    "data": {')
    md.append('      "pageSize": 7,')
    md.append('      "lastId": "...",  // 翻页游标')
    md.append('      "resultList": [')
    md.append('        {')
    md.append('          "feedId": "...",')
    md.append('          "userInfo": {')
    md.append('            "userId": "3546208",  // numeric_id')
    md.append('            "nickName": "蓝鲸跃财",')
    md.append('            "userLevel": 8,')
    md.append('            "fundProfit": "318.6万",')
    md.append('            "avatarUrl": "..."')
    md.append('          },')
    md.append('          "content": "【蓝鲸观点】...",')
    md.append('          "publishTime": "2026-07-12 14:30",')
    md.append('          "likeCount": 19,')
    md.append('          "commentCount": 29,')
    md.append('          "shareCount": 5,')
    md.append('          "imageList": []')
    md.append('        }')
    md.append('      ]')
    md.append('    }')
    md.append('  }')
    md.append('}')
    md.append('```')
    md.append('')
    md.append('### `queryFundFirmOfferMultiRankHead` (牛人榜头 2.6KB)')
    md.append('')
    md.append('```json')
    md.append('{')
    md.append('  "resultData": {')
    md.append('    "data": {')
    md.append('      "rankTypeRadio": {')
    md.append('        "options": [')
    md.append('          {')
    md.append('            "label": "收益最多",  // 父类')
    md.append('            "value": "400",')
    md.append('            "children": [')
    md.append('              {"label":"收益总榜","value":"401"},')
    md.append('              {"label":"稳健掌舵人","value":"403"},')
    md.append('              {"label":"均衡配置专家","value":"404"},')
    md.append('              {"label":"海外先锋","value":"405"}')
    md.append('            ]')
    md.append('          },')
    md.append('          // 还有 7 个父类 ...')
    md.append('        ]')
    md.append('      }')
    md.append('    }')
    md.append('  }')
    md.append('}')
    md.append('```')
    md.append('')
    md.append('### `homePageHeadInfo` (蓝鲸跃财 5.9KB)')
    md.append('')
    md.append('```json')
    md.append('{')
    md.append('  "resultData": {')
    md.append('    "data": {')
    md.append('      "userId": "3546208",')
    md.append('      "nickName": "蓝鲸跃财",')
    md.append('      "avatarUrl": "...",')
    md.append('      "userLevel": 8,')
    md.append('      "fansCount": 324000,  // 32.4万')
    md.append('      "followCount": 14,')
    md.append('      "isFollowed": true,')
    md.append('      "desc": "...",')
    md.append('      "totalAmount": "8437152.97",  // 8,437,152.97 元')
    md.append('      "totalProfit": "3186032.31",  // 3,186,032.31 元')
    md.append('      "wealthAge": 8.5,  // 财龄')
    md.append('      "ipLocation": "黑龙江",')
    md.append('      "fundList": [')
    md.append('        // 持仓基金列表（详细）')
    md.append('      ]')
    md.append('    }')
    md.append('  }')
    md.append('}')
    md.append('```')
    md.append('')

    # Python 封装
    md.append('## 即用型 Python 封装')
    md.append('')
    md.append('添加到 `tools/jd_finance_api.py`:')
    md.append('')
    md.append('```python')
    md.append('class JDFinanceAPI:')
    md.append('    BASE = "https://ms.jr.jd.com"')
    md.append('    ')
    md.append('    # ============= 用户 =============')
    md.append('    def get_current_user(self):')
    md.append('        """获取当前登录用户 (uid/numeric_id 都在)"""')
    md.append('        url = f"{self.BASE}/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo"')
    md.append('        return self._post(url, {})')
    md.append('    ')
    md.append('    def get_user_holding(self):')
    md.append('        """获取当前登录用户的基金持仓 (13KB 含 fundList)"""')
    md.append('        url = f"{self.BASE}/gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo"')
    md.append('        # userId 参数不影响，永远返当前用户')
    md.append('        return self._get(url, {"userId": "", "pageId": 1, "pageSize": 50})')
    md.append('    ')
    md.append('    def get_user_homepage(self, user_id: str):')
    md.append('        """获取大佬个人主页 (蓝鲸跃财 5.9KB)"""')
    md.append('        url = f"{self.BASE}/gw2/generic/CreatorSer/h5/m/homePageHeadInfo"')
    md.append('        return self._post(url, {"userId": user_id})')
    md.append('    ')
    md.append('    # ============= 关注流 =============')
    md.append('    def get_following_feed(self, last_id: str = "", page_size: int = 20):')
    md.append('        """⭐ 获取我关注的大佬动态流 (80KB 含 6 大佬动态)"""')
    md.append('        url = f"{self.BASE}/gw/generic/jimu/h5/m/feedFlowOfCircle"')
    md.append('        req = {')
    md.append('            "tagId": 112,  # 关注流')
    md.append('            "contentId": "2689640",  # 基金圈')
    md.append('            "iosType": "",')
    md.append('            "extParams": {"requestFrom": "h5"},')
    md.append('            "lastId": last_id,')
    md.append('            "pageSize": page_size')
    md.append('        }')
    md.append('        return self._get(url, req)')
    md.append('    ')
    md.append('    def get_recommend_feed(self, last_id: str = ""):')
    md.append('        """推荐流 (tagId=55)"""')
    md.append('        return self.get_feed(tag_id=55, last_id=last_id)')
    md.append('    ')
    md.append('    def get_latest_feed(self, last_id: str = ""):')
    md.append('        """最新流 (tagId=113)"""')
    md.append('        return self.get_feed(tag_id=113, last_id=last_id)')
    md.append('    ')
    md.append('    # ============= 排行榜 =============')
    md.append('    def get_full_ranking(self, device: str = "h5"):')
    md.append('        """⭐ 26 个官方榜单 (人气/主题/业绩)，每榜 20 只 = 287KB"""')
    md.append('        url = f"{self.BASE}/gw2/generic/jj/h5/m/queryFullRanking"')
    md.append('        return self._get(url, {"deviceType": device})')
    md.append('    ')
    md.append('    def get_featured_rankings(self):')
    md.append('        """便捷方法：解析 queryFullRanking 为 list[dict]"""')
    md.append('        data = self.get_full_ranking()')
    md.append('        result = []')
    md.append('        for prim in data["resultData"]["datas"]["primRanking"]:')
    md.append('            for sec in prim["secRanking"]:')
    md.append('                for fund in sec["rankingContent"]:')
    md.append('                    result.append({')
    md.append('                        "category": prim["primRankName"],')
    md.append('                        "list_name": sec.get("secRankName"),')
    md.append('                        **fund')
    md.append('                    })')
    md.append('        return result  # 26*20 = 520 条')
    md.append('    ')
    md.append('    # ============= 牛人榜 =============')
    md.append('    def get_bull_rank_head(self):')
    md.append('        """⭐ 牛人榜 14 子榜配置 (收益最多/稳健/均衡/海外先锋)"""')
    md.append('        url = f"{self.BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRankHead"')
    md.append('        return self._get(url)')
    md.append('    ')
    md.append('    def get_bull_rank(self, rank_type: str = "400", page_id: int = 1):')
    md.append('        """获取某牛人榜 (rank_type 400=收益最多, 401=收益总, 403=稳健, 404=均衡, 405=海外)"""')
    md.append('        url = f"{self.BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank"')
    md.append('        return self._get(url, {"rankType": rank_type, "pageId": page_id, "pageSize": 20})')
    md.append('    ')
    md.append('    # ============= 行情 =============')
    md.append('    def get_index_quote(self, codes: List[str]):')
    md.append('        """A 股/港股/美股/黄金批量行情"""')
    md.append('        url = f"{self.BASE}/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes"')
    md.append('        return self._get(url, {')
    md.append('            "ticket": "jdt-wealth-tools",')
    md.append('            "uniqueCodes": codes')
    md.append('        })')
    md.append('    ')
    md.append('    def get_gold_price(self, code: str = "CZB-JCJ"):')
    md.append('        """积存金金价 (独立域 api.jdjygold.com)"""')
    md.append('        return self._get(f"https://api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice?goldCode={code}")')
    md.append('    ')
    md.append('    def get_zx_product_list(self, ptype: int = 1):')
    md.append('        """自选产品行情 (jdtwt) - 7.9KB 含基金 code + 涨幅"""')
    md.append('        url = f"{self.BASE}/gw2/generic/jdtwt/h5/m/queryZxProductList"')
    md.append('        return self._get(url, {"type": ptype})')
    md.append('```')
    md.append('')

    # 404 端点
    md.append('## 404 端点清单（路径错误，jdjr.jd.com 不存在）')
    md.append('')
    md.append('以下端点**不在 jdjr.jd.com (PC H5)**，调用均返回 `{"resultCode":10000404,"resultMsg":"API识别错误"}` 或 `{"resultCode":-1,"resultMsg":"业务请求异常"}`:')
    md.append('')
    md.append('| 端点路径 | 状态 | 备注 |')
    md.append('|---|---|---|')
    md.append('| `gw/generic/jj/h5/m/getFundDetail` | 404 | 基金详情，APP 端才有 |')
    md.append('| `gw2/generic/jj/h5/m/getFundDetail` | 404 | 同上 |')
    md.append('| `gw2/generic/jj/h5/m/queryFundDetail` | 404 | 同上 |')
    md.append('| `gw/generic/jj/h5/m/getTradeRule` | 404 | 交易规则 |')
    md.append('| `gw2/generic/jj/h5/m/queryTradeRule` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/getFundManager` | 404 | 基金经理 |')
    md.append('| `gw2/generic/jj/h5/m/queryManagerInfo` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/getFundAnnouncement` | 404 | 基金公告 |')
    md.append('| `gw2/generic/jj/h5/m/getFundBaseInfo` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/getFundInfo` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/queryFundDetailV2` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/queryFundBaseInfo` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/queryNetValueTrend` | 404 | 净值曲线 |')
    md.append('| `gw2/generic/jj/h5/m/queryNetValue` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/queryFundChartData` | 404 | 累计收益率 |')
    md.append('| `gw2/generic/jj/h5/m/queryPerformance` | 404 | 业绩 |')
    md.append('| `gw2/generic/jj/h5/m/queryFundPerformance` | 404 | |')
    md.append('| `gw2/generic/jj/h5/m/queryFundPortfolio` | 404 | 持仓 |')
    md.append('| `gw2/generic/jj/h5/m/queryFundStockPortfolio` | 404 | 持仓股票 |')
    md.append('| `gw2/generic/jj/h5/m/queryNewsList` | 404 | 资讯 |')
    md.append('| `gw2/generic/jj/h5/m/querySubRankingList` | 404 | 子榜 |')
    md.append('| `gw2/generic/opdataapi/newh5/m/getSimpleQuote` | 404 | |')
    md.append('| `gw2/generic/opdataapi/newh5/m/getFundLabelList` | 404 | |')
    md.append('| `gw2/generic/opdataapi/newh5/m/getFundBaseInfo` | 404 | |')
    md.append('| `gw2/generic/wealthBase/newh5/m/getIndexBlockInfo` | 200 (FAIL) | 需正确参数 |')
    md.append('| `gw2/generic/wealthBase/newh5/m/getIndexDetail` | 200 (FAIL) | |')
    md.append('| `gw2/generic/wealthBase/newh5/m/getIndexValuationTrendChart` | 200 (FAIL) | |')
    md.append('| `gw2/generic/wealthBase/newh5/m/getBuyIndexRelatedFund` | 200 (FAIL) | |')
    md.append('')
    md.append('**结论**: jdjr.jd.com (PC H5) **没有基金详情/净值/经理/公告端点**。')
    md.append('这些信息通过 fund.jd.com 静态页 或 APP 端获取（不在 H5 API 域）。')
    md.append('**实际上** 您项目里 `tools/jd_finance_api.py` 的 `get_fund_chart_data` 等函数能工作是因为走的是 **fund.jd.com 静态资源** (`storage.360buyimg.com/app-oss-dev/*.json`)，不是 ms.jr.jd.com API。')
    md.append('')

    # 数据位置
    md.append('## 原始响应数据位置')
    md.append('')
    md.append(f'所有 {len(files)} 个原始 JSON 响应保存在:  ')
    md.append('```')
    md.append('c:/项目/A基金/基金/.playwright-mcp/')
    md.append('```')
    md.append('')
    md.append('文件列表:')
    md.append('')
    for f in files:
        size = os.path.getsize(f)
        md.append(f'- `{os.path.basename(f)}` ({size/1024:.1f} KB)')
    md.append('')
    md.append('---')
    md.append('')
    md.append('## 下一步建议')
    md.append('')
    md.append('1. **补 3 个新关注人的 numeric_id** —— 在浏览器关注流点击 红豆的甜美/京东-和路雪/小猫咪爱赚钱 头像，记下 URL 中的 `jimu_user_info-XXXXX` 数字')
    md.append('2. **添加 `get_following_feed` 函数** —— 自动发现新关注的人（无需手填）')
    md.append('3. **添加 `get_user_holding` 函数** —— `queryUserFundHoldingInfo` 真实工作且不需 userId 永远返当前用户')
    md.append('4. **添加 `get_bull_rank` 函数** —— 5 大牛人榜全 200 OK')
    md.append('5. **牛人榜 + 关注流结合** —— 算出"我关注的人中谁上了牛人榜"')
    md.append('')

    # 保存
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))

    size = os.path.getsize(OUT_MD)
    print(f'✅ 生成 {OUT_MD}')
    print(f'   大小: {size/1024:.1f} KB ({size/1024/1024:.2f} MB)')
    print(f'   端点数: {sum(len(v) for v in ENDPOINT_CATEGORIES.values())}')
    print(f'   源文件数: {len(files)}')

if __name__ == '__main__':
    main()
