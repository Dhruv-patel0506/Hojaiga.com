@echo off
title Download llama.cpp and Qwen2.5-VL
color 0B
echo.
echo ========================================
echo   Automatic Download Script
echo ========================================
echo.
echo This will download:
echo 1. llama-bin-win-msvc-x64.zip (~150MB)
echo 2. Qwen2.5-VL-7B-Instruct GGUF (~4.5GB)
echo.
echo Total download size: ~4.7GB
echo.
echo Press any key to start downloads...
pause >nul

cd /d "D:\new_automation\llama.cpp"

echo.
echo [1/2] Downloading llama-bin-win-msvc-x64.zip...
echo Using latest release...
echo.
powershell -Command "$latest = (Invoke-WebRequest -Uri 'https://api.github.com/repos/ggerganov/llama.cpp/releases/latest' | ConvertFrom-Json).tag_name; Invoke-WebRequest -Uri \"https://github.com/ggerganov/llama.cpp/releases/download/$latest/llama-bin-win-msvc-x64.zip\" -OutFile 'llama-bin-win-msvc-x64.zip'"

if %errorlevel% neq 0 (
    echo ERROR: Failed to download llama.cpp automatically
    echo.
    echo Please download manually:
    echo 1. Visit: https://github.com/ggerganov/llama.cpp/releases/latest
    echo 2. Download: llama-bin-win-msvc-x64.zip
    echo 3. Extract to this folder
    echo.
    pause
    exit /b 1
)

echo.
echo Extracting llama-bin-win-msvc-x64.zip...
powershell -Command "Expand-Archive -Path 'llama-bin-win-msvc-x64.zip' -DestinationPath '.' -Force"

if %errorlevel% neq 0 (
    echo ERROR: Failed to extract
    pause
    exit /b 1
)

echo.
echo Cleaning up zip file...
del llama-bin-win-msvc-x64.zip

echo.
echo [2/2] Downloading Qwen2.5-VL-7B-Instruct GGUF...
echo This is a large file (~4.5GB) - please be patient...
echo.
powershell -Command "Invoke-WebRequest -Uri 'https://huggingface.co/Qwen/Qwen2.5-VL/resolve/main/Qwen2.5-VL-7B-Instruct-GGUF/qwen2.5-vl-7b-instruct-q4_k_m.gguf' -OutFile 'models\Qwen2.5-VL-7B-Instruct.GGUF'"

if %errorlevel% neq 0 (
    echo ERROR: Failed to download Qwen2.5-VL model
    echo.
    echo Please download manually:
    echo 1. Visit: https://huggingface.co/Qwen/Qwen2.5-VL
    echo 2. Download: qwen2.5-vl-7b-instruct-q4_k_m.gguf
    echo 3. Place in: models\ folder
    echo 4. Rename to: Qwen2.5-VL-7B-Instruct.GGUF
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Download Complete!
echo ========================================
echo.
echo Files downloaded:
echo - llama-server.exe (ready)
echo - Qwen2.5-VL-7B-Instruct.GGUF (ready)
echo.
echo Next steps:
echo 1. Run: start_llamacpp.bat
echo 2. Run: cd D:\new_automation\windows_ai_tutor
echo 3. Run: python src\core\app.py
echo.
pause