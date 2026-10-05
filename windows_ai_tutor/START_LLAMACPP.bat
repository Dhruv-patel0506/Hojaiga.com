@echo off
title Windows AI Tutor - llama.cpp Startup
color 0B
echo.
echo ========================================
echo   Windows AI Tutor - llama.cpp Mode
echo ========================================
echo.
echo RECOMMENDED: Qwen2.5-VL (better than LLaVA-LLaMA3)
echo.
echo Why Qwen2.5-VL is better for your holographic AI tutor:
echo - Educational optimization (designed for teaching)
echo - Better vision understanding (more accurate screen interpretation)
echo - Slightly faster performance (better real-time response)
echo - Smaller footprint (more resources for other features)
echo.
echo ========================================
echo   Startup Steps
echo ========================================
echo.
echo Step 1: Download llama.cpp
echo   Visit: https://github.com/ggerganov/llama.cpp/releases
echo   Download: llama-bin-win-msvc-x64.zip
echo   Extract to: D:\new_automation\llama.cpp
echo.
echo Step 2: Download Qwen2.5-VL GGUF model
echo   Visit: https://huggingface.co/Qwen/Qwen2.5-VL
echo   Download: Qwen2.5-VL-7B-Instruct-GGUF
echo   Place in: D:\new_automation\llama.cpp\models
echo.
echo Step 3: Start llama.cpp server
echo   Command: cd D:\new_automation\llama.cpp
echo            llama-server.exe --model models\Qwen2.5-VL-7B-Instruct-GGUF --port 8080
echo.
echo Step 4: Update configuration
echo   Set "backend": "llamacpp" in config/settings.json
echo.
echo Step 5: Start Windows AI Tutor
echo   Command: python src/core/app.py
echo.
echo PRESS ANY KEY TO OPEN DOWNLOAD PAGES...
pause >nul

echo.
echo Opening llama.cpp releases page...
start https://github.com/ggerganov/llama.cpp/releases

timeout /t 2 /nobreak >nul

echo.
echo Opening Qwen2.5-VL model page...
start https://huggingface.co/Qwen/Qwen2.5-VL

echo.
echo ========================================
echo   Manual Setup Instructions
echo ========================================
echo.
echo After downloading:
echo.
echo 1. Extract llama.cpp to: D:\new_automation\llama.cpp
echo 2. Download Qwen2.5-VL GGUF to: D:\new_automation\llama.cpp\models
echo 3. Run: cd D:\new_automation\llama.cpp
echo 4. Run: llama-server.exe --model models\Qwen2.5-VL-7B-Instruct-GGUF --port 8080
echo 5. Update config settings.json to use llamacpp backend
echo 6. Run: python src/core/app.py
echo.
pause