@echo off
REM 3个月模拟: 2026-04-13 ~ 2026-07-11 (T+N bug 已修)
REM 1. 重置虚拟组合 (删 virtual_portfolio.json)
REM 2. 按工作日顺序跑

setlocal
set PYTHONIOENCODING=utf-8
cd /d "c:\项目\A基金\基金"

REM 备份 + 重置
if not exist reports\sim\virtual_portfolio_3month_baseline.json (
  copy /Y reports\sim\virtual_portfolio.json reports\sim\virtual_portfolio_1month_baseline.json >nul
  del /Q reports\sim\virtual_portfolio.json
)

REM 3 个月 (4-13 ~ 7-11 共 58 个工作日, 跳过周末)
set DATES=2026-04-13 2026-04-14 2026-04-15 2026-04-16 2026-04-17 2026-04-20 2026-04-21 2026-04-22 2026-04-23 2026-04-24 2026-04-27 2026-04-28 2026-04-29 2026-04-30 2026-05-06 2026-05-07 2026-05-08 2026-05-11 2026-05-12 2026-05-13 2026-05-14 2026-05-15 2026-05-18 2026-05-19 2026-05-20 2026-05-21 2026-05-22 2026-05-25 2026-05-26 2026-05-27 2026-05-28 2026-05-29 2026-06-01 2026-06-02 2026-06-03 2026-06-04 2026-06-05 2026-06-08 2026-06-09 2026-06-10 2026-06-11 2026-06-12 2026-06-15 2026-06-16 2026-06-17 2026-06-18 2026-06-19 2026-06-22 2026-06-23 2026-06-24 2026-06-25 2026-06-26 2026-06-29 2026-06-30 2026-07-01 2026-07-11

REM 删 6-01~7-11 旧 md/json 重建
del /Q reports\sim\2026-06-*.md reports\sim\2026-06-*.json reports\sim\2026-07-01.md reports\sim\2026-07-01.json reports\sim\2026-07-11.md reports\sim\2026-07-11.json 2>nul

for %%D in (%DATES%) do (
  echo === Simulating %%D ===
  py -3.10 scripts\daily_live.py --simulate-date %%D 1>>_sim_3month.txt 2>>&1
  echo. >> _sim_3month.txt
)
echo === 3 months done ===
endlocal
