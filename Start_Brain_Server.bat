@echo off
title Hojaiga Brain Server (Ngrok + Gatekeeper)
color 0B

echo ==================================================
echo       STARTING HOJAIGA BRAIN SERVER 
echo ==================================================
echo.

echo [1/3] Verifying Ollama is running...
curl -s http://127.0.0.1:11434/ >nul
if %errorlevel% neq 0 (
    echo [WARNING] Ollama doesn't seem to be responding on port 11434. 
    echo Please make sure Ollama is installed and running!
) else (
    echo [OK] Ollama is running perfectly.
)
echo.

echo [2/3] Starting the Brain Gatekeeper Proxy...
start "Hojaiga Brain Gatekeeper" cmd /c "python D:\new_automation\Brain_Gatekeeper.py"
echo [OK] Gatekeeper is running on port 11435.
echo.

echo [3/3] Exposing Gatekeeper to the Internet via Ngrok...
echo.
echo ==================================================
echo INSTRUCTIONS:
echo 1. Ngrok will open in a new window.
echo 2. Look for the "Forwarding" URL (https://....ngrok-free.app)
echo 3. On the OTHER laptop, run this before starting the automation:
echo.
echo $env:HOJAIGA_BRAIN_URL = "https://your-url.ngrok-free.app/api/chat"
echo ==================================================
echo.
echo Starting Ngrok... (Keep both windows open!)
echo.

:: Authenticate Ngrok instantly using the Environment Variable approach
set NGROK_AUTHTOKEN=3I0gQkLMtTojKsLPYDDffqxfQCa_5523Pxh29Sw1j79ghrwjj

:: Start ngrok to forward to the Gatekeeper port (11435) instead of Ollama directly
ngrok http 11435 --host-header="localhost:11435"
pause
