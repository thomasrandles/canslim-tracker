@echo off
setlocal enabledelayedexpansion
cd /d "C:\CANSLIM"

set "LOG=canslim_log.txt"
set "SCREEN=C:\CANSLIM\screen_output.json"
REM Minimum believable size for a real screen. A healthy run is ~80 KB.
set "MINBYTES=5000"

echo [%DATE% %TIME%] Starting CANSLIM run >> "%LOG%"

REM ============================================================
REM  Step 1: screen via Python (direct TradingView API - no Claude tokens)
REM ============================================================
"C:\Python314\python.exe" screen_stocks.py >> "%LOG%" 2>&1
echo [%DATE% %TIME%] Screen done - exit code: %ERRORLEVEL% >> "%LOG%"

REM ------------------------------------------------------------
REM  GUARD: screen_output.json must exist and be a real result.
REM ------------------------------------------------------------
set "SIZE=0"
if exist "%SCREEN%" for %%A in ("%SCREEN%") do set "SIZE=%%~zA"

if not exist "%SCREEN%" (
    echo [%DATE% %TIME%] ERROR: screen step produced NO screen_output.json. >> "%LOG%"
    echo [%DATE% %TIME%] CANSLIM run FAILED >> "%LOG%"
    exit /b 1
)
if !SIZE! LSS %MINBYTES% (
    echo [%DATE% %TIME%] ERROR: screen_output.json is only !SIZE! bytes ^(min %MINBYTES%^) - empty/garbage. >> "%LOG%"
    echo [%DATE% %TIME%] CANSLIM run FAILED >> "%LOG%"
    exit /b 1
)
echo [%DATE% %TIME%] Screen OK - screen_output.json = !SIZE! bytes >> "%LOG%"

if not exist "C:\CANSLIM\archive" mkdir "C:\CANSLIM\archive"
copy /Y "%SCREEN%" "C:\CANSLIM\archive\screen_last.json" >> "%LOG%" 2>&1

REM ============================================================
REM  Step 2: write to Notion
REM ============================================================
"C:\Python314\python.exe" notion_writer.py >> "%LOG%" 2>&1
set "NWRC=%ERRORLEVEL%"
echo [%DATE% %TIME%] Notion writer done - exit code: %NWRC% >> "%LOG%"
if not "%NWRC%"=="0" (
    echo [%DATE% %TIME%] ERROR: notion_writer.py failed ^(exit %NWRC%^) - screen_output.json kept for retry. >> "%LOG%"
    echo [%DATE% %TIME%] CANSLIM run FAILED >> "%LOG%"
    exit /b 1
)
del "%SCREEN%" >> "%LOG%" 2>&1

REM ============================================================
REM  Step 3: regenerate dashboard
REM ============================================================
"C:\Python314\python.exe" generate_dashboard.py >> "%LOG%" 2>&1
set "DASHRC=%ERRORLEVEL%"
echo [%DATE% %TIME%] Dashboard regenerated - exit code: %DASHRC% >> "%LOG%"

if not "%DASHRC%"=="0" (
    echo [%DATE% %TIME%] ERROR: dashboard regen failed - skipping git push. >> "%LOG%"
    echo [%DATE% %TIME%] CANSLIM run FAILED >> "%LOG%"
    exit /b 1
)

REM ============================================================
REM  Step 4: publish
REM ============================================================
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM add CANSLIM_Dashboard.html >> "%LOG%" 2>&1
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM commit -m "Daily update %DATE%" >> "%LOG%" 2>&1
"C:\Program Files\Git\cmd\git.exe" -C C:\CANSLIM push >> "%LOG%" 2>&1
echo [%DATE% %TIME%] Git push done - exit code: %ERRORLEVEL% >> "%LOG%"

echo %DATE% %TIME% > "C:\CANSLIM\last_success.txt"
echo [%DATE% %TIME%] CANSLIM run complete >> "%LOG%"
endlocal
