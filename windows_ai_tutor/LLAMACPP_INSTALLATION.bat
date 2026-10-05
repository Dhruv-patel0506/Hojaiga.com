@echo off
title Windows AI Tutor - llama.cpp Installation
color 0B
echo.
echo ========================================
echo   llama.cpp + Qwen2.5-VL Installation
echo ========================================
echo.
echo This will set up llama.cpp with Qwen2.5-VL for MAXIMUM performance on your RTX 3050
echo.

cd /d "D:\new_automation"

REM Create llama.cpp directory
echo [Step 1/5] Creating llama.cpp directory...
if not exist "llama.cpp" mkdir llama.cpp
cd llama.cpp
echo Directory created
echo.

REM Download llama.cpp
echo [Step 2/5] Downloading llama.cpp...
echo Visit: https://github.com/ggerganov/llama.cpp/releases
echo Download: llama-bin-win-msvc-x64.zip
echo.
echo Opening download page...
start https://github.com/ggerganov/llama.cpp/releases/latest
echo.
echo After downloading:
echo 1. Extract llama-bin-win-msvc-x64.zip to this directory
echo 2. The extracted folder should contain llama-server.exe
echo.
pause

REM Create models directory
echo [Step 3/5] Creating models directory...
if not exist "models" mkdir models
echo Models directory created
echo.

REM Download Qwen2.5-VL GGUF model
echo [Step 4/5] Downloading Qwen2.5-VL GGUF model...
echo Visit: https://huggingface.co/Qwen/Qwen2.5-VL
echo Look for: Qwen2.5-VL-7B-Instruct-GGUF
echo.
echo Opening model page...
start https://huggingface.co/Qwen/Qwen2.5-VL
echo.
echo After downloading:
echo 1. Place the GGUF file in: D:\new_automation\llama.cpp\models\
echo 2. Rename it to: Qwen2.5-VL-7B-Instruct.GGUF
echo.
pause

REM Create startup script
echo [Step 5/5] Creating startup script...
echo @echo off > start_llamacpp.bat
echo cd /d "D:\new_automation\llama.cpp" >> start_llamacpp.bat
echo llama-server.exe --model models\Qwen2.5-VL-7B-Instruct.GGUF --port 8080 --ctx-size 8192 --n-gpu-layers 99 >> start_llamacpp.bat
echo pause >> start_llamacpp.bat
echo Startup script created: start_llamacpp.bat
echo.

echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo NEXT STEPS:
echo 1. Extract llama-bin-win-msvc-x64.zip to this directory
echo 2. Download Qwen2.5-VL-7B-Instruct.GGUF to models\ folder
echo 3. Run: start_llamacpp.bat
echo 4. Update config\settings.json: set "backend": "llamacpp"
echo 5. Run: python src\core\app.py
echo.
pause