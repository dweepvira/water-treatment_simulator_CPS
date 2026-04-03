@echo off
REM ============================================================
REM  collect_attack_24h.bat  --  Day 2: Attack Dataset
REM  Double-click this file to run.
REM  Window stays open until you press a key.
REM ============================================================

cd /d "%~dp0"

REM -- Python from conda test environment (full path avoids PATH issues)
set PYTHON=C:\Users\Dweep\miniconda3\envs\test\python.exe

set HOST=192.168.5.194
set PORT=1502
set MATLAB_PATH=C:\Users\Dweep\Documents\water-cps
set OUTPUT=data\attack_24h_hw
set TOTAL_MIN=1440
set ATTACK_SCRIPT=attack_schedular_24h.py

echo.
echo ============================================================
echo   SWaT  --  Attack 24-Hour Data Collection
echo   Host     : %HOST%:%PORT%
echo   Output   : %OUTPUT%\master_dataset.csv
echo   Duration : %TOTAL_MIN% min  (24 h)
echo   Attacks  : All 9 types  (~45%% of rows)
echo   Python   : %PYTHON%
echo ============================================================
echo.

REM -- Verify python exists
if not exist "%PYTHON%" (
    echo [ERROR] Python not found at: %PYTHON%
    echo         Edit PYTHON= in this file to match your conda env.
    goto :done
)

REM -- Create output folder first (before lockfile check uses it)
if not exist "%OUTPUT%" mkdir "%OUTPUT%"
if not exist "logs"      mkdir "logs"

REM -- Check for stale lockfile from a previous crashed run
if exist "%OUTPUT%\attack_scheduler.lock" (
    echo [WARNING] Stale lockfile found: %OUTPUT%\attack_scheduler.lock
    echo.
    echo   This means a previous run crashed without cleaning up.
    echo   Deleting stale lock and continuing...
    del "%OUTPUT%\attack_scheduler.lock"
    echo   Lock deleted.
    echo.
)

echo [%DATE% %TIME%] Starting attack collection... > logs\collect_attack_24h.log
echo.
echo Starting physics bridge + MATLAB + attack scheduler. Please wait...
echo.

"%PYTHON%" start_system.py ^
    --host                 %HOST%           ^
    --port                 %PORT%           ^
    --reuse-existing-matlab                 ^
    --matlab-path          "%MATLAB_PATH%"  ^
    --output               "%OUTPUT%"       ^
    --total                %TOTAL_MIN%      ^
    --attack-script        %ATTACK_SCRIPT%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Attack dataset collection complete!
    echo.
    echo --- Attack class distribution ---
    "%PYTHON%" -c "
import csv
from collections import Counter
try:
    counts = Counter()
    with open(r'%OUTPUT%\master_dataset.csv') as f:
        for row in csv.DictReader(f):
            counts[row.get('ATTACK_NAME','Unknown')] += 1
    total = sum(counts.values())
    print(f'  Total rows : {total:,}')
    print()
    for name, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        bar = '#' * int(pct / 2)
        print(f'  {name:30s}  {cnt:7,}  ({pct:5.1f}%%)  {bar}')
    atk = total - counts.get('Normal', 0)
    print()
    print(f'  Attack rows : {atk:,}  ({atk/total*100:.1f}%%)')
    print(f'  Normal rows : {counts.get(chr(78)+chr(111)+chr(114)+chr(109)+chr(97)+chr(108),0):,}')
except Exception as e:
    print(f'  Could not parse CSV: {e}')
"
    echo [%DATE% %TIME%] SUCCESS >> logs\collect_attack_24h.log
) else (
    echo.
    echo [ERROR] Collection failed  --  exit code %ERRORLEVEL%
    echo.
    echo Troubleshooting:
    echo   1. Is CODESYS reachable?  ping %HOST%
    echo   2. Is MATLAB running?     Check port 9501
    echo   3. See logs: %OUTPUT%\scheduler_execution.log
    echo [%DATE% %TIME%] FAILED exit=%ERRORLEVEL% >> logs\collect_attack_24h.log
)

:done
echo.
echo Press any key to close this window...
pause >nul
