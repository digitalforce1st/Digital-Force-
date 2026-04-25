@echo off
echo ================================================
echo  Digital Force -- Full Stack Launcher
echo ================================================
echo.

:: Use system temp — D:\pip-cache was causing corruption issues
set TEMP=%USERPROFILE%\AppData\Local\Temp
set TMP=%USERPROFILE%\AppData\Local\Temp
set PIP_NO_CACHE_DIR=1

echo [1/3] Activating virtual environment...
call "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\activate.bat"
echo Done.

echo [2/3] Checking for missing packages (no cache, fast timeout)...
"d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\pip.exe" ^
    install --quiet --no-cache-dir --no-warn-script-location ^
    --timeout=10 --retries=1 ^
    -r "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\requirements.txt"
if %ERRORLEVEL% EQU 0 (
    echo Done.
) else (
    echo   Some packages failed - starting anyway with what is installed.
)

echo [3/3] Starting Ngrok in a separate window...
set NGROK_AUTHTOKEN=3CTdhTZhb44Ddv3fw4DlQZRkjAs_2atEtEaWJKsbbMLaWbyu9
start "Ngrok Proxy" "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\ngrok.exe" http 8000 --domain=lunacy-unsettled-probe.ngrok-free.dev

echo [4/4] Starting Digital Force Backend...
echo.
cd /d "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend"
"d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\python.exe" run_server.py
