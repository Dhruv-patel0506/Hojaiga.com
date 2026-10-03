@echo off
cd /d "d:\new_automation\All codes"
echo Starting Infinite Void Server...
start /B python infinite_void_server.py
timeout /t 2 /nobreak >nul
echo Opening Infinite Void in browser...
start infinite_void_react.html
echo.
echo Infinite Void is ready!
echo Press Ctrl+C to stop the server when done.
python -c "import time; input('Press Enter to stop server...')" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq infinite_void_server*" 2>nul
