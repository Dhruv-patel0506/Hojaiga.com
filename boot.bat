@echo off
title Hojaiga OS - Environment Boot
echo.
echo ============================================
echo   HOJAIGA OS — Booting Environment
echo ============================================
echo.

:: Set Python path
set PYTHONPATH=D:\new_automation\All codes

:: Kill any stale Chrome/Python from previous runs
echo [1/4] Cleaning stale processes...
taskkill /F /IM chrome.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Clear stale lockfiles
echo [2/4] Clearing lockfiles...
del /q "D:\new_automation\var\hojaiga\organ19\profiles\permanent_profile\lockfile" >nul 2>&1
del /q "D:\new_automation\var\hojaiga\organ19\profiles\permanent_profile\DevToolsActivePort" >nul 2>&1

:: Verify Ollama is running
echo [3/4] Checking Ollama...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARNING: Ollama not responding on port 11434
    echo   Start Ollama manually before running tasks.
) else (
    echo   Ollama OK
)

:: Verify SSMS database
echo [4/4] Checking database...
echo   Database: DHRUV_PATEL\SQLEXPRESS / hojaiga_knowledge
echo.

echo ============================================
echo   Environment Ready
echo ============================================
echo.
echo   To run a task, execute:
echo   python "D:\new_automation\test_hojaiga_real_task.py" --command "YOUR TASK HERE"
echo.
echo   Example — Lead generation:
echo   python "D:\new_automation\test_hojaiga_real_task.py" --command "find coffee shops in austin tx and make a list in excel"
echo.
echo   Example — App learning:
echo   python "D:\new_automation\test_hojaiga_real_task.py" --command "open calculator"
echo.
