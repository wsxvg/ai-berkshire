import sys
sys.path.insert(0, '.')
from tools.jd_finance_api import _api_post
import json

for code in ['519673', '100055', '501226', '000043', '501026', '161725']:
    data = _api_post('gw/generic/jj/h5/m/getFundTradeRulesPageInfo', {'fundCode': code})
    rd = data.get('resultData', {})
    datas = rd.get('datas', {})
    rr = datas.get('redeemRule', {})
    print(f'===== {code} =====')
    print(f'  redeemText: {rr.get("redeemText", "N/A")!r}')
    print(f'  isSupportFastRedeem: {rr.get("isSupportFastRedeem", "N/A")!r}')
    print(f'  redeemMinPortion: {rr.get("redeemMinPortion", "N/A")!r}')
    print(f'  redeemHoldPortion: {rr.get("redeemHoldPortion", "N/A")!r}')
    print(f'  redeemStatus: {rr.get("redeemStatus", "N/A")!r}')
    # Also check datas-level fields
    for k in ['quickRedeemFlag', 'quickRedeemText', 'redeemTN', 'arriveTN', 'redeemDays', 'tPlusN']:
        if k in datas:
            print(f'  datas.{k}: {datas[k]!r}')
        if k in rr:
            print(f'  redeemRule.{k}: {rr[k]!r}')
    print()
