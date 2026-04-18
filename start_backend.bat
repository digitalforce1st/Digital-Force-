@echo off
echo ================================================
echo  Digital Force -- Full Stack Launcher
echo ================================================
echo.

:: Force ALL build/temp/rust paths to D: drive
set TEMP=D:\tmp
set TMP=D:\tmp
set PIP_CACHE_DIR=D:\pip-cache
mkdir D:\tmp 2>nul

echo [1/3] Activating virtual environment...
call "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\activate.bat"
echo Done.

echo [2/3] Checking for missing packages...
"d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\pip.exe" install --no-cache-dir --only-binary=:all: -q -r "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\requirements.txt"
echo Done.

echo [3/3] Starting Ngrok in a separate window...
set NGROK_AUTHTOKEN=3CTdhTZhb44Ddv3fw4DlQZRkjAs_2atEtEaWJKsbbMLaWbyu9
start "Ngrok Proxy" "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\ngrok.exe" http 8000 --domain=lunacy-unsettled-probe.ngrok-free.dev

echo [4/4] Starting Digital Force Backend...
echo.
cd /d "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend"
"d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\python.exe" run_server.py
