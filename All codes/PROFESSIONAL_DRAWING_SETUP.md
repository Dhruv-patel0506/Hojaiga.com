# 🎨 Professional Local Drawing Setup Guide

## 🚀 Complete Installation (No APIs, No Rate Limits, 100% Local)

### Step 1: Install Stable Diffusion WebUI (AUTOMATIC1111)

**Clone and Setup:**
```bash
# Clone the repository
git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
cd stable-diffusion-webui

# Install dependencies (Python 3.10 recommended)
pip install -r requirements.txt

# Run it
python webui-user.bat
```

**Access at:** `http://127.0.0.1:7860`

### Step 2: Download Professional Models

**Place these files in `stable-diffusion-webui/models/Stable-diffusion/`:**

**1. Stable Diffusion XL (SDXL) - For Professional Art**
- **Download:** `sd_xl_base_1.0.safetensors` (7GB)
- **Source:** https://huggingface.co/stabilityai/sdxl-turbo
- **Purpose:** High-quality professional drawing

**2. Stable Diffusion 2.1 - For Technical Diagrams**
- **Download:** `v2-1_768-ema-pruned.safetensors` (5GB)
- **Source:** https://huggingface.co/stabilityai/sd-v2-1
- **Purpose:** Faster, good for diagrams and technical drawings

### Step 3: Install ControlNet Extension

```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/Mikubill/sd-webui-controlnet.git
```

**Download ControlNet Models (place in `models/ControlNet/`):**

**1. ControlNet Canny** - For edge detection/diagrams
- **Download:** `control_canny.safetensors`
- **Source:** https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main

**2. ControlNet Depth** - For depth-aware drawings
- **Download:** `control_depth.safetensors`
- **Source:** https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main

**3. ControlNet Pose** - For anatomical drawings
- **Download:** `control_openpose.safetensors`
- **Source:** https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main

**4. ControlNet Scribble** - For sketch-to-image
- **Download:** `control_scribble.safetensors`
- **Source:** https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main

### Step 4: Install Python Dependencies

```bash
# Core dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Professional drawing libraries
pip install diffusers transformers accelerate
pip install controlnet-aux
pip install safetensors
pip install xformers

# Image processing
pip install opencv-python pillow numpy
pip install matplotlib plotly

# Vector graphics
pip install svgwrite cairosvg
pip install inkscape-python
pip install drawsvg

# Document processing
pip install pytesseract pdf2image
pip install pypdf

# API communication
pip install requests
```

### Step 5: Configure System for Hojaiga

**Environment Variables (Optional):**
```bash
# Stable Diffusion WebUI URL
$env:SD_WEBUI_URL = "http://127.0.0.1:7860"

# Model quality settings
$env:SD_STEPS = "30"
$env:SD_GUIDANCE_SCALE = "7.5"
```

### Step 6: Test Professional Drawing

```bash
cd "D:\new_automation\All codes"
& "D:\new_automation\venv\Scripts\python.exe" professional_drawing_engine.py
```

### Step 7: Integrate with Hojaiga

**The system is already integrated in `app.py`:**
```python
from app import TutorExtensions

# Initialize with Stable Diffusion connection
ext = TutorExtensions(
    sd_webui_url="http://127.0.0.1:7860"
)

# Check status
status = ext.get_professional_drawing_status()
print("Professional drawing available:", status["available"])
print("WebUI connected:", status["webui_connected"])
```

## 🎨 Usage Examples

### Generate Anatomical Drawing
```python
result = ext.generate_anatomical_drawing("human nervous system", detailed=True)
print("Success:", result["success"])
print("Image path:", result["image_path"])
```

### Generate Scientific Diagram
```python
result = ext.generate_scientific_diagram("solar system", labeled=True)
print("Success:", result["success"])
```

### Generate Professional Drawing with Style
```python
result = ext.generate_professional_drawing(
    prompt="detailed diagram of human heart with chambers",
    style="medical",
    subject_type="anatomical"
)
print("Success:", result["success"])
```

## 🎯 Available Styles

- **realistic** - Photorealistic, highly detailed
- **artistic** - Creative, expressive, bold colors
- **scientific** - Accurate, detailed, educational
- **medical** - Anatomically accurate, professional
- **technical** - Precise, engineering standard
- **sketch** - Hand-drawn, artistic, rough
- **watercolor** - Soft colors, artistic, fluid
- **oil_painting** - Rich colors, textured, classical
- **digital_art** - Modern, vibrant, detailed

