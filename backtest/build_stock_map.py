#!/usr/bin/env python3
"""建立股票代码→行业映射表（基于持仓数据手工补充）"""
import json, glob

# 已知的股票→行业映射（通过股票名字+实际业务判断）
# 格式: {股票代码: 行业}
STOCK_SECTOR = {
    # ── 通信/光模块 ──
    "300502": "通信",  # 新易盛 - 光模块龙头
    "300308": "通信",  # 中际旭创 - 光模块龙头
    "300394": "通信",  # 天孚通信 - 光器件
    "300548": "通信",  # 博创科技 - 光器件
    "600487": "通信",  # 亨通光电 - 光纤光缆
    "600498": "通信",  # 烽火通信 - 通信设备
    "601869": "通信",  # 长飞光纤 - 光纤光缆

    # ── 科技/电子 ──
    "300476": "科技",  # 胜宏科技 - PCB
    "300620": "科技",  # 光库科技 - 光纤器件
    "300757": "科技",  # 罗博特科 - 自动化设备
    "301200": "科技",  # 大族数控 - PCB设备
    "600183": "科技",  # 生益科技 - 覆铜板
    "002384": "科技",  # 东山精密 - PCB/精密制造
    "002463": "科技",  # 沪电股份 - PCB
    "002851": "科技",  # 麦格米特 - 电源设备
    "002916": "科技",  # 深南电路 - PCB
    "601231": "科技",  # 环旭电子 - 电子制造

    # ── 半导体 ──
    "688498": "半导体",  # 源杰科技 - 光芯片
    "688150": "半导体",  # 莱特光电 - OLED材料
    "688167": "半导体",  # 炬光科技 - 激光器件
    "688195": "半导体",  # 腾景科技 - 光学元件
    "688205": "半导体",  # 德科立 - 光芯片
    "688183": "半导体",  # 生益电子 - PCB/半导体

    # ── 材料/元器件 ──
    "600105": "科技",  # 永鼎股份 - 光缆
    "300806": "科技",  # 斯迪克 - 功能性涂层材料
    "301377": "科技",  # 鼎泰高科 - PCB微型钻头

    # ── 港股科技 ──
    "06869": "科技",  # 长飞光纤(港股)
    "KR7000660001": "半导体",  # 三星半导体
    "KR7005930003": "半导体",  # 海力士半导体

    # ── 美股半导体/AI ──
    "NVDA": "半导体",  # 英伟达
    "TSM": "半导体",  # 台积电
    "AVGO": "半导体",  # 博通
    "ASML": "半导体",  # 阿斯麦
    "MU": "半导体",  # 美光科技
    "INTC": "半导体",  # 英特尔
    "TSEM": "半导体",  # Tower半导体
    "MPWR": "半导体",  # 芯源系统
    "ONTO": "半导体",  # Onto Innovation
    "COHR": "半导体",  # Coherent Corp.
    "LITE": "半导体",  # Lumentum
    "AEIS": "半导体",  # 先进能源工业
    "SNDK": "半导体",  # Sandisk
    "TER": "半导体",  # 泰瑞达

    # ── 美股科技 ──
    "AAPL": "科技",  # 苹果
    "MSFT": "科技",  # 微软
    "GOOGL": "科技",  # 谷歌
    "GOOG": "科技",  # 谷歌
    "META": "科技",  # Meta
    "AMZN": "科技",  # 亚马逊
    "WDC": "科技",  # 西部数据

    # ── 美股消费/其他 ──
    "TSLA": "科技",  # 特斯拉
    "WMT": "消费",  # 沃尔玛

    # ── 美股通信 ──
    "CIEN": "通信",  # Ciena科技
    "VIAV": "通信",  # Viavi
    "AAOI": "通信",  # 应用光电子
    "GLW": "科技",  # 康宁

    # ── 印度金融 ──
    "ICICIBC": "金融",  # ICICI银行
    "HDFCB": "金融",  # HDFC银行
    "AXSB": "金融",  # Axis银行
    "SBIN": "金融",  # 印度国家银行
    "BAF": "金融",  # Bajaj金融
    "BHARTI": "科技",  # 巴帝电信
    "MM": "金融",  # 金融公司
    "SHFL": "金融",  # Shriram金融
    "TTAN": "消费",  # 泰坦公司
    "RELIANCE": "科技",  # 信实工业
}

if __name__ == "__main__":
    # 验证覆盖率
    stocks_found = set()
    stocks_missing = set()

    for f in glob.glob('data/fund_cache/fund_holdings_*.json'):
        try:
            d = json.load(open(f,'r',encoding='utf-8'))
            for s in d.get('top_stocks',[]):
                code = s.get('code','')
                if code in STOCK_SECTOR:
                    stocks_found.add(code)
                else:
                    stocks_missing.add((code, s.get('name','')))
        except: pass

    print(f"已覆盖: {len(stocks_found)} 只股票")
    print(f"未覆盖: {len(stocks_missing)} 只")
    for code, name in sorted(stocks_missing):
        print(f"  {code}: {name}")

    # 保存映射表
    json.dump(STOCK_SECTOR, open('backtest/data/stock_sector_map.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f"\n已保存到 backtest/data/stock_sector_map.json")
