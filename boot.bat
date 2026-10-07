@echo off
title Hojaiga OS - Boot & Preflight
setlocal

set "ROOT=D:\new_automation"
set "PY=%ROOT%\hojaiga_env\Scripts\python.exe"
set "PYTHONPATH=%ROOT%\All codes"

echo.
echo  ============================================
echo    HOJAIGA OS - Boot + Preflight
echo  ============================================
echo.

if not exist "%PY%" (
    echo  [FAIL] Hojaiga venv python not found at "%PY%"
    echo         Create it first:  python -m venv hojaiga_env
    exit /b 1
)

REM Non-destructive: we NO LONGER kill all chrome.exe/python.exe (that closed your own
REM browser and any other running work). Isolated automation Chrome uses its own profile
REM and port; leave the rest of the machine alone.

echo  Running readiness preflight (never fakes a green)...
echo.
"%PY%" "%ROOT%\hojaiga_preflight.py"
set "PREFLIGHT=%ERRORLEVEL%"
echo.

if not "%PREFLIGHT%"=="0" (
    echo  Stopping: the preflight reported NO-GO. Fix the [FAIL] lines above, then run boot again.
    echo  (If Ollama is the issue: start it with "ollama serve" in another window.)
    exit /b 1
)

echo  ============================================
echo    Environment ready.
echo  ============================================
echo.
echo    Run a task:
echo      "%PY%" "%ROOT%\test_hojaiga_real_task.py" --command "YOUR TASK HERE"
echo.
echo    Or launch the avatar / holographic teaching engine:
echo      call "%ROOT%\launch_hojaiga_avatar.bat"
echo.
endlocal
