@echo off
:: Stub of start_hojaiga.bat [2/6] - same logic, echo instead of start, to verify
:: variable flow / fallback / overrides before trusting the real boot path.

echo === CASE A: defaults, Qwen3 absent in models\ (expect FALLBACK to 7B, -ngl 24) ===
set "HOJAIGA_VISION_GGUF="
set "HOJAIGA_VISION_MMPROJ="
set "HOJAIGA_VISION_NGL="
call :vision
echo.

echo === CASE B: overrides to existing dummy files (expect dummy path, -ngl 12) ===
echo dummy> "D:\new_automation\scratch\_stub_llm.gguf"
echo dummy> "D:\new_automation\scratch\_stub_mmproj.gguf"
set "HOJAIGA_VISION_GGUF=D:\new_automation\scratch\_stub_llm.gguf"
set "HOJAIGA_VISION_MMPROJ=D:\new_automation\scratch\_stub_mmproj.gguf"
call :vision
echo.

echo === CASE C: same + HOJAIGA_VISION_NGL=9 (expect -ngl 9) ===
set "HOJAIGA_VISION_NGL=9"
call :vision
del "D:\new_automation\scratch\_stub_llm.gguf" "D:\new_automation\scratch\_stub_mmproj.gguf" 2>NUL
exit /b 0

:vision
echo [2/6] Starting llama.cpp Vision Server (Qwen3-VL-8B, auto-fallback to Qwen2.5-VL-7B)...
set "VISION_GGUF=%HOJAIGA_VISION_GGUF%"
set "VISION_MMPROJ=%HOJAIGA_VISION_MMPROJ%"
set "VISION_NGL=%HOJAIGA_VISION_NGL%"
if "%VISION_GGUF%"=="" set "VISION_GGUF=D:\new_automation\models\Qwen3-VL-8B-Instruct-Q4_K_M.gguf"
if "%VISION_MMPROJ%"=="" set "VISION_MMPROJ=D:\new_automation\models\mmproj-Qwen3-VL-8B-Instruct-f16.gguf"
if "%VISION_NGL%"=="" set "VISION_NGL=12"
if not exist "%VISION_GGUF%" (
    echo   [FALLBACK] Qwen3-VL-8B GGUF not found - booting Qwen2.5-VL-7B instead ^(run models\download_qwen3_vl_8b.ps1 to upgrade^)
    set "VISION_GGUF=D:\new_automation\models\Qwen_Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
    set "VISION_MMPROJ=D:\new_automation\models\mmproj-Qwen_Qwen2.5-VL-7B-Instruct-f16.gguf"
    set "VISION_NGL=24"
)
echo   [..] Starting llama-server on port 8081: %VISION_GGUF% -ngl %VISION_NGL%
exit /b
