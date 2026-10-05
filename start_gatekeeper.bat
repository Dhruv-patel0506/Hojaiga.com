@echo off
title Hojaiga Brain Gatekeeper + Aider
echo ============================================
echo   HOJAIGA BRAIN GATEKEEPER + AIDER
echo ============================================
echo Starting Gatekeeper on port 11435...
echo Protecting Ollama on port 11434.
echo.

REM Start Gatekeeper in background
start /B python D:\new_automation\Brain_Gatekeeper.py

REM Wait for Gatekeeper to be ready
timeout /t 3 /nobreak >nul

echo.
echo Starting Aider Code Architecture Hook...
echo Loading: database_manager.py, cns_bridge.py, Brain_Gatekeeper.py
echo.

REM Set Aider environment
set OLLAMA_API_BASE=http://127.0.0.1:11434
set OLLAMA_CONTEXT_LENGTH=16384

REM Launch Aider with key files
cd /d D:\new_automation\All codes
aider --model ollama_chat/llama3 core_organs\database_manager.py core_organs\cns_bridge.py Brain_Gatekeeper.py
