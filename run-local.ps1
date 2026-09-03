# DevVision AI — Local Development Runner (Windows PowerShell)
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Starting DevVision AI (Local Development)   " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Start Backend in separate process
$backendProcess = Start-Process -FilePath "backend\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --app-dir backend --reload --port 8000" -PassThru
Write-Host "[+] Backend API started on http://127.0.0.1:8000 (PID: $($backendProcess.Id))" -ForegroundColor Green

# 2. Start Frontend in separate process
$frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList "run dev -- --host 127.0.0.1 --port 5173" -WorkingDirectory "frontend" -PassThru
Write-Host "[+] Frontend started on http://127.0.0.1:5173 (PID: $($frontendProcess.Id))" -ForegroundColor Green

Write-Host "`nPress Ctrl+C or Enter to stop both servers..." -ForegroundColor Yellow
Read-Host

Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
Write-Host "[+] Servers stopped cleanly." -ForegroundColor Cyan