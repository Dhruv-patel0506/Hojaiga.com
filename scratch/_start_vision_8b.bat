@echo off
:: Start Qwen3-VL-8B vision board on :8081 with exact start_hojaiga.bat flags
"C:\Users\dhruv\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe" --model "D:\new_automation\models\Qwen3-VL-8B-Instruct-Q4_K_M.gguf" --mmproj "D:\new_automation\models\mmproj-Qwen3-VL-8B-Instruct-f16.gguf" --port 8081 --ctx-size 4096 -ngl 12 -t 8 -tb 8 -fa on -np 1 --image-min-tokens 1024 --host 127.0.0.1 >> "D:\new_automation\scratch\_vision8081_8b.log" 2>&1
