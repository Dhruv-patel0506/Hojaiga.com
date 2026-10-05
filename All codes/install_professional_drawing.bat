@echo off
REM Professional Drawing Installation Script for Hojaiga
REM Optimized for NVIDIA RTX 3050 (6GB VRAM) with 32GB RAM
REM Includes CPU fallback option for lower VRAM systems

echo ========================================
echo Professional Drawing Setup for Hojaiga
echo Optimized for RTX 3050 (6GB VRAM) + 32GB RAM
echo ========================================
echo.

REM Step 1: Clone Stable Diffusion WebUI
echo [1/7] Cloning Stable Diffusion WebUI...
if not exist "stable-diffusion-webui" (
    git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
    echo [OK] Stable Diffusion WebUI cloned
) else (
    echo [SKIP] Stable Diffusion WebUI already exists
)
echo.

REM Step 2: Install Python dependencies
echo [2/7] Installing Python dependencies...
cd stable-diffusion-webui
pip install -r requirements.txt
echo [OK] Dependencies installed
cd ..
echo.

REM Step 3: Install ControlNet extension
echo [3/7] Installing ControlNet extension...
if not exist "stable-diffusion-webui\extensions\sd-webui-controlnet" (
    cd stable-diffusion-webui\extensions
    git clone https://github.com/Mikubill/sd-webui-controlnet.git
    echo [OK] ControlNet extension installed
    cd ..\..
) else (
    echo [SKIP] ControlNet extension already exists
)
echo.

REM Step 4: Install Hojaiga professional drawing dependencies
echo [4/7] Installing Hojaiga dependencies...
echo Installing PyTorch (CUDA 11.8 for RTX 3050)...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
echo.
echo Installing professional drawing libraries...
pip install diffusers transformers accelerate
pip install controlnet-aux
pip install safetensors
pip install xformers
echo.
echo Installing image processing libraries...
pip install opencv-python pillow numpy
pip install matplotlib plotly
echo.
echo Installing vector graphics libraries...
pip install svgwrite cairosvg
pip install inkscape-python
pip install drawsvg
echo.
echo Installing document processing libraries...
pip install pytesseract pdf2image
pip install pypdf
echo.
echo Installing API communication library...
pip install requests
echo [OK] All dependencies installed
echo.

REM Step 5: Create directories for models
echo [5/7] Creating model directories...
if not exist "stable-diffusion-webui\models\Stable-diffusion" mkdir "stable-diffusion-webui\models\Stable-diffusion"
if not exist "stable-diffusion-webui\models\ControlNet" mkdir "stable-diffusion-webui\models\ControlNet"
echo [OK] Model directories created
echo.

REM Step 6: Create optimized configuration file
echo [6/7] Creating optimized configuration for RTX 3050...
(
echo [OPTIMIZED FOR RTX 3050 6GB VRAM]
echo use_cpu_for_drawing = false
echo optimize_for_low_vram = true
echo default_width = 512
echo default_height = 512
echo default_steps = 20
echo default_guidance = 7.0
echo.
echo [CPU FALLBACK CONFIGURATION]
echo [Uncomment below if you want to use CPU instead of GPU]
echo use_cpu_for_drawing = true
echo optimize_for_low_vram = true
) > professional_drawing_config.txt
echo [OK] Configuration file created
echo.

REM Step 7: Manual download instructions
echo [7/7] MANUAL DOWNLOAD REQUIRED
echo.
echo You need to manually download these models:
echo.
echo MAIN MODELS (place in stable-diffusion-webui\models\Stable-diffung\):
echo 1. SD 2.1 (RECOMMENDED for RTX 3050 - lower VRAM usage):
echo    - Download: v2-1_768-ema-pruned.safetensors (5GB)
echo    - Source: https://huggingface.co/stabilityai/sd-v2-1
echo    - Why: Better for 6GB VRAM, faster generation
echo.
echo 2. SDXL Base (OPTIONAL - higher quality, more VRAM):
echo    - Download: sd_xl_base_1.0.safetensors (7GB)
echo    - Source: https://huggingface.co/stabilityai/sdxl-turbo
echo    - Why: Higher quality but may need CPU fallback
echo.
echo CONTROLNET MODELS (place in stable-diffusion-webui\models\ControlNet\):
echo [Only download if using GPU - ControlNet requires VRAM]
echo 1. ControlNet Canny: https://huggingface.co/lllyasviel/ControlNet-v1-1
echo    - Download: control_canny.safetensors
echo.
echo 2. ControlNet Depth: https://huggingface.co/lllyasviel/ControlNet-v1-1
echo    - Download: control_depth.safetensors
echo.
echo NOTE: For RTX 3050 6GB, recommend using SD 2.1 with 512x512 resolution
echo       ControlNet may cause VRAM issues - disable if needed
echo.

REM Step 8: Create launch script with optimizations
echo [8/7] Creating optimized launch script...
(
echo @echo off
echo cd stable-diffusion-webui
echo REM Optimized launch for RTX 3050 6GB VRAM
echo set COMMANDLINE_ARGS=--xformers --opt-sdp-attention --medvram
echo python webui-user.bat
) > start_stable_diffusion_optimized.bat
echo [OK] Launch script created: start_stable_diffusion_optimized.bat
echo.

REM Step 9: Test installation
echo Testing installation...
cd "D:\new_automation\All codes"
& "D:\new_automation\venv\Scripts\python.exe" -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('CUDA device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
echo.

echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo YOUR SPECS: RTX 3050 6GB VRAM + 32GB RAM
echo OPTIMIZED SETTINGS APPLIED:
echo - Resolution: 512x512 (optimized for 6GB VRAM)
echo - Steps: 20 (balanced quality/speed)
echo - Memory optimization: Enabled
echo - CPU fallback: Available if needed
echo.
echo NEXT STEPS:
echo 1. Download SD 2.1 model (recommended for your GPU)
echo    - Place in: stable-diffusion-webui\models\Stable-diffung\
echo    - File: v2-1_768-ema-pruned.safetensors
echo.
echo 2. Start Stable Diffusion WebUI:
echo    .\start_stable_diffusion_optimized.bat
echo    OR
echo    cd stable-diffusion-webui
echo    python webui-user.bat
echo.
echo 3. Access at: http://127.0.0.1:7860
echo.
echo 4. Run Hojaiga with professional drawing:
echo    cd "D:\new_automation\All codes"
echo    & "D:\new_automation\venv\Scripts\python.exe" "ai_teaching_assistant_v8_master_engine_universal_hojaiga_holographic.py" --7b --live-bridge
echo.
echo EXPECTED PERFORMANCE (RTX 3050 6GB):
echo - SD 2.1 @ 512x512: 3-8 seconds per image
echo - SDXL @ 512x512: 8-15 seconds per image
echo - CPU fallback: 20-40 seconds per image
echo.
echo If you experience VRAM errors:
echo 1. Edit professional_drawing_config.txt
echo 2. Set use_cpu_for_drawing = true
echo 3. Restart the application
echo.
pause