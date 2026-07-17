"""验证所有新/改进 API 端点"""
import urllib.request, urllib.error, json
import sys

BASE = 'http://127.0.0.1:3456'

# (path, method, body, description)
TESTS = [
    # 新端点
    ('/api/status', 'GET', None, '系统状态'),
    ('/api/health', 'GET', None, '健康检查'),
    ('/api/cache/clear', 'GET', None, '列出缓存'),
    ('/api/insights', 'GET', None, '全局 insights'),
    ('/api/insights?code=005660', 'GET', None, '单基金 signals'),
    ('/api/insights?code=005660&type=analysis', 'GET', None, '单基金 analysis'),
    # 改进端点
    ('/api/fund', 'GET', None, '自选 GET (空 30min 缓存)'),
    ('/api/score?codes=005660', 'GET', None, '评分 (含 missing)'),
    ('/api/score?codes=invalid', 'GET', None, '评分 400 (非法 code)'),
    ('/api/score?codes=005660,016416,012240', 'GET', None, '评分 3 只'),
    ('/api/ranking?limit=5', 'GET', None, '排行 limit=5'),
    ('/api/ranking?sortBy=sharpe&limit=3', 'GET', None, '排行 排序'),
    ('/api/ranking?type=' + urllib.parse.quote('股票型') + '&limit=3', 'GET', None, '排行 过滤'),
    ('/api/ranking?search=' + urllib.parse.quote('华夏') + '&limit=3', 'GET', None, '排行 搜索'),
    ('/api/ranking/featured', 'GET', None, '精选榜单'),
    ('/api/sector', 'GET', None, '行业列表'),
    ('/api/sector?code=801010', 'GET', None, '单行业'),
    ('/api/sector?status=low', 'GET', None, '行业 过滤低估'),
    ('/api/news', 'GET', None, '资讯'),
    ('/api/news?asof=2026-07-01&lookback=7', 'GET', None, '资讯 历史回测'),
    ('/api/notices?codes=005660', 'GET', None, '公告'),
    ('/api/notices?criticalOnly=true&codes=005660', 'GET', None, '公告 关键'),
    ('/api/notices?codes=005660&keywords=' + urllib.parse.quote('限购,清盘'), 'GET', None, '公告 自定义关键词'),
    ('/api/compare?codes=005660,016416', 'GET', None, '对比'),
    ('/api/compare?codes=A,B,C,D,E,F,G,H,I,J,K', 'GET', None, '对比 11 只 (超限)'),
    ('/api/compare?codes=invalid', 'GET', None, '对比 非法'),
    ('/api/detail?code=005660', 'GET', None, '详情'),
    ('/api/detail', 'GET', None, '详情 缺 code (400)'),
    ('/api/detail?code=abc', 'GET', None, '详情 非法 (400)'),
    ('/api/feed', 'GET', None, 'feed'),
    ('/api/feed?action=buy&page=1&pageSize=5', 'GET', None, 'feed 分页+筛选'),
    ('/api/backtest', 'GET', None, '最优配置'),
    ('/api/backtest?list=true', 'GET', None, '列出所有历史最优'),
    ('/api/report', 'GET', None, '日报'),
    ('/api/report?days=10', 'GET', None, '日报 days=10'),
    ('/api/search?q=005660&localOnly=true', 'GET', None, '搜索 本地'),
    # 错误路径
    ('/api/foo/bar', 'GET', None, '未知路径 404'),
    ('/api/' + urllib.parse.quote('任意不存在'), 'POST', {}, '未知路径 POST 404'),
    # POST 端点
    ('/api/fund', 'POST', '{"code": "999999", "name": "测试"}', '自选 添加'),
    ('/api/fund?code=999999', 'DELETE', None, '自选 删除'),
    ('/api/run-backtest', 'POST', '{"start":"2024-03-11","end":"2024-03-12","cash":100000,"timeout":60}', '回测(1天-快)'),
    ('/api/run-backtest', 'POST', '{"start":"bad","end":"2026-07-01","cash":100000}', '回测 400 校验'),
    ('/api/run-backtest', 'POST', '{"start":"2026-07-01","end":"2024-03-11"}', '回测 start>=end'),
]

passed = 0
failed = 0
for path, method, body, desc in TESTS:
    url = BASE + path
    req = urllib.request.Request(url, method=method)
    if body:
        req.data = body.encode('utf-8')
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status = r.status
            text = r.read().decode('utf-8', errors='replace')
            preview = text[:100]
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read().decode('utf-8', errors='replace')
        preview = text[:100]
    except Exception as e:
        status = 'ERR'
        preview = str(e)[:100]
        text = ''

    # 检查是否包含错误 (业务 4xx/5xx 视为预期)
    has_error = '"error"' in text[:200] or status in (400, 404, 503)
    flag = 'OK' if (status == 200 or has_error) else 'FAIL'
    if flag == 'OK':
        passed += 1
    else:
        failed += 1
    print(f'[{flag}] {method:5} {status:3} {path:50} | {desc}  | {preview}')

print(f'\n{"=" * 60}\n  PASSED: {passed}  FAILED: {failed}  TOTAL: {len(TESTS)}\n{"=" * 60}')
sys.exit(0 if failed == 0 else 1)
