@echo off
echo Starting Stable Diffusion WebUI directly with Hojaiga venv...
cd stable-diffusion-webui
set PYTHONPATH=%PYTHONPATH%;..\..\venv\Lib\site-packages
set STABLE_DIFFUSION_REPO=repositories\stable-diffusion-stability-ai
..\..\venv\Scripts\python.exe launch.py --skip-python-version-check --skip-torch-cuda-test --skip-install --skip-prepare-environment --xformers --opt-sdp-attention --medvram
