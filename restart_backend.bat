@echo off
title Digital Force — Backend Restart
color 0A

echo.
echo  ==========================================
echo   Digital Force — Restarting Backend...
echo  ==========================================
echo.

:: Kill any process on port 8000
echo [1/3] Stopping old backend...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Also kill any lingering python/uvicorn processes
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq uvicorn*" >nul 2>&1

echo [2/3] Starting backend (no hot-reload)...
cd /d "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend"
start "Digital Force Backend" /B python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info

echo [3/3] Waiting for server to come up...
timeout /t 4 /nobreak >nul

:: Quick health check using curl (available on Windows 10+)
curl -s -o nul -w "%%{http_code}" http://localhost:8000/api/health > temp_status.txt 2>&1
set /p STATUS=<temp_status.txt
del temp_status.txt >nul 2>&1

if "%STATUS%"=="200" (
    echo.
    echo  ==========================================
    echo   Backend is UP! Status: %STATUS%
    echo   Ngrok tunnel is still connected.
    echo   You are good to go!
    echo  ==========================================
) else (
    echo.
    echo  Backend starting... (give it 5 more seconds)
    echo  If it still fails, check the backend window for errors.
)

echo.
pause
