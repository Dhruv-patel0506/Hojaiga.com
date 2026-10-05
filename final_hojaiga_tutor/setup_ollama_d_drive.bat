@echo off
echo ========================================
echo Clicky Vision Platform - Ollama Setup
echo ========================================
echo.

REM Set Ollama installation directory to D drive
set OLLAMA_INSTALL_DIR=D:\Ollama

echo Installing Ollama to D: drive...
echo.

REM Create directory
if not exist "%OLLAMA_INSTALL_DIR%" mkdir "%OLLAMA_INSTALL_DIR%"

REM Download Ollama for Windows
echo Downloading Ollama installer...
powershell -Command "Invoke-WebRequest -Uri 'https://ollama.ai/download/OllamaSetup.exe' -OutFile '%TEMP%\OllamaSetup.exe'"

REM Install silently to D drive
echo Installing Ollama to %OLLAMA_INSTALL_DIR%...
start /wait "" "%TEMP%\OllamaSetup.exe" /S /D=%OLLAMA_INSTALL_DIR%

REM Set environment variables
setx OLLAMA_HOME "%OLLAMA_INSTALL_DIR%"
setx PATH "%PATH%;%OLLAMA_INSTALL_DIR%"

echo.
echo Ollama installed to D: drive successfully!
echo.
echo Now pulling LLaVA vision model...
echo.

REM Change to Ollama directory
cd /d "%OLLAMA_INSTALL_DIR%"

REM Pull LLaVA model
ollama pull llava

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Ollama is installed at: %OLLAMA_INSTALL_DIR%
echo LLaVA model is downloaded and ready.
echo.
echo To start Ollama server, run:
echo   cd /d "%OLLAMA_INSTALL_DIR%"
echo   ollama serve
echo.
echo Or use the provided start_ollama.bat script
echo.
pause
