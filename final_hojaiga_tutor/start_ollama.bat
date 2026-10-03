@echo off
echo ========================================
echo Starting Ollama Server
echo ========================================
echo.

set OLLAMA_INSTALL_DIR=D:\Ollama

echo Starting Ollama from: %OLLAMA_INSTALL_DIR%
echo.

cd /d "%OLLAMA_INSTALL_DIR%"

REM Start Ollama server
ollama serve

pause
