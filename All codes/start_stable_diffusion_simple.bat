@echo off
echo Starting Stable Diffusion WebUI with Hojaiga venv...
cd stable-diffusion-webui
set PYTHON=..\..\venv\Scripts\python.exe
set VENV_DIR=
set COMMANDLINE_ARGS=--skip-python-version-check --skip-torch-cuda-test --skip-install --xformers --opt-sdp-attention --medvram
call webui-user.bat
