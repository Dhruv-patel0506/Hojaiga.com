@echo off
REM ================================================================
REM  Hojaiga Brain launcher (Windows)
REM    brain.bat pipeline --data D:\datasets\biology      (everything)
REM    brain.bat ask "What is a zygote?" --trace
REM    brain.bat finetune --data D:\datasets\gmail --name gmail
REM    brain.bat --adapter gmail ask "..."
REM    brain.bat render chapter3.pdf --out chapter3.html --subject biology
REM    brain.bat overnight --data D:\datasets --hours 8 --loop
REM    brain.bat --help
REM ================================================================
setlocal
if "%HOJAIGA_ROOT%"=="" set "HOJAIGA_ROOT=D:\new_automation"
set "PY=%HOJAIGA_ROOT%\hojaiga_env\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONPATH=%HOJAIGA_ROOT%;%HOJAIGA_ROOT%\All codes"
if "%HOJAIGA_BRAIN_HOME%"=="" set "HOJAIGA_BRAIN_HOME=%HOJAIGA_ROOT%\storage\brain"
if "%HOJAIGA_NI_DB%"=="" set "HOJAIGA_NI_DB=%HOJAIGA_ROOT%\storage\natural_intelligence.sqlite"
set "PYTHONUTF8=1"
pushd "%HOJAIGA_ROOT%\All codes"
"%PY%" -X utf8 -m core_organs.hojaiga_ml_engine brain %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
