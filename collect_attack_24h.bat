@echo off
REM ============================================================
REM  collect_attack_24h.bat  —  Day 2: Attack Dataset
REM  Output : data\attack_24h_hw\master_dataset.csv
REM  Rows   : ~864,000 @ 10 Hz over 24 h
REM  Attacks: All 9 types (IDs 8-16), ~45% attack / 55% normal
REM
REM  Attack types injected:
REM   ID  8  Tank Overflow      (LIT_101 ramps up, outlet blocked)
REM   ID  9  Chemical Depletion (dosing tanks drain to 0)
REM   ID 10  Membrane Damage    (DPIT + fouling factor ramp)
REM   ID 11  pH Manipulation    (AIT_202 driven to target)
REM   ID 12  Slow Ramp          (AIT_202 +1 unit every 2 s)
REM   ID 13  Reconnaissance     (network scan, label only)
REM   ID 14  Denial of Service  (sensor registers frozen)
REM   ID 15  Replay Attack      (stale snapshot replayed)
REM   ID 16  Valve Manipulation (MV_101/301/302=0, flows=0)
REM
REM  PRE-CHECKS:
REM    1. CODESYS reachable at 192.168.5.194:1502
REM    2. MATLAB swat_physics_server.m is running
REM    3. Normal 24h run is COMPLETE (run Day 1 first!)
REM    4. No attack_scheduler.lock file in data\attack_24h_hw\
REM ============================================================

setlocal
cd /d "%~dp0"

set HOST=192.168.5.194
set PORT=1502
set MATLAB_PATH=C:\Users\Dweep\Documents\water-cps
set OUTPUT=data\attack_24h_hw
set TOTAL_MIN=1440
set ATTACK_SCRIPT=attack_schedular_24h.py
set LOGFILE=logs\collect_attack_24h.log

echo.
echo ============================================================
echo   SWaT  --  Attack 24-Hour Data Collection
echo   Host     : %HOST%:%PORT%
echo   Output   : %OUTPUT%\master_dataset.csv
echo   Duration : %TOTAL_MIN% min (24 h)
echo   Scheduler: %ATTACK_SCRIPT%
echo   Target   : ~45%% attack / 55%% normal
echo ============================================================
echo.

if not exist logs      mkdir logs
if not exist %OUTPUT%  mkdir %OUTPUT%

REM Safety: refuse to start if lockfile already exists
if exist "%OUTPUT%\attack_scheduler.lock" (
    echo [ERROR] Lock file found: %OUTPUT%\attack_scheduler.lock
    echo         Another scheduler may still be running!
    echo         If you are SURE no other process is running, delete it:
    echo           del "%OUTPUT%\attack_scheduler.lock"
    echo         Then run this batch file again.
    pause
    exit /b 1
)

echo [%DATE% %TIME%] Starting attack 24h collection >> %LOGFILE%

python start_system.py ^
    --host               %HOST%            ^
    --port               %PORT%            ^
    --reuse-existing-matlab                ^
    --matlab-path        "%MATLAB_PATH%"   ^
    --output             %OUTPUT%          ^
    --total              %TOTAL_MIN%       ^
    --attack-script      %ATTACK_SCRIPT%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Attack collection complete!
    echo [SUCCESS] Attack collection complete >> %LOGFILE%
    echo.
    echo --- Attack class distribution ---
    python -c "
import csv
from collections import Counter
counts = Counter()
with open(r'%OUTPUT%\master_dataset.csv') as f:
    for row in csv.DictReader(f):
        counts[row.get('ATTACK_NAME','?')] += 1
total = sum(counts.values())
print(f'  Total rows : {total:,}  (expected ~864000)')
print()
for name, cnt in sorted(counts.items(), key=lambda x: -x[1]):
    bar = '#' * int(cnt / total * 40)
    print(f'  {name:30s} {cnt:7,}  ({cnt/total*100:5.1f}%%)  {bar}')
print()
attack_rows = total - counts.get('Normal', 0)
print(f'  Attack total : {attack_rows:,}  ({attack_rows/total*100:.1f}%%)')
print(f'  Normal total : {counts.get(\"Normal\",0):,}  ({counts.get(\"Normal\",0)/total*100:.1f}%%)')
"
) else (
    echo.
    echo [ERROR] Collection failed  (exit code %ERRORLEVEL%)
    echo [ERROR] Collection failed >> %LOGFILE%
    echo.
    echo Troubleshooting:
    echo   1. Check logs\collect_attack_24h.log
    echo   2. Check %OUTPUT%\scheduler_execution.log
    echo   3. Verify CODESYS ping: ping %HOST%
)

echo [%DATE% %TIME%] Done >> %LOGFILE%
echo.
pause
