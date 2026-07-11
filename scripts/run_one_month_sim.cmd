@echo off
REM 跑近一个月 (5-31 ~ 7-01) 的历史模拟
REM 5-31 是周日 (无交易), 但用作起点
REM 7-11 单独跑 (今天真实数据)
setlocal
set PYTHONIOENCODING=utf-8
cd /d c:\项目\A基金\基金
set DATES=2026-06-01 2026-06-02 2026-06-03 2026-06-04 2026-06-05 2026-06-08 2026-06-09 2026-06-10 2026-06-11 2026-06-12 2026-06-15 2026-06-16 2026-06-17 2026-06-18 2026-06-19 2026-06-22 2026-06-23 2026-06-24 2026-06-25 2026-06-26 2026-06-29 2026-06-30 2026-07-01
for %%D in (%DATES%) do (
  echo === Simulating %%D ===
  py -3.10 scripts\daily_live.py --simulate-date %%D 1>>_sim_month.txt 2>>&1
  echo. >> _sim_month.txt
)
echo === One month done ===
endlocal
