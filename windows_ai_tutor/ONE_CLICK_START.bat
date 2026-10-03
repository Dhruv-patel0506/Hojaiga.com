@echo off
title Windows AI Tutor - One Click Start
color 0A
echo.
echo ========================================
echo   Windows AI Tutor - One Click Start
echo ========================================
echo.

cd /d "D:\new_automation\windows_ai_tutor"

REM Check Python
echo [Step 1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)
echo Python is installed
echo.

REM Check Ollama
echo [Step 2/4] Checking Ollama installation...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Ollama is not installed or not in PATH
    echo Please install Ollama from https://ollama.ai/
    pause
    exit /b 1
)
echo Ollama is installed
echo.

REM Start Ollama server
echo [Step 3/4] Starting Ollama server...
start "Ollama Server" cmd /k "ollama serve"
echo Waiting for Ollama server to start...
timeout /t 8 /nobreak >nul
echo Ollama server started
echo.

REM Check and pull model
echo [Step 4/4] Checking Qwen2.5-VL model...
echo Checking installed models...
ollama list > temp_models.txt 2>&1
findstr /i "qwen2.5-vl" temp_models.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo Qwen2.5-VL not found, pulling model...
    echo This will take a few minutes (downloading ~4GB)...
    echo Please wait...
    ollama pull qwen2.5-vl
    if %errorlevel% neq 0 (
        echo ERROR: Failed to pull Qwen2.5-VL model
        del temp_models.txt
        pause
        exit /b 1
    )
    echo Qwen2.5-VL model installed successfully
) else (
    echo Qwen2.5-VL model is already installed
)
del temp_models.txt
echo.

echo ========================================
echo   Starting Windows AI Tutor...
echo ========================================
echo.
echo INSTRUCTIONS:
echo - Look for the blue triangle icon in your system tray
echo - Press Ctrl+Alt to start talking
echo - Release Ctrl+Alt to send your question
echo - The AI can see your screen and help you learn
echo.
echo Press Ctrl+C here to stop the application
echo The Ollama server will continue running in the background
echo.

python src/core/app.py

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo   Application exited with error
    echo ========================================
    echo.
    echo Troubleshooting steps:
    echo 1. Make sure Ollama server is running: ollama serve
    echo 2. Check Python dependencies: pip install -r requirements.txt
    echo 3. Verify model installation: ollama list
    echo 4. Check Ollama connection: curl http://localhost:11434/api/tags
    echo.
)

pause