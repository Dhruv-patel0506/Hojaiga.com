@echo off
REM ==================================================================
REM  Hojaiga Brain (Windows launcher)
REM    brain.bat ingest D:\datasets\biology
REM    brain.bat import-hf Voxel51/WaveUI-25k --max-samples 2000
REM    brain.bat ask "What is a zygote?"
REM    brain.bat ask "What is the next step in this screen?" --image screen.png
REM    brain.bat overnight --epochs 3
REM    brain.bat render D:\datasets\workflow.json --out view.html
REM    brain.bat test                (runs the automated test suite)
REM  Options before the command: --variant tiny_5m|small_17m|base_37m
REM                              --workspace D:\new_automation\hojaiga_storage
REM ==================================================================
setlocal
if "%HOJAIGA_ROOT%"=="" set "HOJAIGA_ROOT=D:\new_automation"
set "PY=%HOJAIGA_ROOT%\hojaiga_env\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "HERE=%~dp0"
set "PYTHONPATH=%HERE%;%PYTHONPATH%"
set "PYTHONUTF8=1"
pushd "%HERE%"
if /I "%~1"=="test" (
  "%PY%" -X utf8 -m pytest tests -v -W ignore::UserWarning
) else (
  "%PY%" -X utf8 brain_cli.py %*
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
