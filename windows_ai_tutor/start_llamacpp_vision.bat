@echo off
title Windows AI Tutor - llama.cpp Vision Server
cd /d "D:\new_automation"

REM Create models directory if not exists
if not exist "models" mkdir models

REM Check if model files exist
if not exist "models\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf" (
    echo ERROR: Main model not found!
    echo Please download from:
    echo hf download second-state/Qwen2.5-VL-7B-Instruct-GGUF Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf --local-dir D:\new_automation\models
    pause
    exit /b 1
)

if not exist "models\Qwen2.5-VL-7B-Instruct-vision.gguf" (
    echo ERROR: Vision projector not found!
    echo Please download from:
    echo hf download second-state/Qwen2.5-VL-7B-Instruct-GGUF Qwen2.5-VL-7B-Instruct-vision.gguf --local-dir D:\new_automation\models
    pause
    exit /b 1
)

echo Starting llama.cpp Vision Server with Qwen2.5-VL...
echo Main Model: Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf
echo Vision Projector: Qwen2.5-VL-7B-Instruct-vision.gguf
echo.

REM Start llama-server with vision support
"C:\Users\dhruv\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe" --model "D:\new_automation\models\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf" --mmproj "D:\new_automation\models\Qwen2.5-VL-7B-Instruct-vision.gguf" --port 8081 --ctx-size 4096 -ngl 24 -t 8 -tb 8 -fa on -np 1 --host 0.0.0.0

pause