@echo off
echo ==============================================
echo Digital Force - Hybrid Architecture Launcher
echo ==============================================
echo.

:: Authenticate Ngrok
echo [1/3] Authenticating Ngrok...
.\ngrok.exe config add-authtoken 3CTdhTZhb44Ddv3fw4DlQZRkjAs_2atEtEaWJKsbbMLaWbyu9

:: Wait a second
timeout /t 2 /nobreak > nul

:: Start the Python backend in a separate terminal window
echo [2/3] Starting Python Backend Server...
start "Digital Force Backend" cmd /k "python run_server.py"

:: Wait a few seconds to ensure backend is fully online
timeout /t 4 /nobreak > nul

:: Start Ngrok in this current window
echo [3/3] Starting Secure Tunnel...
.\ngrok.exe http 8000
pause
