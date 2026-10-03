# Infinite Void Launcher for PowerShell
cd "d:\new_automation\All codes"

Write-Host "Starting Infinite Void Server..." -ForegroundColor Cyan
Start-Process python -ArgumentList "infinite_void_server.py" -WindowStyle Hidden

Write-Host "Waiting for server to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

Write-Host "Opening browser..." -ForegroundColor Cyan
Start-Process "infinite_void_react.html"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "INFINITE VOID IS READY!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Enter any topic in the browser and click 'Teach Me'"
Write-Host "Press Ctrl+C to stop the server"
Write-Host ""

# Keep running
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Host ""
    Write-Host "Stopping server..." -ForegroundColor Yellow
    Get-Process python | Where-Object {$_.MainWindowTitle -like "*infinite_void*"} | Stop-Process -Force
    Write-Host "Server stopped. Goodbye!" -ForegroundColor Green
}
