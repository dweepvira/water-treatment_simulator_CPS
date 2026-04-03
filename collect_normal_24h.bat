@echo off
REM ============================================================
REM  collect_normal_24h.bat  --  Day 1: Pure Normal Baseline
REM  Double-click this file to run.
REM  Window stays open until you press a key.
REM ============================================================

cd /d "%~dp0"

REM -- Python from conda test environment (full path avoids PATH issues)
set PYTHON=C:\Users\Dweep\miniconda3\envs\test\python.exe

set HOST=192.168.5.195
set PORT=1502
set MATLAB_PATH=C:\Users\Dweep\Documents\water-cps
set OUTPUT=data\normal_24h_hw
set TOTAL_MIN=1440

echo.
echo ============================================================
echo   SWaT  --  Normal 24-Hour Data Collection
echo   Host     : %HOST%:%PORT%
echo   Output   : %OUTPUT%\master_dataset.csv
echo   Duration : %TOTAL_MIN% min  (24 h)
echo   Python   : %PYTHON%
echo ============================================================
echo.

REM -- Verify python exists
if not exist "%PYTHON%" (
    echo [ERROR] Python not found at: %PYTHON%
    echo         Edit PYTHON= in this file to match your conda env.
    goto :done
)

REM -- Create output folder
if not exist "%OUTPUT%" mkdir "%OUTPUT%"
if not exist "logs"      mkdir "logs"

echo [%DATE% %TIME%] Starting normal collection... > logs\collect_normal_24h.log
echo.
echo Starting physics bridge + MATLAB. Please wait...
echo.

"%PYTHON%" start_system.py ^
    --host                 %HOST%          ^
    --port                 %PORT%          ^
    --reuse-existing-matlab                ^
    --matlab-path          "%MATLAB_PATH%" ^
    --output               "%OUTPUT%"      ^
    --total                %TOTAL_MIN%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Normal dataset collection complete!
    echo.
    "%PYTHON%" -c "import csv; r=sum(1 for _ in open(r'%OUTPUT%\master_dataset.csv'))-1; print(f'  Rows collected : {r:,}  (expected ~864000)')"
    echo [%DATE% %TIME%] SUCCESS >> logs\collect_normal_24h.log
) else (
    echo.
    echo [ERROR] Collection failed  --  exit code %ERRORLEVEL%
    echo         Check logs\collect_normal_24h.log for details.
    echo [%DATE% %TIME%] FAILED exit=%ERRORLEVEL% >> logs\collect_normal_24h.log
)

:done
echo.
echo Press any key to close this window...
pause >nul
