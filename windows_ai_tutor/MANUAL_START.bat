@echo off
title Windows AI Tutor - Manual Start
color 0A
echo.
echo ========================================
echo   Windows AI Tutor - Manual Start
echo ========================================
echo.
echo Please follow these steps one by one:
echo.
echo Step 1: Start Ollama Server
echo   Command: ollama serve
echo   (Open a new terminal and run this command)
echo.
echo Step 2: Pull Qwen2.5-VL Model
echo   Command: ollama pull qwen2.5-vl
echo   (Run this in another terminal after Step 1)
echo.
echo Step 3: Start Windows AI Tutor
echo   Command: python src/core/app.py
echo   (Run this in another terminal after Step 2)
echo.
echo Press any key to launch Step 1 automatically...
pause >nul

echo.
echo Starting Ollama server...
start "Ollama Server" cmd /k "ollama serve"
echo.
echo Ollama server started in a new window.
echo.
echo Please wait 10 seconds, then run these commands in a NEW terminal:
echo.
echo   cd D:\new_automation\windows_ai_tutor
echo   ollama pull qwen2.5-vl
echo   python src/core/app.py
echo.
pause