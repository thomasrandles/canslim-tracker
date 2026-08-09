@echo off
setlocal enabledelayedexpansion
set "LOG=C:\CANSLIM\DayTrader\logs\options_scan_log.txt"

echo [%DATE% %TIME%] === OPTIONS SCAN START === >> "%LOG%"

REM -- Run the scanner (saves .txt and .json to DayTrader\outputs\)
"C:\Python314\python.exe" "C:\CANSLIM\scan_options.py"
echo [%DATE% %TIME%] Scanner exit: %ERRORLEVEL% >> "%LOG%"

REM -- Generate HTML dashboard
"C:\Python314\python.exe" "C:\CANSLIM\gen_options_html.py"
echo [%DATE% %TIME%] HTML generated: %ERRORLEVEL% >> "%LOG%"

REM -- Push to GitHub Pages
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM add Options_Dashboard.html
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM commit -m "Options scan update %DATE% %TIME%"
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM push
echo [%DATE% %TIME%] GitHub push exit: %ERRORLEVEL% >> "%LOG%"

echo [%DATE% %TIME%] === OPTIONS SCAN COMPLETE === >> "%LOG%"
endlocal
