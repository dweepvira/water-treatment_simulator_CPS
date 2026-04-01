@echo off
REM ============================================================
REM  collect_normal_24h.bat  —  Day 1: Pure Normal Baseline
REM  Output : data\normal_24h_hw\master_dataset.csv
REM  Rows   : ~864,000 @ 10 Hz over 24 h
REM  Labels : ALL rows ATTACK_ID=0 / ATTACK_NAME=Normal
REM
REM  PRE-CHECKS (do these before double-clicking):
REM    1. CODESYS is running and REACHABLE at 192.168.5.194:1502
REM    2. MATLAB swat_physics_server.m is already running
REM       (if not, remove the --reuse-existing-matlab flag below)
REM    3. No other collection is using this output folder
REM ============================================================

setlocal
cd /d "%~dp0"

set HOST=192.168.5.194
set PORT=1502
set MATLAB_PATH=C:\Users\Dweep\Documents\water-cps
set OUTPUT=data\normal_24h_hw
set TOTAL_MIN=1440
set LOGFILE=logs\collect_normal_24h.log

echo.
echo ============================================================
echo   SWaT  --  Normal 24-Hour Data Collection
echo   Host     : %HOST%:%PORT%
echo   Output   : %OUTPUT%\master_dataset.csv
echo   Duration : %TOTAL_MIN% min (24 h)
echo ============================================================
echo.

if not exist logs   mkdir logs
if not exist %OUTPUT% mkdir %OUTPUT%

echo [%DATE% %TIME%] Starting normal 24h collection >> %LOGFILE%

python start_system.py ^
    --host               %HOST%            ^
    --port               %PORT%            ^
    --reuse-existing-matlab                ^
    --matlab-path        "%MATLAB_PATH%"   ^
    --output             %OUTPUT%          ^
    --total              %TOTAL_MIN%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Normal collection complete!
    echo [SUCCESS] Normal collection complete >> %LOGFILE%
    echo.
    echo Rows in CSV:
    python -c "
with open(r'%OUTPUT%\master_dataset.csv') as f:
    rows = sum(1 for _ in f) - 1
print(f'  Total rows : {rows:,}')
print(f'  Expected   : ~864000')
print('  All rows should be ATTACK_ID=0 / ATTACK_NAME=Normal')
"
) else (
    echo.
    echo [ERROR] Collection failed  (exit code %ERRORLEVEL%)
    echo [ERROR] Collection failed >> %LOGFILE%
    echo Check logs\collect_normal_24h.log for details.
)

echo [%DATE% %TIME%] Done >> %LOGFILE%
echo.
pause
