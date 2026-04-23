# Digital Force — Fast Restart Script
# Run this whenever you change backend code.
# Kills the running uvicorn process and starts it fresh.
# Ngrok stays connected — backend is back online in < 5 seconds.

Write-Host "Restarting Digital Force backend..." -ForegroundColor Cyan

# Kill any running uvicorn processes
Get-Process -Name "python" -ErrorAction SilentlyContinue | 
    Where-Object { $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*main:app*" } | 
    Stop-Process -Force -ErrorAction SilentlyContinue

# Also kill by port 8000 if still running
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($port8000) {
    $port8000 | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Killed process on port 8000" -ForegroundColor Yellow
}

Start-Sleep -Milliseconds 500

# Start uvicorn WITHOUT --reload (reload causes the Ngrok disconnect problem)
# Changes require this script to be run again — takes < 5 seconds
Write-Host "Starting backend (no hot-reload — run this script after each change)..." -ForegroundColor Green

Set-Location "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend"

# Start in background so this script returns immediately
$venvPython = "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv\Scripts\python.exe"
Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info" -NoNewWindow

Start-Sleep -Seconds 3

# Quick health check
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "Backend is UP and healthy!" -ForegroundColor Green
        Write-Host "Ngrok is still connected — you're good to go." -ForegroundColor Green
    }
} catch {
    Write-Host "Backend started but health check not ready yet (give it 5 more seconds)" -ForegroundColor Yellow
}
