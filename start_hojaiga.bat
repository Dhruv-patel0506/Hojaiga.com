@echo off
title Hojaiga OS - CrewAI Autonomous Multi-Agent Swarm
color 0A

:: Set virtual environment path
set HOJAIGA_VENV=D:\new_automation\hojaiga_env
set HOJAIGA_PYTHON=%HOJAIGA_VENV%\Scripts\python.exe
set HOJAIGA_PIP=%HOJAIGA_VENV%\Scripts\pip.exe

echo ============================================================
echo       HOJAIGA OS - CREWAI AUTONOMOUS SWARM BOOT
echo ============================================================
echo [VENV] Using virtual environment: %HOJAIGA_VENV%
echo.

:: ------------------------------------------------------------
:: [1/6] Verify / Start Ollama Runtime (Port 11434)
:: ------------------------------------------------------------
echo [1/6] Checking Ollama on port 11434...
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri http://127.0.0.1:11434/api/tags -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop)|Out-Null; exit 0}catch{exit 1}"
if %ERRORLEVEL% EQU 0 (
    echo   [OK] Ollama is already running on port 11434.
) else (
    echo   [..] Starting Ollama server...
    start "" ollama serve
    ping -n 5 127.0.0.1 >nul
    echo   [OK] Ollama server started.
)

:: ------------------------------------------------------------
:: [2/6] Start llama.cpp Vision Server (Port 8081)
:: ------------------------------------------------------------
echo.
echo [2/6] Starting llama.cpp Vision Server (Qwen3-VL-8B, auto-fallback to Qwen2.5-VL-7B)...
tasklist /FI "IMAGENAME eq llama-server.exe" 2>NUL | find /I "llama-server.exe" >NUL
if %ERRORLEVEL% EQU 0 (
    echo   [OK] llama-server already running.
    goto :vision_ready
)
:: Fail-safe model auto-select: prefer the smarter Qwen3-VL-8B (extra layers spill to the
:: 32GB RAM on this 6GB-VRAM box); keep booting today's Qwen2.5-VL-7B until it is downloaded
:: via models\download_qwen3_vl_8b.ps1 - boot NEVER breaks on a missing upgrade file.
:: HOJAIGA_VISION_GGUF / HOJAIGA_VISION_MMPROJ / HOJAIGA_VISION_NGL override these defaults.
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
start /min "" "C:\Users\dhruv\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe" --model "%VISION_GGUF%" --mmproj "%VISION_MMPROJ%" --port 8081 --ctx-size 4096 -ngl %VISION_NGL% -t 8 -tb 8 -fa on -np 1 --host 0.0.0.0
echo   [..] Waiting for vision server to load model...
ping -n 35 127.0.0.1 >nul
echo   [OK] Vision server started on port 8081.
:vision_ready

:: ------------------------------------------------------------
:: [3/6] Configure Environment for CrewAI Swarm and Vision
:: ------------------------------------------------------------
echo.
echo [3/6] Configuring environment (CrewAI Multi-Agent Swarm)...
set HOJAIGA_ENGINE=crewai
set HOJAIGA_CREWAI_MODEL=qwen2.5:7b
set HOJAIGA_CREWAI_BACKEND=ollama
set CREWAI_TRACING_ENABLED=false
set HOJAIGA_VISION_MODEL=qwen2.5vl:3b
set HOJAIGA_VISION_REASON_MODEL=qwen2.5vl:3b
set HOJAIGA_VISION_PRECISION_ENDPOINT=http://localhost:8081
set OPENAI_API_KEY=sk-dummy
set HOJAIGA_HEADLESS=0
set HOJAIGA_STEALTH_MODE=0
set HOJAIGA_VISION_URL=http://127.0.0.1:11434/api/chat
set HOJAIGA_BRAIN_MODEL=qwen2.5:7b
set HOJAIGA_SMALL_MODEL=qwen2.5vl:3b
set HOJAIGA_BRAIN_URL=http://127.0.0.1:11435/api/chat
set HOJAIGA_AUTO_LAUNCH=1
set PYTHONUNBUFFERED=1

echo   Engine:        HOJAIGA_ENGINE=crewai
echo   CrewAI Model:  HOJAIGA_CREWAI_MODEL=qwen2.5:7b (local reasoning model)
echo   Vision Model:  HOJAIGA_VISION_MODEL=qwen2.5vl:3b (Grounding Ready)
echo   Vision Prec:   HOJAIGA_VISION_PRECISION_ENDPOINT=http://localhost:8081
echo   Browser Mode:  HOJAIGA_HEADLESS=0 (Visible Desktop Chrome)
echo   Window Mode:   HOJAIGA_STEALTH_MODE=0 (Visible Desktop Windows)
echo   [OK] Environment variables set.

