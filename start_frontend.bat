@echo off
echo Starting Digital Force frontend...
cd /d "d:\KASHIRI BRIGHTON\BUSINESS\AiiA\Digital Force\frontend"

if not exist node_modules (
    echo Installing npm packages...
    npm install
)

echo.
echo Starting Next.js dev server on port 3000...
npm run dev
