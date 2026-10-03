@echo off
setlocal
cd /d "D:\new_automation"
python -u "D:\new_automation\All codes\ai_teaching_assistant_v8_master_engine_universal_hojaiga_holographic.py" %*
set "HOJAIGA_EXIT=%ERRORLEVEL%"
if not "%HOJAIGA_EXIT%"=="0" echo [Hojaiga] Process exited with code %HOJAIGA_EXIT%.
endlocal & exit /b %HOJAIGA_EXIT%