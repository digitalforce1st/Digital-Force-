# Digital Force -- Backend Launcher (PowerShell)
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Digital Force -- Full Stack Launcher" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Use system temp — do NOT override to D:\ (caused corrupt pip cache)
$env:PIP_NO_CACHE_DIR = "1"

$VENV   = "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\venv"
$PIP    = "$VENV\Scripts\pip.exe"
$PYTHON = "$VENV\Scripts\python.exe"
$NGROK  = "$VENV\Scripts\ngrok.exe"
$REQ    = "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend\requirements.txt"

# ── Step 1: Activate ────────────────────────────────────────────────────────
Write-Host "[1/4] Activating virtual environment..." -ForegroundColor White
& "$VENV\Scripts\Activate.ps1" 2>$null
Write-Host "      Done." -ForegroundColor Green

# ── Step 2: Package sync ────────────────────────────────────────────────────
Write-Host "[2/4] Syncing packages (no cache, 10s timeout)..." -ForegroundColor White
& $PIP install --quiet --no-cache-dir --no-warn-script-location `
    --timeout=10 --retries=1 `
    -r $REQ
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Packages OK." -ForegroundColor Green
} else {
    Write-Host "      Some packages unavailable - starting with installed versions." -ForegroundColor Yellow
}

# ── Step 3: Ngrok ──────────────────────────────────────────────────────────
Write-Host "[3/4] Starting Ngrok tunnel..." -ForegroundColor White
$env:NGROK_AUTHTOKEN = "3CTdhTZhb44Ddv3fw4DlQZRkjAs_2atEtEaWJKsbbMLaWbyu9"
if (Test-Path $NGROK) {
    Start-Process -FilePath $NGROK `
        -ArgumentList "http 8000 --domain=lunacy-unsettled-probe.ngrok-free.dev" `
        -WindowStyle Normal
    Write-Host "      Ngrok started." -ForegroundColor Green
} else {
    Write-Host "      WARNING: ngrok not found - tunnel skipped." -ForegroundColor Yellow
}

# ── Step 4: Backend ────────────────────────────────────────────────────────
Write-Host "[4/4] Starting Digital Force Backend..." -ForegroundColor White
Write-Host ""
Set-Location "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\backend"
& $PYTHON run_server.py
