# Final Setup Guide - Using Your Existing llama.cpp

## ✅ Good News: You Already Have llama.cpp Installed!

**Location:** `C:\Users\dhruv\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe`

## 📥 Download These 2 Files (Required for Vision)

### File 1: Main Model (~4.5GB)
**Download Link:** https://huggingface.co/Qwen/Qwen2.5-VL/resolve/main/Qwen2.5-VL-7B-Instruct-GGUF/qwen2.5-vl-7b-instruct-q4_k_m.gguf
**Save as:** `D:\new_automation\models\Qwen_Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf`

### File 2: Vision Projector (~1.5GB) - REQUIRED for images!
**Download Link:** https://huggingface.co/Qwen/Qwen2.5-VL/resolve/main/Qwen2.5-VL-7B-Instruct-GGUF/mmproj-Qwen_Qwen2.5-VL-7B-Instruct-f16.gguf
**Save as:** `D:\new_automation\models\mmproj-Qwen_Qwen2.5-VL-7B-Instruct-f16.gguf`

## 🚀 After Downloading Both Files

### Step 1: Start llama.cpp Vision Server
```powershell
cd D:\new_automation\windows_ai_tutor
.\start_llamacpp_vision.bat
```

### Step 2: Start Windows AI Tutor
```powershell
cd D:\new_automation\windows_ai_tutor
python src\core\app.py
```

## 📊 Configuration Already Updated

Your `config/settings.json` is now configured to:
- Use your existing llama.cpp installation
- Use port 8081 (to avoid conflict with Hojaiga)
- Use vision projector for image support
- Model: Qwen2.5-VL-7B with Q4_K_M quantization

## 🎯 Why Two Files?

Qwen2.5-VL requires:
1. **Main Model** (Q4_K_M): The text generation model
2. **Vision Projector** (f16): The image understanding component

Both are required for the AI to see and understand your screen!

## 📋 Quick Summary

| What | Status |
|------|--------|
| llama.cpp installed | ✅ Already via WinGet |
| Main model | ⏳ Download (~4.5GB) |
| Vision projector | ⏳ Download (~1.5GB) |
| Configuration | ✅ Updated |
| Startup script | ✅ Created |

## 🎮 Startup Commands

After downloading both files:

**Terminal 1:**
```powershell
cd D:\new_automation\windows_ai_tutor
.\start_llamacpp_vision.bat
```

**Terminal 2:**
```powershell
cd D:\new_automation\windows_ai_tutor
python src\core\app.py
```

## 🔥 Benefits of This Setup

- ✅ Uses your existing llama.cpp (no reinstallation)
- ✅ Port 8081 (no conflict with Hojaiga on 8081)
- ✅ Vision support (can see your screen)
- ✅ GPU acceleration on RTX 3050
- ✅ Educational optimization with Qwen2.5-VL

**Download the 2 files and you're ready to go!**