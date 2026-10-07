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

:: The Ngrok auth token is a SECRET and must never be committed in this file.
:: Put it in your environment (PowerShell):  setx NGROK_AUTHTOKEN "your-token"   (then restart the shell)
if "%NGROK_AUTHTOKEN%"=="" (
    echo [ERROR] NGROK_AUTHTOKEN is not set in the environment.
    echo         Set it once:  setx NGROK_AUTHTOKEN "your-token"   (restart this shell after)
    echo         Skipping ngrok tunnel - the Gatekeeper still runs locally on 11435.
    goto :localonly
)
set "NGROK_AUTHTOKEN=%NGROK_AUTHTOKEN%"

:: Start ngrok to forward to the Gatekeeper port (11435) instead of Ollama directly
ngrok http 11435 --host-header="localhost:11435"
:localonly
pause
