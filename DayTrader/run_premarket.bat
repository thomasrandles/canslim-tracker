@echo off
setlocal enabledelayedexpansion
cd /d "C:\CANSLIM\DayTrader"
set "LOG=logs\daytrader_log.txt"

echo [%DATE% %TIME%] === PRE-MARKET SCAN START === >> "%LOG%"

REM Step 1: Python broad scan (Python writes to log itself; don't redirect here)
"C:\Python314\python.exe" scanner_premarket.py
echo [%DATE% %TIME%] Python scan exit: %ERRORLEVEL% >> "%LOG%"

REM Step 2: TradingView deep scan on top candidates (uses Claude + TradingView MCP)
if exist "outputs\premarket_latest.json" (
    echo [%DATE% %TIME%] Starting TradingView deep scan... >> "%LOG%"
    call "C:\Users\Tom Randles\AppData\Roaming\npm\claude.cmd" -p --dangerously-skip-permissions -m claude-fable-5 < "prompts\premarket_tv_prompt.txt" > "outputs\tv_premarket_output.txt" 2>&1
    echo [%DATE% %TIME%] TradingView scan exit: %ERRORLEVEL% >> "%LOG%"
)

REM Step 3: Generate dashboard
"C:\Python314\python.exe" generate_dashboard.py
echo [%DATE% %TIME%] === PRE-MARKET SCAN COMPLETE === >> "%LOG%"
endlocal
