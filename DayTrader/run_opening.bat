@echo off
setlocal enabledelayedexpansion
cd /d "C:\CANSLIM\DayTrader"
set "LOG=logs\daytrader_log.txt"

echo [%DATE% %TIME%] === OPENING BELL SCAN START === >> "%LOG%"

REM Python writes to the log itself; do not redirect stdout here (causes file lock conflict)
"C:\Python314\python.exe" scanner_opening.py
echo [%DATE% %TIME%] Python scan exit: %ERRORLEVEL% >> "%LOG%"

"C:\Python314\python.exe" generate_dashboard.py
echo [%DATE% %TIME%] Dashboard updated >> "%LOG%"

REM Publish to GitHub Pages
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM add DayTrader/DayTrader_Dashboard.html
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM commit -m "DayTrader opening bell update %DATE% %TIME%"
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM push
echo [%DATE% %TIME%] GitHub push exit: %ERRORLEVEL% >> "%LOG%"
echo [%DATE% %TIME%] === OPENING BELL SCAN COMPLETE === >> "%LOG%"
endlocal