:: ------------------------------------------------------------
:: [4/6] Start Gatekeeper Security Proxy (Port 11435)
:: ------------------------------------------------------------
echo.
echo [4/6] Starting Gatekeeper Proxy on port 11435...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Brain_Gatekeeper*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
ping -n 2 127.0.0.1 >nul
start "Hojaiga Gatekeeper (Port 11435)" cmd /k "cd /d D:\new_automation & %HOJAIGA_PYTHON% -u Brain_Gatekeeper.py"
ping -n 3 127.0.0.1 >nul
powershell -NoProfile -Command "try{(Get-NetTCPConnection -LocalPort 11435 -ErrorAction Stop)|Out-Null; exit 0}catch{exit 1}"
if %ERRORLEVEL% EQU 0 (
    echo   [OK] Gatekeeper started and listening on port 11435.
) else (
    echo   [!] Gatekeeper is starting up on port 11435...
)

:: ------------------------------------------------------------
:: [5/6] Start Hojaiga Edge Avatar + Teaching Void - DISABLED
:: ------------------------------------------------------------
echo.
echo [5/6] Skipping Hojaiga edge avatar and teaching Void (disabled by user)...
echo   [SKIPPED] Avatar and teaching void not started.

:: ------------------------------------------------------------
:: [6/6] Living Interface Visualizer 2 (Frontend Monitor + CNS Server) - DISABLED
:: ------------------------------------------------------------
echo.
echo [6/6] Skipping Living Interface Visualizer 2 (disabled by user)...
echo   [SKIPPED] Visualizer and CNS server not started.

:: ------------------------------------------------------------
:: [BOOT HEALTH] One honest line per service and organ (ready / degraded / absent)
:: ------------------------------------------------------------
echo.
echo [health] Probing services and organs...
"%HOJAIGA_PYTHON%" -u "D:\new_automation\All codes\core_organs\boot_health.py"
if %ERRORLEVEL% NEQ 0 (
    echo   [!] BOOT INCOMPLETE - a critical service/organ is absent. See lines above.
)

:: ------------------------------------------------------------
:: [ATTACHED] Launch CrewAI Multi-Agent Execution
:: ------------------------------------------------------------
echo.
echo ============================================================
echo   CREWAI ORCHESTRATION ENGINE ATTACHED
echo ============================================================
echo   Ollama Endpoint:     http://127.0.0.1:11434
echo   Gatekeeper Proxy:    http://127.0.0.1:11435
echo   Active Swarm Engine: CrewAI ReAct (Qwen VL llama.cpp :8081 - Qwen3-VL-8B, 7B fallback)
echo   Execution Terminal:  Attached (Live Output)
echo ============================================================
echo.

:: If arguments were passed on the command line, execute them directly
if not "%~1"=="" (
    echo [CREWAI] Executing task with provided arguments: %*
    echo.
    %HOJAIGA_PYTHON% -u "D:\new_automation\test_hojaiga_real_task.py" --engine crewai %*
    goto :end
)

:: Interactive task prompt when run without arguments
echo Options:
echo   [1] Type a task objective and press ENTER (e.g. "Find interior designers in Georgia")
echo   [2] Press ENTER with an empty line to launch the Swarm GUI
echo   [3] Type "standalone" to test the pure CrewAIEngine CLI
echo.
set "USER_TASK="
set /p "USER_TASK=Enter Task or Option > "
echo.

if /i "%USER_TASK%"=="standalone" (
    echo [CREWAI] Running standalone Organ 01 CrewAI Engine CLI...
    echo.
    %HOJAIGA_PYTHON% -u "D:\new_automation\All codes\core_organs\organ_01_crewai_engine.py"
    goto :end
)

if "%USER_TASK%"=="" (
    echo [CREWAI] Launching Swarm GUI Interface with CrewAI Engine...
    echo.
    %HOJAIGA_PYTHON% -u "D:\new_automation\test_hojaiga_real_task.py" --engine crewai
) else (
    echo [CREWAI] Dispatching task: "%USER_TASK%"
    echo.
    %HOJAIGA_PYTHON% -u "D:\new_automation\test_hojaiga_real_task.py" --engine crewai --command "%USER_TASK%"
)

:end
echo.
echo ============================================================
echo   HOJAIGA CREWAI EXECUTION FINISHED
echo ============================================================
pause

