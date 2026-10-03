@echo off
cd stable-diffusion-webui
REM Optimized launch for RTX 3050 6GB VRAM
REM Use main Hojaiga venv which already has torch installed
set PYTHON=..\..\venv\Scripts\python.exe
set VENV_DIR=
set COMMANDLINE_ARGS=--skip-python-version-check --skip-torch-cuda-test --skip-install --xformers --opt-sdp-attention --medvram
call webui-user.bat