## 🎯 Available Subject Types

- **anatomical** - Medical accuracy, detailed structure
- **biological** - Scientific accuracy, detailed
- **mechanical** - Engineering precise, technical
- **architectural** - Perspective, detailed structure
- **abstract** - Creative, unique, expressive
- **landscape** - Beautiful scenery, detailed environment
- **portrait** - Detailed features, realistic
- **diagram** - Clear, educational, labeled

## 💻 Hardware Requirements

**Minimum:**
- GPU: NVIDIA RTX 3060 (8GB VRAM)
- RAM: 16GB
- Storage: 20GB free space
- CPU: Modern multi-core processor

**Recommended:**
- GPU: NVIDIA RTX 4070 or better (12GB+ VRAM)
- RAM: 32GB
- Storage: 50GB free space (SSD)
- CPU: Intel i7 or AMD Ryzen 7

**For CPU-only (slower):**
- RAM: 32GB minimum
- Storage: 50GB free space
- Expect 10-30 seconds per image

## ⚡ Performance Expectations

**With GPU (RTX 3060):**
- SDXL: 5-10 seconds per image
- SD 2.1: 2-5 seconds per image
- ControlNet: +2-3 seconds per image

**With CPU:**
- SDXL: 30-60 seconds per image
- SD 2.1: 15-30 seconds per image
- ControlNet: +10-15 seconds per image

## 🔧 Troubleshooting

**WebUI not connecting:**
1. Make sure Stable Diffusion WebUI is running
2. Check URL: `http://127.0.0.1:7860`
3. Try in browser first to confirm it's accessible

**Out of memory errors:**
1. Reduce image size to 512x512
2. Reduce steps to 20
3. Use SD 2.1 instead of SDXL
4. Close other applications

**Poor quality results:**
1. Increase steps to 40-50
2. Increase guidance_scale to 8.0-10.0
3. Use better prompts
4. Try different models

## 🚀 Advanced Configuration

**Custom settings in `professional_drawing_engine.py`:**
```python
engine = ProfessionalDrawingEngine(
    sd_webui_url="http://127.0.0.1:7860"
)

# High quality settings
request = DrawingRequest(
    prompt="detailed drawing",
    style=DrawingStyle.REALISTIC,
    width=1536,  # Higher resolution
    height=1536,
    steps=50,  # More steps for quality
    guidance_scale=8.0  # Higher guidance
)
```

## 📚 Additional Resources

**Stable Diffusion WebUI:**
- GitHub: https://github.com/AUTOMATIC1111/stable-diffusion-webui
- Documentation: https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki

**ControlNet:**
- GitHub: https://github.com/Mikubill/sd-webui-controlnet
- Models: https://huggingface.co/lllyasviel/ControlNet-v1-1

**Model Downloads:**
- HuggingFace: https://huggingface.co
- CivitAI: https://civitai.com (additional models)

## ✅ Quick Start Checklist

- [ ] Clone Stable Diffusion WebUI
- [ ] Install requirements
- [ ] Download SDXL model
- [ ] Download SD 2.1 model
- [ ] Install ControlNet extension
- [ ] Download ControlNet models
- [ ] Install Python dependencies
- [ ] Start WebUI: `python webui-user.bat`
- [ ] Test connection: Visit `http://127.0.0.1:7860`
- [ ] Run professional drawing test
- [ ] Integrate with Hojaiga

## 🎉 After Setup

Once everything is installed:

```bash
# Start Stable Diffusion WebUI
cd stable-diffusion-webui
python webui-user.bat

# In another terminal, run Hojaiga
cd "D:\new_automation\All codes"
& "D:\new_automation\venv\Scripts\python.exe" "ai_teaching_assistant_v8_master_engine_universal_hojaiga_holographic.py" --7b --live-bridge
```

**The system will now be able to:**
- ✅ Generate professional anatomical drawings
- ✅ Create medical-grade illustrations
- ✅ Produce complex organic diagrams
- ✅ Render artistic visualizations
- ✅ All 100% local, no APIs, no rate limits

**Estimated setup time:** 30-60 minutes (mostly downloading models)
**Total storage needed:** ~20-50GB
**One-time setup:** Works forever after installation