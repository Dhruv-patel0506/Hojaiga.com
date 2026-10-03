@echo off
title llama.cpp Server - Qwen2.5-VL
cd /d "D:\new_automation\llama.cpp"
llama-server.exe --model models\Qwen2.5-VL-7B-Instruct.GGUF --port 8080 --ctx-size 8192 --n-gpu-layers 99 --threads 8
pause