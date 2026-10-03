# Start llama.cpp vision server
$llamaPath = "C:\Users\dhruv\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
$modelPath = "D:\new_automation\models\Qwen_Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
$mmprojPath = "D:\new_automation\models\mmproj-Qwen_Qwen2.5-VL-7B-Instruct-f16.gguf"

Write-Host "Starting llama.cpp vision server..."
Start-Process -FilePath $llamaPath -ArgumentList "--model", "$modelPath", "--mmproj", "$mmprojPath", "--port", "8081", "--ctx-size", "4096", "-ngl", "24", "-t", "8", "-tb", "8", "-fa", "on", "-np", "1", "--host", "0.0.0.0" -WindowStyle Minimized

# Wait for server to start
Start-Sleep -Seconds 10
Write-Host "Vision server started on port 8081"
