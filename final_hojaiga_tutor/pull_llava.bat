@echo off
echo ========================================
echo Pulling LLaVA Vision Model
echo ========================================
echo.

set OLLAMA_INSTALL_DIR=D:\Ollama

echo Using Ollama from: %OLLAMA_INSTALL_DIR%
echo.

cd /d "%OLLAMA_INSTALL_DIR%"

REM Pull LLaVA model
echo Downloading LLaVA vision model (this may take a few minutes)...
echo.

ollama pull llava

echo.
echo ========================================
echo LLaVA Model Downloaded Successfully!
echo ========================================
echo.
echo Model is ready for use with Clicky Vision Platform.
echo.
pause
