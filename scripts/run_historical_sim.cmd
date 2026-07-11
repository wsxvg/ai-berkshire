@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d c:\项目\A基金\基金
set DATES=2026-05-22 2026-05-29 2026-06-05 2026-06-12 2026-06-19 2026-06-26
for %%D in (%DATES%) do (
  echo === Simulating %%D ===
  py -3.10 scripts\daily_live.py --simulate-date %%D 1>>_sim_all.txt 2>>&1
  echo. >> _sim_all.txt
)
echo === All done ===
endlocal

